"""macOS filesystem permission checks & Full Disk Access helpers for codebone."""
import logging
import os
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("codebone.permissions")

FULL_DISK_ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


def trigger_full_disk_access_probe():
    """Probes protected macOS directories to register codebone with the TCC Full Disk Access subsystem.

    When an application touches protected paths (e.g. Safari tabs or TCC records), macOS registers
    its bundle identifier in the Full Disk Access list in System Settings so the user can easily toggle it ON.
    """
    candidates = [
        Path.home() / "Library" / "Safari" / "CloudTabs.db",
        Path.home() / "Library" / "Safari" / "Bookmarks.plist",
        Path.home() / "Library" / "Mail",
        Path("/Library/Application Support/com.apple.TCC/TCC.db"),
    ]
    for p in candidates:
        try:
            if p.exists():
                _ = p.stat()
        except Exception:
            pass


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
    trigger_full_disk_access_probe()
    try:
        subprocess.Popen(["open", FULL_DISK_ACCESS_URL])
        logger.info("Opened macOS Full Disk Access settings pane")
        return True
    except Exception as exc:
        logger.error("Failed to open Full Disk Access settings: %s", exc)
        return False


def reveal_codebone_in_finder() -> bool:
    """Reveals the codebone.app bundle in Finder for easy drag-and-drop into System Settings."""
    candidates = [
        Path("/Applications/codebone.app"),
        Path.home() / "Applications" / "codebone.app",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target:
        try:
            subprocess.Popen(["open", "-R", str(target)])
            logger.info("Revealed %s in Finder", target)
            return True
        except Exception as exc:
            logger.error("Failed to reveal codebone in Finder: %s", exc)
    return False
