"""Battery-aware idle detection via macOS `pmset -g batt`."""
import logging
import subprocess
import threading
import time
import sys

logger = logging.getLogger("codebone.battery")

_CACHE_SECONDS = 30.0
_lock = threading.Lock()
_cached_at = 0.0
_cached_value = False


def on_battery_power() -> bool:
    """True if the Mac is running unplugged. The answer is cached for 30 s: pmset costs ~17 ms per call and this
    is asked once per debounce decision, which used to mean once per filesystem event."""
    global _cached_at, _cached_value
    with _lock:
        now = time.monotonic()
        if now - _cached_at < _CACHE_SECONDS:
            return _cached_value
        try:
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes
                class PowerStatus(ctypes.Structure):
                    _fields_ = [("ac", wintypes.BYTE), ("flags", wintypes.BYTE),
                                ("percent", wintypes.BYTE), ("reserved", wintypes.BYTE),
                                ("life", wintypes.DWORD), ("full_life", wintypes.DWORD)]
                status = PowerStatus()
                _cached_value = bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))) and status.ac == 0
            else:
                out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
                _cached_value = "Battery Power" in out and "AC Power" not in out
        except (OSError, subprocess.SubprocessError):
            _cached_value = False
        _cached_at = now
        return _cached_value
