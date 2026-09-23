"""macOS filesystem permission checks & Full Disk Access helpers for codebone."""
import logging
import os
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("codebone.permissions")

FULL_DISK_ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


def check_folder_access(path: Path) -> Tuple[bool, str]:
    """Validates that codebone can access, list, and read files in the target directory.
    
    Returns:
        (is_accessible, error_message)
    """
    if not path.exists():
        return False, f"Directory does not exist: {path}"

    if not path.is_dir():
        return False, f"Path is not a directory: {path}"

    try:
        # Attempt to list directory entries
        with os.scandir(path) as it:
            # Try reading first few entries to verify read permissions
            count = 0
            for entry in it:
                count += 1
                if count >= 5:
                    break
        return True, "Access granted"
    except PermissionError as exc:
        msg = (
            f"Permission denied accessing '{path}'. macOS TCC or Full Disk Access required. "
            f"Please grant Full Disk Access to codebone in System Settings."
        )
        logger.warning(msg)
        return False, msg
    except OSError as exc:
        msg = f"Cannot access '{path}': {exc}"
        logger.warning(msg)
        return False, msg


def open_full_disk_access_settings() -> bool:
    """Opens macOS System Settings directly to Privacy & Security -> Full Disk Access."""
    try:
        subprocess.Popen(["open", FULL_DISK_ACCESS_URL])
        logger.info("Opened macOS Full Disk Access settings pane")
        return True
    except Exception as exc:
        logger.error("Failed to open Full Disk Access settings: %s", exc)
        return False
