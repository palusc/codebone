"""CodeBoneService ties together config, brain provider, watcher, storage, and server."""
import ast
import copy
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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



def format_eta(seconds: float | int) -> str:
    """Format an ETA in seconds into a clean human-readable string like ~14s, ~1m 20s, or ~2h 15m."""
    sec = int(round(seconds))
    if sec <= 0:
        return "< 1s"
    if sec < 60:
        return f"~{sec}s"
    mins = sec // 60
    rem_sec = sec % 60
    if mins < 60:
        return f"~{mins}m {rem_sec}s" if rem_sec > 0 else f"~{mins}m"
    hrs = mins // 60
    rem_mins = mins % 60
    return f"~{hrs}h {rem_mins}m" if rem_mins > 0 else f"~{hrs}h"


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
        self._workspace_cache: Optional[tuple] = None  # (cache key, workspace_stats payload)
        self._snapshot_lock = threading.Lock()  # parallel project workers serialize registry updates
        self._parallel_progress_lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

    # ── activity bookkeeping ────────────────────────────────────────────
    @property
    def sniffing(self) -> bool:
        return self._active > 0

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def pause_scan(self):
        """Pause any ongoing scan pass."""
        self._pause_event.clear()
        if self.scan_progress:
            with self._parallel_progress_lock:
                self.scan_progress["paused"] = True

    def resume_scan(self):
        """Resume a paused scan pass."""
        self._pause_event.set()
        if self.scan_progress:
            with self._parallel_progress_lock:
                self.scan_progress["paused"] = False

    def toggle_pause_scan(self) -> bool:
        """Toggle pause/resume state. Returns True if now paused, False if running."""
        if self.is_paused:
            self.resume_scan()
            return False
        else:
            self.pause_scan()
            return True

    def cancel_scan(self):
        """Cancel any ongoing scan pass immediately."""
        self._cancel_requested.set()
        self._epoch += 1
        with self._req_lock:
            self._rescan_requested = False
        self._pause_event.set()  # unblock paused workers so they can terminate cleanly
        self.scan_progress = None

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

    @property
    def model_ready(self) -> bool:
        """Public form of _model_ready() for the menu's status line."""
        return self._model_ready()

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
            "is_paused": self.is_paused,
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

    def workspace_stats(self) -> dict:
        """Per-project node/connection counts for the whole workspace, plus totals.

        The live index only ever holds one project (see _bind_project), so every other folder is counted
        from its rolling scan snapshot — no database is opened unless something actually changed. Only
        folders that exist on disk are reported: an unmounted volume must not show up as an empty project.
        """
        active = self.config.project_path
        snapshots = {s.get("project_path"): s for s in self.scans.list_scans() if s.get("project_path")}
        key = (
            str(active),
            self.storage.revision,  # the active project's counts change on every write
            tuple(sorted((p, m.get("updated_at"), m.get("file_count")) for p, m in snapshots.items())),
        )
        if getattr(self, "_workspace_cache", None) is not None and self._workspace_cache[0] == key:
            return self._workspace_cache[1]

        index = self.storage.entity_index()
        total_nodes = total_edges = 0
        projects: list[dict] = []
        for p in self.config.project_paths:
            if not p.exists():
                continue
            if active and p == active:
                nodes = self.storage.file_count()
                edges = len(self.storage.graph_edges(index, include_domains=True))
            else:
                meta = snapshots.get(str(p))
                db = Path(meta["db_path"]) if meta and meta.get("db_path") else None
                if not db or not db.exists():
                    continue  # never scanned: nothing to report rather than a fake "0 files"
                snap = None
                try:
                    snap = Storage(db, readonly=True)
                    snap_idx = snap.entity_index()
                    nodes = snap.file_count()
                    edges = len(snap.graph_edges(snap_idx, include_domains=True))
                except Exception as exc:
                    logger.warning("Could not read snapshot for %s: %s", p, exc)
                    continue
                finally:
                    if snap is not None:
                        snap.close()
            total_nodes += nodes
            total_edges += edges
            projects.append({
                "name": p.name,
                "path": str(p),
                "active": bool(active and p == active),
                "nodes": nodes,
                "connections": edges,
            })

        payload = {"projects": projects, "total_nodes": total_nodes, "total_connections": total_edges}
        self._workspace_cache = (key, payload)
        return payload

    def resolve_workspace_project(self, project: str | Path | None = None) -> Path:
        """Resolve an optional menu/API project selector strictly inside the configured workspace."""
        if project is None or not str(project).strip():
            active = self.config.project_path
            if not active:
                raise FileNotFoundError("No active project")
            return active
        raw = str(project).strip()
        workspace = [p for p in self.config.project_paths if p.exists()]
        try:
            candidate = Path(raw).expanduser().resolve()
        except OSError:
            candidate = Path(raw)
        exact = [p for p in workspace if p == candidate]
        if exact:
            return exact[0]
        named = [p for p in workspace if p.name.casefold() == raw.casefold()]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise ValueError(f"Project name '{raw}' is ambiguous; use its full path")
        raise FileNotFoundError(f"No workspace project matches '{raw}'")

    def project_tldr(self, project: str | Path | None = None) -> dict:
        """Return a short whole-project explanation from the live index or the project's snapshot."""
        target = self.resolve_workspace_project(project)
        storage = self.storage if target == self.config.project_path else None
        close_after = False
        if storage is None:
            snapshot = self._snapshot_for_project(target)
            if not snapshot:
                raise FileNotFoundError(f"'{target.name}' has not been indexed yet")
            storage = Storage(Path(snapshot["db_path"]), readonly=True)
            close_after = True
        try:
            # TLDR is a view over the already-built project index. It does not open or summarize individual
            # source documents on demand.
            files = storage.all_files()
            index = storage.entity_index()
            if not files:
                raise ValueError(f"'{target.name}' has no indexed files")
            text = self.provider.project_tldr(target.name, files, index)
            return {
                "project": target.name,
                "project_path": str(target),
                "file_count": len(files),
                "text": text,
            }
        finally:
            if close_after:
                storage.close()

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
            self._cancel_requested.clear()
            self._pause_event.set()
            while True:
                result = self._rescan_once(on_progress, force)
                if self._cancel_requested.is_set():
                    self._scan_guard.release()
                    return result
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

    def scan_all_projects(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[dict]:
        """Scan every workspace folder concurrently into isolated databases.

        Workers share the configured brain but never the live SQLite connection. Each completed database is
        published as that project's rolling snapshot, then the project selected by the user is restored into
        the live index. A project switch during the batch therefore wins and no worker can overwrite another
        project's rows.
        """
        projects = [p for p in self.config.project_paths if p.exists()]
        if not projects:
            return []

        with self._req_lock:
            if not self._scan_guard.acquire(blocking=False):
                self._rescan_requested = True
                return []
        self._cancel_requested.clear()
        self._pause_event.set()
        self._begin()
        run_requested_pass = False
        try:
            results = self._scan_projects_parallel(projects, on_progress)
            if self._cancel_requested.is_set():
                return results
            selected = self.config.project_path  # a menu/MCP switch during the scan wins
            completed = {r["project_path"] for r in results if not r.get("error")}
            if selected and str(selected) in completed:
                self._restore_snapshot_to_live(selected)
            self._workspace_cache = None
            errors = [f"{Path(r['project_path']).name}: {r['error']}" for r in results if r.get("error")]
            self.last_error = "; ".join(errors) if errors else None
            return results
        finally:
            with self._parallel_progress_lock:
                self.scan_progress = None
            self._end()
            with self._req_lock:
                run_requested_pass = self._rescan_requested and not self._cancel_requested.is_set()
                self._rescan_requested = False
                self._scan_guard.release()
            if run_requested_pass and self.config.is_configured:
                # Preserve rescan_all's "one more pass" contract when a watcher/API request arrives while
                # the workspace batch owns the scan guard.
                self.rescan_all(wait=True)

    def scan_project(
        self,
        project: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """Scan one workspace project in isolation without temporarily changing the active project."""
        project = Path(project).expanduser().resolve()
        if not project.exists():
            raise FileNotFoundError(f"Project folder not found: {project}")
        self.config.add_project_path(str(project))

        self._scan_guard.acquire()
        self._cancel_requested.clear()
        self._pause_event.set()
        self._begin()
        try:
            res_list = self._scan_projects_parallel([project], on_progress)
            if not res_list:
                return {"project_path": str(project), "total": 0, "sniffed": 0, "skipped": 0}
            result = res_list[0]
            if self._cancel_requested.is_set():
                return result
            if result.get("error"):
                raise RuntimeError(result["error"])
            if self.config.project_path == project:
                self._restore_snapshot_to_live(project)
            self._workspace_cache = None
            return result
        finally:
            with self._parallel_progress_lock:
                self.scan_progress = None
            self._end()
            self._scan_guard.release()

    def _scan_projects_parallel(
        self,
        projects: list[Path],
        on_progress: Optional[Callable[[int, int, str], None]],
    ) -> list[dict]:
        parallel_start = time.time()
        progress: dict[str, dict] = {}
        total_paused_time = 0.0
        paused_start = None

        def report(project: Path, current: int, total: int, current_file: str):
            nonlocal paused_start, total_paused_time
            now = time.time()
            if self.is_paused:
                if paused_start is None:
                    paused_start = now
            else:
                if paused_start is not None:
                    total_paused_time += max(0.0, now - paused_start)
                    paused_start = None

            with self._parallel_progress_lock:
                progress[str(project)] = {
                    "current": current,
                    "total": total,
                    "current_file": current_file,
                }
                done = sum(p["current"] for p in progress.values())
                grand_total = sum(p["total"] for p in progress.values())
                elapsed = max(0.01, (now - parallel_start) - total_paused_time)
                rate = done / elapsed if elapsed > 0 else 1.0
                eta_sec = max(0, round((grand_total - done) / rate)) if grand_total > done and rate > 0 else 0
                eta_str = format_eta(eta_sec)
                self.scan_progress = {
                    "current": done,
                    "total": grand_total,
                    "pct": int(done * 100 / max(1, grand_total)),
                    "eta_seconds": eta_sec,
                    "eta_str": eta_str,
                    "current_file": current_file,
                    "project": f"{len(progress)}/{len(projects)} projects",
                    "projects": {Path(k).name: dict(v) for k, v in progress.items()},
                    "paused": self.is_paused,
                }
            if on_progress:
                on_progress(done, grand_total, current_file)

        max_workers = min(4, len(projects))
        results_by_path: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="codebone-project") as pool:
            futures = {
                pool.submit(
                    self._scan_project_isolated,
                    project,
                    lambda cur, tot, name, p=project: report(p, cur, tot, name),
                ): project
                for project in projects
            }
            for future in as_completed(futures):
                if self._cancel_requested.is_set():
                    for f in futures:
                        f.cancel()
                    break
                project = futures[future]
                try:
                    results_by_path[str(project)] = future.result()
                except Exception as exc:
                    logger.exception("Parallel project scan failed for %s", project)
                    results_by_path[str(project)] = {
                        "project_path": str(project),
                        "total": 0,
                        "sniffed": 0,
                        "skipped": 0,
                        "error": str(exc),
                    }
        return [results_by_path.get(str(p), {"project_path": str(p), "total": 0, "sniffed": 0, "skipped": 0}) for p in projects]

    def _scan_project_isolated(
        self,
        project: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """Build one project's index in a private SQLite database, then publish its rolling snapshot."""
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".parallel-scan-", dir=self.config.config_dir) as tmp:
            worker_config = Config(Path(tmp) / "config.json")
            worker_config.data = copy.deepcopy(self.config.data)
            worker_config.data["project_path"] = str(project)
            worker_config.data["project_paths"] = [str(project)]
            worker_config.save()

            worker = CodeBoneService(worker_config)
            worker._cancel_requested = self._cancel_requested
            worker._pause_event = self._pause_event
            worker_owns_provider = True
            # Cloud/local providers are cheap and carry mutable request state, so each worker keeps its own.
            # The built-in model is hundreds of MB and already protects llama.cpp with a generation lock;
            # it must be shared instead of loaded once per project. Exact fallback instances can be cloned,
            # while custom Provider subclasses used by integrations/tests stay shared.
            if type(self.provider) is FastFallbackProvider:
                unused_provider = worker.provider
                worker.provider = FastFallbackProvider()
                if hasattr(unused_provider, "close"):
                    unused_provider.close()
            elif self.config.get("brain_provider", "builtin") not in ("cloud", "local_url"):
                unused_provider = worker.provider
                worker.provider = self.provider
                worker_owns_provider = False
                if unused_provider is not self.provider and hasattr(unused_provider, "close"):
                    unused_provider.close()
            try:
                total, sniffed, skipped = worker.rescan_all(on_progress=on_progress, wait=True)
                if not self._cancel_requested.is_set():
                    with self._snapshot_lock:
                        self.scans.save_snapshot(project.name, project, worker.storage)
                        self.config.add_recent_scanned_project(str(project))
                result = {
                    "project_path": str(project),
                    "total": total,
                    "sniffed": sniffed,
                    "skipped": skipped,
                }
                if worker.last_error:
                    result["error"] = worker.last_error
                return result
            finally:
                worker.stop()
                if worker_owns_provider and hasattr(worker.provider, "close"):
                    worker.provider.close()
                worker.storage.close()

    def _snapshot_for_project(self, project: Path) -> Optional[dict]:
        target = str(Path(project).expanduser().resolve())
        return next((s for s in self.scans.list_scans() if s.get("project_path") == target), None)

    def _restore_snapshot_to_live(self, project: Path):
        snapshot = self._snapshot_for_project(project)
        if not snapshot:
            return
        self.config.set("project_path", str(project))
        self.stop()
        self.storage.restore_from(Path(snapshot["db_path"]))
        self.start(auto_scan=False)

    def activate_project(self, project: Path):
        """Switch the live map and watcher to an already-scanned workspace project without rescanning it."""
        target = Path(project).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError(f"Project folder not found: {target}")
        snapshot = self._snapshot_for_project(target)
        if not snapshot:
            raise FileNotFoundError(f"'{target.name}' has not been indexed yet")
        if self.config.project_path == target and self.watching:
            return

        self.stop()
        if not self._scan_guard.acquire(timeout=5):
            raise RuntimeError("A project scan is still finishing. Try again in a moment.")
        try:
            self.config.add_project_path(str(target))
            self.config.set("project_path", str(target))
            self.storage.restore_from(Path(snapshot["db_path"]))
            self._workspace_cache = None
        finally:
            self._scan_guard.release()
        self.start(auto_scan=False)
        self.last_error = None

    def _restore_project(self, project: Path):
        """Makes project active again from its rolling snapshot instead of rescanning it. Falls back to a
        full scan when no snapshot exists (first run after adding the folder to the workspace)."""
        self.config.set("project_path", str(project))
        self.start(auto_scan=False)
        matching = self.scans.find_matching_scan(project)
        if matching:
            try:
                self.adopt_scan(matching["id"])
                return
            except Exception as exc:
                logger.warning("Snapshot restore for %s failed, rescanning instead: %s", project, exc)
        self.rescan_all(wait=True)

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
        total_paused_time = 0.0
        last_report = 0.0
        aborted = False

        self._begin()
        try:
            for idx, path in enumerate(matching_files, start=1):
                if epoch != self._epoch or self._cancel_requested.is_set():
                    aborted = True
                    break

                # Handle scan pause
                paused_start = None
                while not self._pause_event.is_set():
                    if epoch != self._epoch or self._cancel_requested.is_set():
                        aborted = True
                        break
                    if paused_start is None:
                        paused_start = time.time()
                        with self._parallel_progress_lock:
                            if self.scan_progress:
                                self.scan_progress["paused"] = True
                        if on_progress:
                            on_progress(idx, total, f"[Paused] {path.name}")
                    time.sleep(0.1)

                if paused_start is not None:
                    total_paused_time += max(0.0, time.time() - paused_start)
                    with self._parallel_progress_lock:
                        if self.scan_progress:
                            self.scan_progress["paused"] = False

                if aborted:
                    break

                try:
                    rel_path = str(path.relative_to(project_path))
                except ValueError:
                    rel_path = str(path)
                active_rel.add(rel_path)

                now = time.time()
                if now - last_report >= PROGRESS_INTERVAL or idx == total:
                    last_report = now
                    elapsed = max(0.01, (now - start_time) - total_paused_time)
                    rate = idx / elapsed
                    eta_sec = max(0, round((total - idx) / rate)) if total > idx else 0
                    eta_str = format_eta(eta_sec)
                    with self._parallel_progress_lock:
                        self.scan_progress = {
                            "current": idx,
                            "total": total,
                            "sniffed": sniffed,
                            "skipped": skipped,
                            "pct": int(idx * 100 / max(1, total)),
                            "eta_seconds": eta_sec,
                            "eta_str": eta_str,
                            "current_file": rel_path,
                            # Which workspace folder this pass belongs to: the menu may be showing another
                            # project while a multi-project scan runs.
                            "project": project_path.name,
                            "paused": self.is_paused,
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
            with self._parallel_progress_lock:
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
            self.config.add_recent_scanned_project(str(self.config.project_path))
            self._last_snapshot = time.time()
            self._snapshot_revision = self.storage.revision
        except Exception as exc:
            logger.warning("Failed to auto-save scan snapshot: %s", exc)

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
            if row and force and row["source"] in ("model", "hybrid") and not (model_backed and self._model_ready()):
                return "skipped"  # never replace model/hybrid output with regex output

        # Inference (a network call for local-URL and cloud brains) runs without the service lock, so the menu bar
        # thread can switch brains and the watcher can proceed while it is busy.
        try:
            raw_output = provider.sniff(rel_path, code)
            source = getattr(provider, "last_source", "hybrid" if model_backed else "regex")
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
