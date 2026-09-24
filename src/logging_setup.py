"""File-based logging for codebone background service and macOS app."""
import faulthandler
import logging
import logging.handlers
import sys
import threading
from pathlib import Path

LOG_DIR = Path.home() / "Library" / "Logs" / "codebone"
LOG_FILE = LOG_DIR / "codebone.log"


def configure_logging(level: int = logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on re-entry
    if not root.handlers:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        if sys.stderr.isatty():
            stream_handler = logging.StreamHandler(sys.stderr)
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)

        _capture_crashes(file_handler.stream)

    return LOG_FILE


def _capture_crashes(log_stream):
    """Uncaught exceptions (main thread and worker threads) and native crashes end up in the log instead of vanishing."""
    log = logging.getLogger("codebone.crash")

    def _excepthook(exc_type, exc, tb):
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        log.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    try:
        faulthandler.enable(file=log_stream)
    except Exception:
        pass
