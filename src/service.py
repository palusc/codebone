"""PugService ties together config, brain provider, watcher, storage, and server."""
import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import Config, is_watched_file, load_gitignore_spec
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
        self.scan_progress: Optional[dict] = None
        self.last_baseline: Optional[dict] = None
        self.on_activity_start: Optional[Callable[[], None]] = None
        self.on_activity_end: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    def start(self, auto_scan: bool = True, on_progress: Optional[Callable[[int, int, str], None]] = None):
        if not self.config.is_configured:
            logger.warning("codebone not configured — skipping sniffer start")
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

    def inspect_baseline(self, project_path: Optional[Path] = None) -> dict:
        """Fast pre-scan assessment that produces a baseline overview:
        counts files, groups languages, determines files needing indexing vs cached,
        and calculates an estimated initial load duration."""
        proj = project_path or self.config.project_path
        if not proj or not proj.exists():
            return {
                "total_files": 0,
                "files_to_index": 0,
                "cached_files": 0,
                "languages": [],
                "languages_summary": "No files",
                "estimated_seconds": 0,
                "estimated_time_str": "0s",
            }

        extensions = set(self.config.get("watched_extensions"))
        ignore_dirs = self.config.get_ignore_dirs(proj)
        gitignore_spec = load_gitignore_spec(proj)

        matching_files: list[Path] = []
        try:
            for path in proj.rglob("*"):
                if is_watched_file(path, extensions, ignore_dirs, gitignore_spec=gitignore_spec, project_path=proj):
                    matching_files.append(path)
        except OSError:
            logger.exception("Error during baseline inspection of %s", proj)
            return {
                "total_files": 0,
                "files_to_index": 0,
                "cached_files": 0,
                "languages": [],
                "languages_summary": "Error reading files",
                "estimated_seconds": 0,
                "estimated_time_str": "0s",
            }

        total = len(matching_files)
        existing_mtimes = self.storage.get_file_mtimes()

        # Count per extension
        ext_counts: dict[str, int] = {}
        files_to_sniff = 0
        cached_count = 0

        for p in matching_files:
            ext = p.suffix.lower() if p.suffix else p.name
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            try:
                rel = str(p.relative_to(proj))
                mtime = p.stat().st_mtime
            except (ValueError, OSError):
                files_to_sniff += 1
                continue

            if rel in existing_mtimes and existing_mtimes[rel] >= mtime:
                cached_count += 1
            else:
                files_to_sniff += 1

        # Format top languages
        ext_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".tsx": "React TSX", ".jsx": "React JSX", ".go": "Go",
            ".rs": "Rust", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
            ".swift": "Swift", ".kt": "Kotlin", ".c": "C", ".cpp": "C++",
            ".h": "C/C++ Header", ".sql": "SQL", ".graphql": "GraphQL",
            ".sh": "Shell Script", ".bash": "Shell Script", ".zsh": "Shell Script",
            ".json": "JSON Config", ".yaml": "YAML Config", ".yml": "YAML Config",
            ".toml": "TOML Config", ".xml": "XML", ".ini": "Config",
            ".md": "Markdown", ".txt": "Text Doc", ".html": "HTML", ".css": "CSS",
            ".scss": "SCSS", ".vue": "Vue", ".svelte": "Svelte", ".prisma": "Prisma",
        }
        sorted_exts = sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True)
        languages = [f"{ext_map.get(ext, ext)} ({cnt})" for ext, cnt in sorted_exts]
        languages_summary = ", ".join(languages[:3]) if languages else "None"

        # Time estimation based on active provider
        provider_type = self.config.get("brain_provider", "builtin")
        if provider_type == "builtin":
            sec_per_file = 0.35  # Apple Silicon Metal Qwen 0.5B
        elif provider_type == "local_url":
            sec_per_file = 0.5   # Ollama / Local HTTP
        elif provider_type == "cloud":
            sec_per_file = 0.4   # Cloud API
        else:
            sec_per_file = 0.05

        est_seconds = max(1, round(files_to_sniff * sec_per_file + cached_count * 0.002))
        if files_to_sniff == 0 and total > 0:
            est_time_str = "< 1 second (all cached)"
        elif est_seconds < 5:
            est_time_str = "~3–5 seconds"
        elif est_seconds < 60:
            est_time_str = f"~{est_seconds} seconds"
        else:
            mins = round(est_seconds / 60, 1)
            est_time_str = f"~{mins} minutes"

        res = {
            "total_files": total,
            "files_to_index": files_to_sniff,
            "cached_files": cached_count,
            "languages": languages,
            "languages_summary": languages_summary,
            "estimated_seconds": est_seconds,
            "estimated_time_str": est_time_str,
        }
        self.last_baseline = res
        return res

    @property
    def is_running(self) -> bool:
        return self.sniffer is not None and self.sniffer.is_alive()

    def stats_snapshot(self) -> dict:
        """Lightweight status/counts payload for the menu bar dashboard."""
        index = self.storage.entity_index()
        proj = self.config.project_path
        return {
            "configured": self.config.is_configured,
            "running": self.is_running,
            "project_path": str(proj) if proj else None,
            "repo_name": proj.name if proj else "None",
            "model_name": self.config.active_model_display_name,
            "sniffing": self.sniffing,
            "scan_progress": self.scan_progress,
            "baseline": self.last_baseline,
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
        gitignore_spec = load_gitignore_spec(project_path)

        matching_files: list[Path] = []
        try:
            for path in project_path.rglob("*"):
                if is_watched_file(path, extensions, ignore_dirs, gitignore_spec=gitignore_spec, project_path=project_path):
                    matching_files.append(path)
        except OSError:
            logger.exception("Error scanning project path %s", project_path)
            return 0, 0, 0

        total = len(matching_files)
        existing_mtimes = self.storage.get_file_mtimes()
        active_rel_paths = set()

        sniffed = 0
        skipped = 0
        start_time = time.time()

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

                    elapsed = max(0.01, time.time() - start_time)
                    rate = idx / elapsed
                    remaining_count = total - idx
                    eta_sec = max(0, round(remaining_count / rate)) if rate > 0 else 0
                    if eta_sec < 60:
                        eta_str = f"~{eta_sec}s"
                    else:
                        eta_str = f"~{round(eta_sec / 60, 1)}m"

                    self.scan_progress = {
                        "current": idx,
                        "total": total,
                        "sniffed": sniffed,
                        "skipped": skipped,
                        "pct": int((idx / total) * 100),
                        "eta_seconds": eta_sec,
                        "eta_str": eta_str,
                        "current_file": rel_path,
                    }

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
                    except Exception as exc:
                        logger.debug("Tolerated error sniffing %s during rescan: %s", path, exc)

                # Clean up deleted files
                deleted_paths = [p for p in existing_mtimes.keys() if p not in active_rel_paths]
                if deleted_paths:
                    self.storage.remove_files(deleted_paths)
                    logger.info("Cleaned up %d deleted files from storage", len(deleted_paths))

            finally:
                self.sniffing = False
                self.scan_progress = None
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
            except Exception as exc:
                logger.debug("Tolerated error sniffing %s: %s", path, exc)
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

        # Syntax-error-resilience for incomplete code during edits (Issue #5):
        # If code has broken syntax (e.g. unclosed parenthesis/quotes during typing),
        # quietly preserve the last known good state in SQLite without error logs.
        if path.suffix == ".py":
            try:
                import ast
                ast.parse(code)
            except SyntaxError as syn_err:
                logger.debug(
                    "Tolerated syntax error in incomplete file %s during edit (preserving previous state): %s",
                    rel_path,
                    syn_err,
                )
                return
        elif path.suffix == ".json":
            try:
                import json
                json.loads(code)
            except Exception as json_err:
                logger.debug(
                    "Tolerated malformed JSON in %s during edit (preserving previous state): %s",
                    rel_path,
                    json_err,
                )
                return

        try:
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
        except (SyntaxError, ValueError) as exc:
            logger.debug(
                "Tolerated parsing error in %s (preserved previous state): %s",
                rel_path,
                exc,
            )
            return
        except Exception as exc:
            logger.debug("Non-fatal parsing issue for %s: %s", rel_path, exc)
            return

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
                            logger.debug("Tolerated error sniffing file %s in batch: %s", p, exc)

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
