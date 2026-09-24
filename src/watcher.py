"""The 'Sniffer' — watches the project folder and sniffs changed files with burst protection."""
import logging
import threading
import time
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
    """Collects filesystem events and flushes them as one batch.

    One worker thread owns all timing: a batch is flushed once events stopped for the debounce interval, or after
    MAX_WAIT_FACTOR x debounce at the latest, so a steady stream of writes (a build, a sync tool) cannot starve
    indexing forever. Deletions are recognised by name alone, since the file no longer exists."""

    MAX_WAIT_FACTOR = 10

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
        self._first_event = 0.0
        self._last_event = 0.0
        self._delay = DEBOUNCE_SECONDS
        self._stopped = False
        self._cv = threading.Condition()
        self._worker = threading.Thread(target=self._run, daemon=True, name="codebone-debounce")
        self._worker.start()

    def _is_watched(self, path: str, check_exists: bool = True) -> bool:
        return is_watched_file(
            Path(path),
            extensions=self.extensions,
            ignore_dirs=self.ignore_dirs,
            gitignore_spec=self.gitignore_spec,
            project_path=self.project_path,
            check_exists=check_exists,
        )

    def _record(self, changed: Optional[Path] = None, deleted: Optional[Path] = None):
        with self._cv:
            if changed is not None:
                self._changed.add(changed)
                self._deleted.discard(changed)
            if deleted is not None:
                self._deleted.add(deleted)
                self._changed.discard(deleted)
            now = time.monotonic()
            if not self._first_event:
                self._first_event = now
            self._last_event = now
            self._delay = DEBOUNCE_SECONDS_ON_BATTERY if on_battery_power() else DEBOUNCE_SECONDS
            self._cv.notify()

    def _run(self):
        while True:
            with self._cv:
                while not self._stopped and not self._first_event:
                    self._cv.wait()
                if self._stopped:
                    return
                due = min(self._last_event + self._delay, self._first_event + self._delay * self.MAX_WAIT_FACTOR)
                remaining = due - time.monotonic()
                if remaining > 0:
                    self._cv.wait(remaining)
                    continue
                changed, deleted = set(self._changed), set(self._deleted)
                self._changed.clear()
                self._deleted.clear()
                self._first_event = 0.0
            self._dispatch(changed, deleted)

    def _dispatch(self, changed: set[Path], deleted: set[Path]):
        if not changed and not deleted:
            return
        if self.on_batch:
            try:
                self.on_batch(changed, deleted)
            except Exception:
                logger.exception("Error in batch change handler")
            return
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

    def close(self):
        with self._cv:
            self._stopped = True
            self._cv.notify_all()
        self._worker.join(timeout=2)

    def on_modified(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            self._record(changed=Path(event.src_path))

    def on_created(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            self._record(changed=Path(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory and self._is_watched(event.src_path, check_exists=False):
            self._record(deleted=Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._is_watched(event.src_path, check_exists=False):
            self._record(deleted=Path(event.src_path))
        if self._is_watched(event.dest_path):
            self._record(changed=Path(event.dest_path))


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
        self._gitignore_spec = load_gitignore_spec(self.project_path)
        self._args = (on_change, on_delete, set(extensions), set(ignore_dirs), on_batch)
        self.handler: Optional[_SnifferHandler] = None
        self.observer = Observer()

    def start(self):
        if self.handler is not None:
            return  # already running: scheduling twice makes FSEvents refuse the second emitter
        on_change, on_delete, extensions, ignore_dirs, on_batch = self._args
        self.handler = _SnifferHandler(
            on_change=on_change,
            on_delete=on_delete,
            extensions=extensions,
            ignore_dirs=ignore_dirs,
            on_batch=on_batch,
            project_path=self.project_path,
            gitignore_spec=self._gitignore_spec,
        )
        self.observer.schedule(self.handler, str(self.project_path), recursive=True)
        self.observer.start()
        logger.info("Sniffer watching %s", self.project_path)

    def is_alive(self) -> bool:
        return self.observer is not None and self.observer.is_alive()

    def stop(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)
        if self.handler is not None:
            self.handler.close()
