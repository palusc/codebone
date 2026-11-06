"""Native per-user locations shared by the desktop app and MCP bridge."""
import sys
from pathlib import Path


def data_dir(platform=None, environ=None, home=None) -> Path:
    home = Path.home() if home is None else Path(home)
    return home / 'Library' / 'Application Support' / 'codebone'


def log_dir() -> Path:
    return Path.home() / 'Library' / 'Logs' / 'codebone'


def resource_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
