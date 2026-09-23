"""File-based logging for codebone background service and macOS app."""
import logging
import logging.handlers
import sys
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

    return LOG_FILE
