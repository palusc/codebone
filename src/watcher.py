"""The 'Sniffer' — watches the project folder and sniffs changed files."""
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .battery import on_battery_power

logger = logging.getLogger("pug.watcher")

DEBOUNCE_SECONDS = 0.75
DEBOUNCE_SECONDS_ON_BATTERY = 2.5


class _SnifferHandler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[Path], None], on_delete: Callable[[Path], None],
                 extensions: set[str], ignore_dirs: set[str]):
        self.on_change = on_change
        self.on_delete = on_delete
        self.extensions = extensions
        self.ignore_dirs = ignore_dirs
        self._pending: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _is_watched(self, path: str) -> bool:
        p = Path(path)
        if p.suffix not in self.extensions:
            return False
        if any(part in self.ignore_dirs for part in p.parts):
            return False
        return True

    def _debounced(self, path: Path, callback: Callable[[Path], None]):
        key = str(path)
        delay = DEBOUNCE_SECONDS_ON_BATTERY if on_battery_power() else DEBOUNCE_SECONDS
        with self._lock:
            existing = self._pending.get(key)
            if existing:
                existing.cancel()
            timer = threading.Timer(delay, lambda: callback(path))
            timer.daemon = True
            self._pending[key] = timer
            timer.start()

    def on_modified(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            self._debounced(Path(event.src_path), self.on_change)

    def on_created(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            self._debounced(Path(event.src_path), self.on_change)

    def on_deleted(self, event):
        if not event.is_directory and self._is_watched(event.src_path):
            self.on_delete(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            if self._is_watched(event.src_path):
                self.on_delete(Path(event.src_path))
            if self._is_watched(event.dest_path):
                self._debounced(Path(event.dest_path), self.on_change)


class Sniffer:
    def __init__(self, project_path: Path, extensions: list[str], ignore_dirs: list[str],
                 on_change: Callable[[Path], None], on_delete: Callable[[Path], None]):
        self.project_path = project_path
        self.handler = _SnifferHandler(
            on_change, on_delete, set(extensions), set(ignore_dirs)
        )
        self.observer = Observer()

    def start(self):
        self.observer.schedule(self.handler, str(self.project_path), recursive=True)
        self.observer.start()
        logger.info("Sniffer watching %s", self.project_path)

    def stop(self):
        self.observer.stop()
        self.observer.join(timeout=5)
