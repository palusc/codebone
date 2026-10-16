"""Native per-user locations shared by the desktop app and MCP bridge."""
import os
import sys
from pathlib import Path


def data_dir(platform=None, environ=None, home=None) -> Path:
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == 'win32':
        return Path(environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local') / 'codebone'
    return home / 'Library' / 'Application Support' / 'codebone'


def log_dir() -> Path:
    if sys.platform == 'win32':
        return data_dir() / 'logs'
    return Path.home() / 'Library' / 'Logs' / 'codebone'


def resource_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
