"""CodeBoneService ties together config, brain provider, watcher, storage, and server."""
import ast
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import (
    BASE_MODEL_PATH,
    GLOBAL_IGNORED_DIRS,
    MAX_READ_BYTES,
    _is_secret_or_junk,
    Config,
    is_pruned_rel,
    is_watched_file,
    list_watched_files,
    load_gitignore_spec,
)
from .providers import FastFallbackProvider, Provider, build_provider
from .scans import ScanManager, ScanReconciler
from .storage import Storage
from .watcher import Sniffer

logger = logging.getLogger("codebone.service")

# Bump when the analysis (prompt, extraction rules, vocabulary) changes so rows written by an older analyser are rebuilt
ANALYSIS_VERSION = "2"
BROKEN_GRACE_SECONDS = 20.0  # how long an unparsable edit keeps the previous analysis
PROGRESS_INTERVAL = 0.25  # seconds between progress callbacks during a scan
SNAPSHOT_INTERVAL = 600.0  # at most one automatic snapshot per 10 minutes


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
        self.scan_progress: Optional[dict] = None
        self.last_baseline: Optional[dict] = None
        self.model_status: Optional[str] = None  # e.g. "downloading 42%" while the base model is fetched
        self.on_activity_start: Optional[Callable[[], None]] = None
        self.on_activity_end: Optional[Callable[[], None]] = None
        # _lock serialises single write units (one file, one batch step) so the watcher can interleave with a
        # running scan instead of waiting for all of it; _scan_guard allows one full scan at a time.
        self._lock = threading.RLock()
        self._scan_guard = threading.Lock()
        self._rescan_requested = False
        self._req_lock = threading.Lock()  # makes 'request another pass' and 'release the scan guard' one atomic step
        self._epoch = 0  # bumped when watching stops or the project changes: running scans notice and abort
        self._active = 0
        self._active_lock = threading.Lock()
        self._last_snapshot = 0.0
        self._broken_since: dict = {}
        self._snapshot_revision = -1

    # ── activity bookkeeping ────────────────────────────────────────────
    @property
    def sniffing(self) -> bool:
        return self._active > 0

    def _begin(self):
        with self._active_lock:
            self._active += 1
            first = self._active == 1
        if first and self.on_activity_start:
            self.on_activity_start()

    def _end(self):
        with self._active_lock:
            self._active = max(0, self._active - 1)
            last = self._active == 0
        if last and self.on_activity_end:
            self.on_activity_end()

    # ── lifecycle ───────────────────────────────────────────────────────
    def _bind_project(self):
        """The index belongs to exactly one project folder. Opening another one must not serve (or mtime-skip
        against) the previous project's rows."""
        proj = self.config.project_path
        if not proj:
            return
        with self._lock:
            stale = self.storage.get_meta("analysis_version") != ANALYSIS_VERSION
            if self.storage.get_meta("project_path") != str(proj) or stale:
                if self.storage.file_count():
                    logger.info("Rebuilding the index (%s)", "new analysis version" if stale else f"project changed to {proj}")
                    self.storage.reset()
                self.storage.set_meta("project_path", str(proj))
                self.storage.set_meta("analysis_version", ANALYSIS_VERSION)

    def start(self, auto_scan: bool = True, on_progress: Optional[Callable[[int, int, str], None]] = None):
        if not self.config.is_configured:
            logger.warning("codebone not configured, skipping sniffer start")
            return
        self.stop()
        project_path = self.config.project_path
        self._bind_project()
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
        """Stop watching and tell any running scan to abort. The loaded model stays in memory so switching
        projects does not reload it; use close() when the app quits."""
        self._epoch += 1
        sniffer, self.sniffer = self.sniffer, None
        if sniffer:
            sniffer.stop()

    def close(self):
        self.stop()
        if self._scan_guard.acquire(timeout=5):  # a running scan notices the new epoch after its current file
            self._scan_guard.release()
        provider = self.provider
        if hasattr(provider, "close"):
            provider.close()

    @property
    def scanning(self) -> bool:
        return self._scan_guard.locked()

    @property
    def watching(self) -> bool:
        return self.sniffer is not None and self.sniffer.is_alive()

    @property
    def is_running(self) -> bool:
        return self.watching

    def ensure_builtin_model(self):
        """Every install path must end with the pinned base model. It is linked from the app bundle (DMG/installer)
        or downloaded once; afterwards the provider is reloaded and the project re-indexed with the real brain."""
        model_path = Path(self.config.get("model_path") or "")
        if self.config.get("brain_provider", "builtin") != "builtin" or str(model_path) != BASE_MODEL_PATH:
            return
        if model_path.exists() or self.model_status:
            return
        threading.Thread(target=self._install_model, args=(model_path,), daemon=True, name="codebone-model-install").start()

    def _install_model(self, dest: Path):
        from . import model_fetch

        self.model_status = "preparing model"
        try:
            model_fetch.install(dest, lambda pct: setattr(self, "model_status", f"downloading {pct}%"))
        except Exception as exc:
            logger.warning("Base model unavailable (regex fallback stays active): %s", exc)
            return
        finally:
            self.model_status = None
        self.reload_provider()
        if self._model_ready() and self.config.is_configured:
            self.rescan_all()  # rows written by the regex fallback are re-analysed automatically

    def reload_provider(self):
        """Call after brain settings change. The old provider is closed once nothing can be using it."""
        new = build_provider(self.config)
        with self._lock:
            old, self.provider = self.provider, new
        if old is not new and hasattr(old, "close"):
            old.close()

    def _model_ready(self) -> bool:
        """True when a real model backs the provider (cheap: never loads or contacts anything)."""
        provider = self.provider
        return not isinstance(provider, FastFallbackProvider) and bool(getattr(provider, "ready", False))

    # ── baseline ────────────────────────────────────────────────────────
    def inspect_baseline(self, project_path: Optional[Path] = None) -> dict:
        """Fast pre-scan assessment that produces a baseline overview:
        counts files, groups languages, determines files needing indexing vs cached,
        and calculates an estimated initial load duration."""
        proj = project_path or self.config.project_path
        empty = {
            "total_files": 0,
            "files_to_index": 0,
            "cached_files": 0,
            "languages": [],
            "languages_summary": "No files",
            "estimated_seconds": 0,
            "estimated_time_str": "0s",
        }
        if not proj or not proj.exists():
            return empty

        try:
            matching_files = list_watched_files(
                proj,
                set(self.config.get("watched_extensions")),
                self.config.get_ignore_dirs(proj),
                load_gitignore_spec(proj),
            )
        except OSError:
            logger.exception("Error during baseline inspection of %s", proj)
            return {**empty, "languages_summary": "Error reading files"}

        total = len(matching_files)
        existing_mtimes = self.storage.get_file_mtimes()

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

            if rel in existing_mtimes and abs(existing_mtimes[rel] - mtime) < 1e-3:
                cached_count += 1
            else:
                files_to_sniff += 1

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

        provider_type = self.config.get("brain_provider", "builtin")
        if not self._model_ready() and provider_type == "builtin":
            sec_per_file = 0.02  # regex fallback until the model is available
        elif provider_type == "builtin":
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
            est_time_str = "~3-5 seconds"
        elif est_seconds < 60:
            est_time_str = f"~{est_seconds} seconds"
        else:
            est_time_str = f"~{round(est_seconds / 60, 1)} minutes"

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

    def stats_snapshot(self) -> dict:
        """Lightweight status/counts payload for the menu bar dashboard (all reads are cached until the next write)."""
        index = self.storage.entity_index()
        proj = self.config.project_path
        return {
            "configured": self.config.is_configured,
            "running": self.is_running,
            "project_path": str(proj) if proj else None,
            "repo_name": proj.name if proj else "None",
            "model_name": self.config.active_model_display_name,
            "sniffing": self.sniffing,
            "model_status": self.model_status,
            "scan_progress": self.scan_progress,
            "baseline": self.last_baseline,
            "last_synced": self.last_synced,
            "file_count": self.storage.file_count(),
            # include_domains=True: table/route/event edges alone are sparse for most projects (a desktop
            # app with no DB or REST routes has almost none), while the live graph already draws domain
            # clusters from the same per-file domain data — excluding them here made the menu bar/
            # notifications report "0 connections" even when the graph itself showed clear clustering.
            "connection_count": len(self.storage.graph_edges(index, include_domains=True)),
            "domain_count": len(index["domains"]),
            "table_count": len(index["tables"]),
            "route_count": len(index["routes"]),
            "event_count": len(index["events"]),
        }

    def reset_map(self):
        """Clear the index. A running scan is told to stop first: it works from a stale snapshot of what exists."""
        self._epoch += 1
        with self._lock:
            self.storage.reset()
        self.last_synced = None

    # ── full scan ───────────────────────────────────────────────────────
    def rescan_all(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        force: bool = False,
        wait: bool = False,
    ) -> tuple[int, int, int]:
        """Full scan of the project folder: sniffs new or modified files (mtime, then SHA-256), re-analyses rows
        written by the regex fallback once a real model is ready, and removes rows of deleted files.

        Only one scan runs at a time; a call made during a scan asks for one more pass afterwards and returns
        (0, 0, 0). wait=True blocks until it can run instead."""
        if not self.config.is_configured:
            return 0, 0, 0
        if wait:
            self._scan_guard.acquire()
        else:
            with self._req_lock:
                if not self._scan_guard.acquire(blocking=False):
                    self._rescan_requested = True
                    return 0, 0, 0
        try:
            while True:
                result = self._rescan_once(on_progress, force)
                with self._req_lock:
                    if not self._rescan_requested:
                        self._scan_guard.release()
                        return result
                    self._rescan_requested = False
                force = False
        except BaseException:
            if self._scan_guard.locked():
                try:
                    self._scan_guard.release()
                except RuntimeError:
                    pass
            raise

    def _rescan_once(self, on_progress, force) -> tuple[int, int, int]:
        project_path = self.config.project_path
        if not project_path or not project_path.exists():
            return 0, 0, 0
        epoch = self._epoch
        self._bind_project()

        unreadable_dirs: list = []
        try:
            matching_files = list_watched_files(
                project_path,
                set(self.config.get("watched_extensions")),
                self.config.get_ignore_dirs(project_path),
                load_gitignore_spec(project_path),
                unreadable_dirs=unreadable_dirs,
            )
            # Big files are analysed last so they never delay the map of everything else
            matching_files.sort(key=lambda p: p.stat().st_size if p.exists() else 0)
        except OSError as exc:
            # An unreadable folder (permissions, unmounted volume) is not an empty project: keep the index
            self.last_error = f"Cannot read project folder: {exc}"
            logger.warning("%s", self.last_error)
            return 0, 0, 0
        if unreadable_dirs:
            self.last_error = (
                f"{len(unreadable_dirs)} folder(s) could not be read and were skipped "
                f"(check macOS Disk Access Settings): {', '.join(unreadable_dirs[:3])}"
                + ("..." if len(unreadable_dirs) > 3 else "")
            )
            logger.warning("%s", self.last_error)
        else:
            self.last_error = None

        total = len(matching_files)
        existing_mtimes = self.storage.get_file_mtimes()
        sources = self.storage.get_file_sources()
        model_ready = self._model_ready()
        active_rel: set[str] = set()
        sniffed = skipped = 0
        start_time = time.time()
        last_report = 0.0
        aborted = False

        self._begin()
        try:
            for idx, path in enumerate(matching_files, start=1):
                if epoch != self._epoch:
                    aborted = True
                    break
                try:
                    rel_path = str(path.relative_to(project_path))
                except ValueError:
                    rel_path = str(path)
                active_rel.add(rel_path)

                now = time.time()
                if now - last_report >= PROGRESS_INTERVAL or idx == total:
                    last_report = now
                    elapsed = max(0.01, now - start_time)
                    eta_sec = max(0, round((total - idx) / (idx / elapsed)))
                    self.scan_progress = {
                        "current": idx,
                        "total": total,
                        "sniffed": sniffed,
                        "skipped": skipped,
                        "pct": int(idx * 100 / max(1, total)),
                        "eta_seconds": eta_sec,
                        "eta_str": f"~{eta_sec}s" if eta_sec < 60 else f"~{round(eta_sec / 60, 1)}m",
                        "current_file": rel_path,
                    }
                    if on_progress:
                        on_progress(idx, total, rel_path)

                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue

                unchanged = rel_path in existing_mtimes and abs(existing_mtimes[rel_path] - mtime) < 1e-3
                stale_regex = model_ready and sources.get(rel_path) == "regex"
                if not force and unchanged and not stale_regex:
                    skipped += 1
                    continue

                try:
                    outcome = self._sniff_file(path, mtime=mtime, force=force or stale_regex)
                except Exception as exc:
                    logger.debug("Tolerated error sniffing %s during rescan: %s", path, exc)
                    continue
                if outcome == "sniffed":
                    sniffed += 1
                else:
                    skipped += 1

            if not aborted:
                # Files under a pruned tree (node_modules, .git, ...) still exist on disk but no longer belong
                # in the index — drop them; everything else is only removed when it is really gone.
                deleted_paths = [p for p in existing_mtimes
                                 if p not in active_rel and (is_pruned_rel(p) or not (project_path / p).exists())]
                if deleted_paths and total == 0:
                    logger.warning("Project lists as empty but %d files are indexed; keeping the index", len(deleted_paths))
                elif deleted_paths:
                    self.storage.remove_files(deleted_paths)
                    logger.info("Cleaned up %d deleted files from storage", len(deleted_paths))
        finally:
            self.scan_progress = None
            self._end()

        logger.info("Rescan %s: %d total, %d sniffed, %d skipped", "aborted" if aborted else "finished", total, sniffed, skipped)
        if not aborted:
            self._maybe_snapshot(force=True)
        return total, sniffed, skipped

    def _maybe_snapshot(self, force: bool = False):
        """Snapshots are full DB copies: write one only if the index changed and the last one is not recent."""
        if not self.config.project_path or self.storage.revision == self._snapshot_revision:
            return
        if not force and time.time() - self._last_snapshot < SNAPSHOT_INTERVAL:
            return
        try:
            self.scans.save_snapshot(
                project_name=self.config.project_path.name,
                project_path=self.config.project_path,
                storage=self.storage,
            )
            self._last_snapshot = time.time()
            self._snapshot_revision = self.storage.revision
        except Exception as exc:
            logger.warning("Failed to auto-save scan snapshot: %s", exc)

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

        deep_provider = BuiltinProvider(model_path=model_path, n_ctx=4096)
        with self._scan_guard:  # no normal scan may run while the provider is swapped
            with self._lock:
                original, self.provider = self.provider, deep_provider
            try:
                self._rescan_requested = False
                return self._rescan_once(on_progress, True)
            finally:
                with self._lock:
                    if self.provider is deep_provider:  # a brain switch during the scan wins
                        self.provider = original
                deep_provider.close()

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

        with self._scan_guard:
            self._begin()
            try:
                self._bind_project()
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
                self._maybe_snapshot(force=True)
                return report
            finally:
                self._end()

    # ── single files and batches ────────────────────────────────────────
    def _rel(self, path: Path) -> Optional[str]:
        """Path relative to the project folder, or None for anything outside it (never index absolute paths)."""
        project_path = self.config.project_path
        if not project_path:
            return None
        for candidate in (path, path.resolve()):
            try:
                return str(candidate.relative_to(project_path))
            except ValueError:
                continue
        return None

    def _handle_change(self, path: Path):
        self._begin()
        try:
            self._sniff_file(path, live=True)
        except Exception as exc:
            logger.debug("Tolerated error sniffing %s: %s", path, exc)
        finally:
            self._end()

    def _sniff_file(self, path: Path, mtime: Optional[float] = None, force: bool = False, live: bool = False) -> str:
        """Analyse one file. Returns "sniffed", "unchanged" (same content) or "skipped" (outside the project or
        not worth overwriting good data). Secret-shaped files (.env, keys, anything below a credential store)
        get a path-only node via _path_only — their content is never read, whatever the extension. A file too
        big to read fully or binary (an image, a compiled binary, an archive, ...) still gets a node in the map
        via _catalog_asset — it just isn't semantically analysed.
        live=True marks a watcher event: a file that stops parsing right after an edit keeps its previous
        analysis for a grace period (it is probably mid-edit)."""
        rel_path = self._rel(path)
        if rel_path is None:
            return "skipped"

        try:
            st = path.stat()
        except OSError:
            return "skipped"
        if mtime is None:
            mtime = st.st_mtime

        # Never read credential-shaped content: secret-looking file names (also behind an innocent
        # symlink) and anything below a credential store (.ssh, secrets, ...) stay path-only.
        real = path.resolve() if path.is_symlink() else path
        if _is_secret_or_junk(real.name) or any(d in GLOBAL_IGNORED_DIRS for d in real.parts):
            return self._path_only(rel_path, mtime)

        if st.st_size > MAX_READ_BYTES:
            return self._catalog_asset(rel_path, path, st.st_size, mtime, force, "oversized")

        try:
            content_bytes = path.read_bytes()
        except OSError:
            return "skipped"
        if b"\0" in content_bytes[:8192]:
            return self._catalog_asset(rel_path, path, st.st_size, mtime, force, "binary")
        code = content_bytes.decode("utf-8", errors="ignore")
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        with self._lock:
            row = self.storage.get_file(rel_path)
            if row and not force and row["content_hash"] == content_hash:
                if abs((row["mtime"] or 0) - mtime) > 1e-3:
                    self.storage.set_mtime(rel_path, mtime)  # touched but identical: refresh, do not re-analyse
                return "unchanged"

            # Mid-edit syntax errors must not destroy the last good analysis. Only for live edits of files we
            # already know, and only for a grace period: JSONC, Python 2 or template files never parse and must
            # not stay frozen forever.
            if live and row and not _parses(path.suffix, code):
                first_seen = self._broken_since.setdefault(rel_path, time.monotonic())
                if time.monotonic() - first_seen < BROKEN_GRACE_SECONDS:
                    logger.debug("Preserving previous analysis of %s (currently unparsable)", rel_path)
                    return "skipped"
            else:
                self._broken_since.pop(rel_path, None)

            provider = self.provider
            model_backed = not isinstance(provider, FastFallbackProvider)
            if row and force and row["source"] == "model" and not (model_backed and self._model_ready()):
                return "skipped"  # never replace model output with regex output

        # Inference (a network call for local-URL and cloud brains) runs without the service lock, so the menu bar
        # thread can switch brains and the watcher can proceed while it is busy.
        try:
            raw_output = provider.sniff(rel_path, code)
            source = getattr(provider, "last_source", "model" if model_backed else "regex")
        except (SyntaxError, ValueError) as exc:
            logger.debug("Tolerated parsing error in %s (preserved previous state): %s", rel_path, exc)
            return "skipped"
        except Exception as exc:
            logger.debug("Non-fatal parsing issue for %s: %s", rel_path, exc)
            return "skipped"

        with self._lock:
            if self._rel(path) != rel_path:  # the project changed while we were analysing
                return "skipped"
            res = self.storage.update_file(rel_path, raw_output, mtime=mtime, content_hash=content_hash, source=source)
        self.last_synced = rel_path
        logger.info(
            "Sniffed %s -> %d tables, %d routes, %d events, %d domains",
            rel_path,
            len(res.get("tables", [])),
            len(res.get("routes", [])),
            len(res.get("events", [])),
            len(res.get("domains", [])),
        )
        return "sniffed"

    def _catalog_asset(self, rel_path: str, path: Path, size: int, mtime: float, force: bool, reason: str) -> str:
        """Gives a non-code file (image, font, archive, compiled binary, oversized file, ...) a node in the map
        without reading or analysing its content: no tables/routes/events, just a category and size so the map
        stays complete. content_hash is a cheap size+mtime fingerprint (not a full read) so a huge or binary
        file is never hashed byte-for-byte just to detect that it hasn't changed."""
        content_hash = f"asset:{size}:{int(mtime)}"
        with self._lock:
            row = self.storage.get_file(rel_path)
            if row and not force and row.get("content_hash") == content_hash:
                return "unchanged"
            category = "oversized" if reason == "oversized" else _asset_category(path)
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
            raw_output = f"TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: Assets\nFLOW: {category} file ({size_str})"
            self.storage.update_file(rel_path, raw_output, mtime=mtime, content_hash=content_hash, source="asset")
        self.last_synced = rel_path
        return "sniffed"

    def _path_only(self, rel_path: str, mtime: float) -> str:
        """A file whose content must never be read (.env, keys, files under credential stores) still gets a
        node in the map: path only, no entities, no content hash."""
        with self._lock:
            row = self.storage.get_file(rel_path)
            if not row or abs((row["mtime"] or 0) - mtime) > 1e-3:
                self.storage.update_file(rel_path, "", mtime=mtime, content_hash="", source="regex")
        return "sniffed"

    def _handle_batch(self, changed: set[Path], deleted: set[Path]):
        """Handles burst changes (e.g. git checkout, branch switch, mass file moves/refactors)."""
        project_path = self.config.project_path
        if not project_path:
            return

        self._begin()
        try:
            hashes = self.storage.get_file_hashes()
            records_by_hash = self.storage.get_records_by_hash()

            # 1. Look at changed files first: identical content that already has an analysis is re-linked, not re-analysed
            genuine_sniff_paths: list[Path] = []
            for p in changed:
                rel = self._rel(p)
                if rel is None or not p.is_file():
                    continue
                try:
                    with open(p, "rb") as fh:
                        content_hash = hashlib.sha256(fh.read(MAX_READ_BYTES)).hexdigest()
                except OSError:
                    continue
                if hashes.get(rel) == content_hash:
                    continue
                prev_records = records_by_hash.get(content_hash)
                if prev_records:
                    rec = dict(prev_records[0])
                    rec["path"] = rel
                    try:
                        rec["mtime"] = p.stat().st_mtime
                    except OSError:
                        pass
                    with self._lock:
                        self.storage.insert_record(rec)
                    logger.info("Re-linked %s via SHA-256 (no analysis needed)", rel)
                    continue
                genuine_sniff_paths.append(p)

            # 2. Then drop rows of files that are really gone (a stale delete must not remove a re-created file)
            deleted_rels = []
            for p in deleted:
                rel = self._rel(p)
                if rel is not None and not p.exists():
                    deleted_rels.append(rel)
            if deleted_rels:
                with self._lock:
                    self.storage.remove_files(deleted_rels)
                logger.info("Batch deleted %d files from storage", len(deleted_rels))

            # 3. Analyse genuine modifications
            if genuine_sniff_paths:
                logger.info("Batch sniffing %d modified/new files", len(genuine_sniff_paths))
                for p in genuine_sniff_paths:
                    try:
                        self._sniff_file(p, live=True)
                    except Exception as exc:
                        self.last_error = str(exc)
                        logger.debug("Tolerated error sniffing file %s in batch: %s", p, exc)

            if len(changed) + len(deleted) >= 8:
                self._maybe_snapshot()
        finally:
            self._end()

    def _handle_delete(self, path: Path):
        rel = self._rel(path)
        if rel is None:
            return
        with self._lock:
            self.storage.remove_file(rel)


ASSET_CATEGORIES = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".ico": "image", ".icns": "image",
    ".svg": "image", ".webp": "image", ".bmp": "image", ".tiff": "image", ".psd": "image",
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video", ".webm": "video",
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".ogg": "audio", ".aac": "audio",
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".7z": "archive", ".rar": "archive",
    ".bz2": "archive", ".xz": "archive", ".iso": "archive", ".dmg": "archive",
    ".gguf": "model weights", ".bin": "model weights", ".safetensors": "model weights", ".onnx": "model weights",
    ".pt": "model weights", ".pth": "model weights", ".pkl": "model weights", ".h5": "model weights", ".tflite": "model weights",
    ".sqlite": "database", ".sqlite3": "database", ".db": "database", ".mdb": "database", ".accdb": "database",
    ".pyc": "compiled", ".pyo": "compiled", ".class": "compiled", ".o": "compiled", ".obj": "compiled",
    ".dylib": "compiled library", ".so": "compiled library", ".dll": "compiled library", ".exe": "executable", ".wasm": "compiled",
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font", ".eot": "font",
    ".pdf": "document", ".doc": "document", ".docx": "document", ".xls": "document", ".xlsx": "document",
    ".ppt": "document", ".pptx": "document",
}


def _asset_category(path: Path) -> str:
    return ASSET_CATEGORIES.get(path.suffix.lower(), "binary")


def _parses(suffix: str, code: str) -> bool:
    """False only for Python/JSON that is provably broken right now (typically mid-edit)."""
    try:
        if suffix == ".py":
            ast.parse(code)
        elif suffix == ".json":
            json.loads(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return True


# Backwards compatibility alias
PugService = CodeBoneService
