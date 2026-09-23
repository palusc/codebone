"""Battery-aware idle detection — via macOS `pmset -g batt`."""
import logging
import subprocess

logger = logging.getLogger("codebone.battery")


def on_battery_power() -> bool:
    """True if the Mac is running unplugged (not on AC power)."""
    try:
        out = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3
        ).stdout
        return "Battery Power" in out and "AC Power" not in out
    except (OSError, subprocess.SubprocessError):
        return False

