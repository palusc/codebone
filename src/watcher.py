"""The 'Sniffer' — watches the project folder and sniffs changed files with burst protection."""
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .battery import on_battery_power
from .config import is_watched_file, load_gitignore_spec

logger = logging.getLogger("codebone.watcher")

DEBOUNCE_SECONDS = 0.5
DEBOUNCE_SECONDS_ON_BATTERY = 15.0


class _SnifferHandler(FileSystemEventHandler):
    def __init__(
        self,
        on_change: Callable[[Path], None],
        on_delete: Callable[[Path], None],
        extensions: set[str],
        ignore_dirs: set[str],
        on_batch: Optional[Callable[[set[Path], set[Path]], None]] = None,
        project_path: Optional[Path] = None,
        gitignore_spec: Optional[object] = None,
    ):
        self.on_change = on_change
        self.on_delete = on_delete
        self.on_batch = on_batch
        self.extensions = extensions
        self.ignore_dirs = ignore_dirs
        self.project_path = project_path
        self.gitignore_spec = gitignore_spec
        self._changed: set[Path] = set()
        self._deleted: set[Path] = set()
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def _is_watched(self, path: str) -> bool:
        p = Path(path)
        return is_watched_file(
            p,
            extensions=self.extensions,
            ignore_dirs=self.ignore_dirs,
            gitignore_spec=self.gitignore_spec,
            project_path=self.project_path,
        )

    def _schedule_batch(self):
        delay = DEBOUNCE_SECONDS_ON_BATTERY if on_battery_power() else DEBOUNCE_SECONDS
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(delay, self._flush_batch)
            self._timer.daemon = True
            self._timer.start()

    def _flush_batch(self):
        with self._lock:
            changed = set(self._changed)
            deleted = set(self._deleted)
            self._changed.clear()
            self._deleted.clear()
            self._timer = None

        if not changed and not deleted:
            return

        if self.on_batch:
            try:
                self.on_batch(changed, deleted)
            except Exception:
                logger.exception("Error in batch change handler")
        else:
            for p in deleted:
                try:
                    self.on_delete(p)
                except Exception:
                    logger.exception("Error in delete handler for %s", p)
            for p in changed:
                try:
                    self.on_change(p)
                except Exception:
                    logger.exception("Error in change handler for %s", p)

    def on_modified(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            p = Path(event.src_path)
            with self._lock:
                self._changed.add(p)
                self._deleted.discard(p)
            self._schedule_batch()

    def on_created(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            p = Path(event.src_path)
            with self._lock:
                self._changed.add(p)
                self._deleted.discard(p)
            self._schedule_batch()

    def on_deleted(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            p = Path(event.src_path)
            with self._lock:
                self._deleted.add(p)
                self._changed.discard(p)
            self._schedule_batch()

    def on_moved(self, event):
        if not event.is_directory:
            src = Path(event.src_path)
            dest = Path(event.dest_path)
            with self._lock:
                if self._is_watched(event.src_path):
                    self._deleted.add(src)
                    self._changed.discard(src)
                if self._is_watched(event.dest_path):
                    self._changed.add(dest)
                    self._deleted.discard(dest)
            self._schedule_batch()


class Sniffer:
    def __init__(
        self,
        project_path: Path,
        extensions: list[str],
        ignore_dirs: list[str],
        on_change: Callable[[Path], None],
        on_delete: Callable[[Path], None],
        on_batch: Optional[Callable[[set[Path], set[Path]], None]] = None,
    ):
        self.project_path = project_path
        gitignore_spec = load_gitignore_spec(self.project_path)
        self.handler = _SnifferHandler(
            on_change=on_change,
            on_delete=on_delete,
            extensions=set(extensions),
            ignore_dirs=set(ignore_dirs),
            on_batch=on_batch,
            project_path=self.project_path,
            gitignore_spec=gitignore_spec,
        )
        self.observer = Observer()

    def start(self):
        self.observer.schedule(self.handler, str(self.project_path), recursive=True)
        self.observer.start()
        logger.info("Sniffer watching %s", self.project_path)

    def is_alive(self) -> bool:
        return self.observer is not None and self.observer.is_alive()

    def stop(self):
        self.observer.stop()
        self.observer.join(timeout=5)
