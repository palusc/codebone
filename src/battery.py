"""Battery-aware idle detection via macOS `pmset -g batt`."""
import logging
import subprocess
import threading
import time

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
            out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
            _cached_value = "Battery Power" in out and "AC Power" not in out
        except (OSError, subprocess.SubprocessError):
            _cached_value = False
        _cached_at = now
        return _cached_value
