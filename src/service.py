"""PugService ties together config, brain provider, watcher, storage, and server."""
import hashlib
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .providers import Provider, build_provider
from .scans import ScanManager, ScanReconciler
from .storage import Storage
from .watcher import Sniffer

logger = logging.getLogger("pug.service")


class PugService:
    def __init__(self, config: Config):
        self.config = config
        self.provider: Provider = build_provider(config)
        self.storage = Storage(config.db_path)
        self.scans = ScanManager(config)
        self.sniffer: Optional[Sniffer] = None
        self.last_synced: Optional[str] = None
        self.last_reconciliation: Optional[dict] = None
        self.sniffing = False
        self.on_activity_start: Optional[Callable[[], None]] = None
        self.on_activity_end: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    def start(self, auto_scan: bool = True, on_progress: Optional[Callable[[int, int, str], None]] = None):
        if not self.config.is_configured:
            logger.warning("PUG not configured — skipping sniffer start")
            return
        project_path = self.config.project_path
        self.sniffer = Sniffer(
            project_path=project_path,
            extensions=self.config.get("watched_extensions"),
            ignore_dirs=self.config.get("ignore_dirs"),
            on_change=self._handle_change,
            on_delete=self._handle_delete,
        )
        self.sniffer.start()
        if auto_scan:
            threading.Thread(
                target=self.rescan_all,
                args=(on_progress,),
                daemon=True,
                name="pug-initial-rescan",
            ).start()

    def stop(self):
        if self.sniffer:
            self.sniffer.stop()
            self.sniffer = None
        if hasattr(self.provider, "close"):
            self.provider.close()

    def reload_provider(self):
        """Call after brain settings change."""
        self.provider = build_provider(self.config)

    def reset_map(self):
        self.storage.reset()
        self.last_synced = None

    def rescan_all(self, on_progress: Optional[Callable[[int, int, str], None]] = None) -> tuple[int, int, int]:
        """Full scan of the project folder:
        - Detects watched files
        - Compares mtime and hash to skip unchanged files
        - Sniffs new/modified files
        - Removes stale database entries
        """
        if not self.config.is_configured:
            return 0, 0, 0
        project_path = self.config.project_path
        if not project_path or not project_path.exists():
            return 0, 0, 0

        extensions = set(self.config.get("watched_extensions"))
        ignore_dirs = set(self.config.get("ignore_dirs"))

        matching_files: list[Path] = []
        try:
            for path in project_path.rglob("*"):
                if path.is_file() and path.suffix in extensions and not any(
                    part in ignore_dirs for part in path.parts
                ):
                    matching_files.append(path)
        except OSError:
            logger.exception("Error scanning project path %s", project_path)
            return 0, 0, 0

        total = len(matching_files)
        existing_mtimes = self.storage.get_file_mtimes()
        active_rel_paths = set()

        sniffed = 0
        skipped = 0

        with self._lock:
            self.sniffing = True
            if self.on_activity_start:
                self.on_activity_start()
            try:
                for idx, path in enumerate(matching_files, start=1):
                    try:
                        rel_path = str(path.relative_to(project_path))
                    except ValueError:
                        rel_path = str(path)
                    active_rel_paths.add(rel_path)

                    if on_progress:
                        on_progress(idx, total, rel_path)

                    try:
                        file_stat = path.stat()
                        mtime = file_stat.st_mtime
                    except OSError:
                        continue

                    # If mtime unchanged, skip reading and re-sniffing
                    if rel_path in existing_mtimes and existing_mtimes[rel_path] >= mtime:
                        skipped += 1
                        continue

                    try:
                        self._sniff_file(path, mtime=mtime)
                        sniffed += 1
                    except Exception:
                        logger.exception("Error sniffing %s during rescan", path)

                # Clean up deleted files
                deleted_paths = [p for p in existing_mtimes.keys() if p not in active_rel_paths]
                if deleted_paths:
                    self.storage.remove_files(deleted_paths)
                    logger.info("Cleaned up %d deleted files from storage", len(deleted_paths))

            finally:
                self.sniffing = False
                if self.on_activity_end:
                    self.on_activity_end()

        logger.info("Rescan finished: %d total, %d sniffed, %d skipped", total, sniffed, skipped)
        if self.config.project_path:
            try:
                self.scans.save_snapshot(
                    project_name=self.config.project_path.name,
                    project_path=self.config.project_path,
                    storage=self.storage,
                )
            except Exception as exc:
                logger.warning("Failed to auto-save scan snapshot: %s", exc)
        return total, sniffed, skipped

    def adopt_scan(
        self,
        source_scan_id_or_path: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """Reconciles the currently configured project folder against an existing scan."""
        if not self.config.is_configured:
            raise ValueError("No project folder configured")

        project_path = self.config.project_path
        scan_meta = self.scans.get_scan(source_scan_id_or_path)
        if not scan_meta:
            raise FileNotFoundError(f"Source scan '{source_scan_id_or_path}' not found")

        source_db_path = Path(scan_meta["db_path"])
        if not source_db_path.exists():
            raise FileNotFoundError(f"Source database file missing: {source_db_path}")

        with self._lock:
            self.sniffing = True
            if self.on_activity_start:
                self.on_activity_start()
            try:
                report = ScanReconciler.reconcile(
                    target_project=project_path,
                    source_db_path=source_db_path,
                    target_storage=self.storage,
                    provider=self.provider,
                    config=self.config,
                    on_progress=on_progress,
                )
                self.last_reconciliation = report
                self.last_synced = "reconciled"

                # Update snapshot with reconciled state
                self.scans.save_snapshot(
                    project_name=project_path.name,
                    project_path=project_path,
                    storage=self.storage,
                )
                return report
            finally:
                self.sniffing = False
                if self.on_activity_end:
                    self.on_activity_end()

    def _handle_change(self, path: Path):
        with self._lock:
            self.sniffing = True
            if self.on_activity_start:
                self.on_activity_start()
            try:
                self._sniff_file(path)
            except Exception:
                logger.exception("Error sniffing %s", path)
            finally:
                self.sniffing = False
                if self.on_activity_end:
                    self.on_activity_end()

    def _sniff_file(self, path: Path, mtime: Optional[float] = None):
        project_path = self.config.project_path
        if not project_path:
            return

        try:
            rel_path = str(path.relative_to(project_path))
        except ValueError:
            rel_path = str(path)

        try:
            content_bytes = path.read_bytes()
            code = content_bytes.decode("utf-8", errors="ignore")
            if mtime is None:
                mtime = path.stat().st_mtime
        except OSError:
            return

        # Check content hash
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        existing_hashes = self.storage.get_file_hashes()
        if existing_hashes.get(rel_path) == content_hash:
            # File content has not actually changed
            return

        raw_output = self.provider.sniff(rel_path, code[:6000])
        res = self.storage.update_file(
            rel_path,
            raw_output,
            mtime=mtime,
            content_hash=content_hash,
        )

        self.last_synced = rel_path
        logger.info(
            "Sniffed %s -> %d tables, %d routes, %d events, %d domains",
            rel_path,
            len(res.get("tables", [])),
            len(res.get("routes", [])),
            len(res.get("events", [])),
            len(res.get("domains", [])),
        )

    def _handle_delete(self, path: Path):
        project_path = self.config.project_path
        if not project_path:
            return
        try:
            rel_path = str(path.relative_to(project_path))
        except ValueError:
            rel_path = str(path)
        self.storage.remove_file(rel_path)
