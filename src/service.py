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

logger = logging.getLogger("codebone.service")


class CodeBoneService:
    def __init__(self, config: Config):
        self.config = config
        self.provider: Provider = build_provider(config)
        self.storage = Storage(config.db_path)
        self.scans = ScanManager(config)
        self.sniffer: Optional[Sniffer] = None
        self.last_synced: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_reconciliation: Optional[dict] = None
        self.sniffing = False
        self.on_activity_start: Optional[Callable[[], None]] = None
        self.on_activity_end: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    def start(self, auto_scan: bool = True, on_progress: Optional[Callable[[int, int, str], None]] = None):
        if not self.config.is_configured:
            logger.warning("CodeBone not configured — skipping sniffer start")
            return
        project_path = self.config.project_path
        ignore_dirs = list(self.config.get_ignore_dirs(project_path))
        self.sniffer = Sniffer(
            project_path=project_path,
            extensions=self.config.get("watched_extensions"),
            ignore_dirs=ignore_dirs,
            on_change=self._handle_change,
            on_delete=self._handle_delete,
            on_batch=self._handle_batch,
        )
        self.sniffer.start()
        if auto_scan:
            threading.Thread(
                target=self.rescan_all,
                args=(on_progress,),
                daemon=True,
                name="codebone-initial-rescan",
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

    def stats_snapshot(self) -> dict:
        """Lightweight status/counts payload for the menu bar dashboard."""
        index = self.storage.entity_index()
        proj = self.config.project_path
        return {
            "configured": self.config.is_configured,
            "project_path": str(proj) if proj else None,
            "repo_name": proj.name if proj else "None",
            "model_name": self.config.active_model_display_name,
            "sniffing": self.sniffing,
            "last_synced": self.last_synced,
            "file_count": self.storage.file_count(),
            "connection_count": len(self.storage.graph_edges()),
            "domain_count": len(index["domains"]),
            "table_count": len(index["tables"]),
            "route_count": len(index["routes"]),
            "event_count": len(index["events"]),
        }

    def reset_map(self):
        self.storage.reset()
        self.last_synced = None

    def rescan_all(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        force: bool = False,
    ) -> tuple[int, int, int]:
        """Full scan of the project folder:
        - Detects watched files
        - Compares mtime and hash to skip unchanged files (unless force=True)
        - Sniffs new/modified files
        - Removes stale database entries
        """
        if not self.config.is_configured:
            return 0, 0, 0
        project_path = self.config.project_path
        if not project_path or not project_path.exists():
            return 0, 0, 0

        extensions = set(self.config.get("watched_extensions"))
        ignore_dirs = self.config.get_ignore_dirs(project_path)

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
                    if not force and rel_path in existing_mtimes and existing_mtimes[rel_path] >= mtime:
                        skipped += 1
                        continue

                    try:
                        self._sniff_file(path, mtime=mtime, force=force)
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

    def run_deep_scan(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> tuple[int, int, int]:
        """One-off full re-sniff using a larger, slower local model (Deep Scan Mode),
        then restores the normal fast brain. Heavier on RAM/CPU/time than the default."""
        model_path = self.config.get("deep_scan_model_path")
        if not model_path or not Path(model_path).exists():
            raise ValueError("No Deep Scan model configured")

        from .providers import BuiltinProvider

        original_provider = self.provider
        deep_provider = BuiltinProvider(model_path=model_path, n_ctx=4096)
        self.provider = deep_provider
        try:
            return self.rescan_all(on_progress=on_progress, force=True)
        finally:
            deep_provider.close()
            self.provider = original_provider

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

    def _sniff_file(self, path: Path, mtime: Optional[float] = None, force: bool = False):
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
        if not force and existing_hashes.get(rel_path) == content_hash:
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

    def _handle_batch(self, changed: set[Path], deleted: set[Path]):
        """Handles burst changes (e.g. git checkout, branch switch, mass file moves/refactors)."""
        project_path = self.config.project_path
        if not project_path:
            return

        with self._lock:
            self.sniffing = True
            if self.on_activity_start:
                self.on_activity_start()
            try:
                # 1. Batch delete removed files in SQLite
                deleted_rels = []
                for p in deleted:
                    try:
                        rel = str(p.relative_to(project_path))
                        deleted_rels.append(rel)
                    except ValueError:
                        pass
                if deleted_rels:
                    self.storage.remove_files(deleted_rels)
                    logger.info("Batch deleted %d files from storage", len(deleted_rels))

                # 2. Check changed files against existing SHA-256 hashes
                existing_hashes = self.storage.get_file_hashes()
                records_by_hash = self.storage.get_records_by_hash()

                genuine_sniff_paths: list[Path] = []
                for p in changed:
                    if not p.exists() or not p.is_file():
                        continue
                    try:
                        rel = str(p.relative_to(project_path))
                    except ValueError:
                        continue

                    try:
                        content_bytes = p.read_bytes()
                        content_hash = hashlib.sha256(content_bytes).hexdigest()
                    except OSError:
                        continue

                    # If file has identical hash at this path, skip
                    if existing_hashes.get(rel) == content_hash:
                        continue

                    # If hash matches a previously indexed file that was moved/renamed:
                    if content_hash in records_by_hash:
                        prev_records = records_by_hash[content_hash]
                        if prev_records:
                            rec = dict(prev_records[0])
                            rec["path"] = rel
                            try:
                                rec["mtime"] = p.stat().st_mtime
                            except OSError:
                                pass
                            self.storage.insert_record(rec)
                            logger.info("Instantly re-linked moved file %s via SHA-256 (0 LLM cost)", rel)
                            continue

                    genuine_sniff_paths.append(p)

                # 3. Process genuine code modifications
                if genuine_sniff_paths:
                    logger.info("Batch sniffing %d modified/new files", len(genuine_sniff_paths))
                    for p in genuine_sniff_paths:
                        try:
                            self._sniff_file(p)
                        except Exception as exc:
                            self.last_error = str(exc)
                            logger.exception("Error sniffing file %s in batch", p)

                # 4. If this was a large batch (e.g. branch switch with >= 8 files), auto-save snapshot
                if len(changed) + len(deleted) >= 8:
                    try:
                        self.scans.save_snapshot(
                            project_name=project_path.name,
                            project_path=project_path,
                            storage=self.storage,
                        )
                    except Exception as exc:
                        logger.warning("Failed to auto-save scan snapshot after batch: %s", exc)
            finally:
                self.sniffing = False
                if self.on_activity_end:
                    self.on_activity_end()

    def _handle_delete(self, path: Path):
        project_path = self.config.project_path
        if not project_path:
            return
        try:
            rel_path = str(path.relative_to(project_path))
        except ValueError:
            rel_path = str(path)
        self.storage.remove_file(rel_path)


# Backwards compatibility alias
PugService = CodeBoneService
