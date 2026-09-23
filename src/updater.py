"""Native macOS In-App Auto-Updater for codebone.

Checks GitHub Releases for new codebone versions, downloads the native
ARM64 ZIP package, verifies codesign integrity, and performs atomic
replacement of the application bundle.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("codebone.updater")

GITHUB_REPO = "palusc/codebone"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CURRENT_VERSION = "1.2.2"


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parses a version string like 'v1.2.0' or '1.2.3-beta' into an integer tuple for comparison."""
    clean = re.sub(r"^[vV]", "", (v_str or "").strip())
    # Extract only the numeric dot-separated prefix
    match = re.match(r"^(\d+(?:\.\d+)*)", clean)
    if not match:
        return (0, 0, 0)
    parts = [int(p) for p in match.group(1).split(".")]
    # Pad to at least 3 parts (major, minor, patch)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_for_updates(current_version: str = CURRENT_VERSION, timeout: int = 8) -> Dict[str, Any]:
    """Queries the GitHub Releases API to see if a newer version of codebone is available.

    Returns:
        dict with keys:
            update_available (bool)
            latest_version (str)
            current_version (str)
            release_name (str)
            release_notes (str)
            download_url (str or None)
            asset_size (int)
            html_url (str)
    """
    req = urllib.request.Request(
        RELEASES_API_URL,
        headers={
            "User-Agent": f"codebone-updater/{current_version}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to check for updates from GitHub: %s", exc)
        return {
            "update_available": False,
            "error": str(exc),
            "current_version": current_version,
            "latest_version": current_version,
            "download_url": None,
        }

    tag_name = data.get("tag_name", "").strip()
    latest_ver_str = re.sub(r"^[vV]", "", tag_name)

    curr_tuple = parse_version(current_version)
    latest_tuple = parse_version(latest_ver_str)

    update_available = latest_tuple > curr_tuple

    # Find the ARM64 ZIP asset
    download_url = None
    asset_size = 0
    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if "arm64" in name and name.endswith(".zip"):
            download_url = asset.get("browser_download_url")
            asset_size = asset.get("size", 0)
            break
        elif name.endswith(".zip") and not download_url:
            download_url = asset.get("browser_download_url")
            asset_size = asset.get("size", 0)

    # Fallback to DMG if zip is not present
    if not download_url:
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".dmg"):
                download_url = asset.get("browser_download_url")
                asset_size = asset.get("size", 0)
                break

    return {
        "update_available": update_available,
        "latest_version": latest_ver_str or current_version,
        "current_version": current_version,
        "release_name": data.get("name", f"codebone v{latest_ver_str}"),
        "release_notes": data.get("body", ""),
        "download_url": download_url,
        "asset_size": asset_size,
        "html_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
    }


def download_and_install_update(
    download_url: str,
    target_app_path: str = "/Applications/codebone.app",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Downloads the release ZIP, extracts it, strips quarantine, signs, and replaces target app bundle."""
    target_path = Path(target_app_path)
    if not target_path.parent.exists():
        target_path = Path.home() / "Applications" / "codebone.app"
        target_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="codebone_update_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        zip_file = tmp_path / "update.zip"

        if progress_callback:
            progress_callback("Downloading update...")
        logger.info("Downloading codebone update from %s...", download_url)

        req = urllib.request.Request(download_url, headers={"User-Agent": "codebone-updater"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(zip_file, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)

        if progress_callback:
            progress_callback("Extracting package...")
        logger.info("Extracting update package to %s...", tmp_dir)
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(tmp_dir)

        # Locate extracted .app bundle
        extracted_app = None
        for item in tmp_path.iterdir():
            if item.is_dir() and item.suffix == ".app":
                extracted_app = item
                break

        if not extracted_app or not (extracted_app / "Contents" / "MacOS" / "codebone").exists():
            raise RuntimeError("Downloaded package does not contain a valid codebone.app bundle.")

        if progress_callback:
            progress_callback("Securing permissions & signatures...")

        # 1. Clean quarantine and unwanted attributes
        subprocess.run(["xattr", "-cr", str(extracted_app)], check=False)

        # 2. Codesign the new bundle
        subprocess.run(
            ["codesign", "--force", "--deep", "-s", "-", str(extracted_app)],
            check=False,
        )

        if progress_callback:
            progress_callback("Replacing application bundle...")
        logger.info("Installing new codebone version into %s...", target_path)

        # 3. Replace target application bundle
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.copytree(extracted_app, target_path, symlinks=True)

        # 4. Final verification and launch services refresh
        subprocess.run(["xattr", "-cr", str(target_path)], check=False)
        subprocess.run(
            ["codesign", "--force", "--deep", "-s", "-", str(target_path)],
            check=False,
        )
        lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
        if os.path.exists(lsregister):
            subprocess.run([lsregister, "-f", str(target_path)], check=False)
        subprocess.run(["touch", str(target_path)], check=False)

        logger.info("Update installed successfully at %s!", target_path)
        return True


def restart_app(app_path: str = "/Applications/codebone.app"):
    """Spawns an independent background process that cleanly quits the running instance and restarts."""
    script = f"""
pkill -f "{app_path}/Contents/MacOS/codebone" >/dev/null 2>&1 || true
sleep 1
open "{app_path}"
"""
    subprocess.Popen(["bash", "-c", script], start_new_session=True)
