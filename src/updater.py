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
from . import __version__

CURRENT_VERSION = __version__  # single source of truth: src/__init__.py


def clean_release_notes(text: str) -> str:
    """Plain-text version of a release body for a non-Markdown alert dialog: drops headers' '#', turns
    '-'/'*' bullets into '•', strips bold/link markup and GitHub's own auto-generated boilerplate
    ('## What's Changed', 'Full Changelog: ...', '* ... by @user in <url>')."""
    if not text:
        return ""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if re.match(r"^\*\*full changelog\*\*", line, re.IGNORECASE) or line.lower().startswith("full changelog"):
            continue
        if re.fullmatch(r"[-*_]{3,}", line):  # markdown horizontal rule
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*]\s+", "• ", line)
        line = re.sub(r"\bby @[\w-]+ in https://\S+", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.rstrip()
        if line or lines and lines[-1] != "":
            lines.append(line)
    # collapse runs of blank lines and trailing separators ("---")
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\n?-{3,}\s*$", "", cleaned).strip()
    return cleaned


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
    checksum_url = None
    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if "arm64" in name and name.endswith(".zip"):
            download_url = asset.get("browser_download_url")
            asset_size = asset.get("size", 0)
            sums = [a.get("browser_download_url") for a in data.get("assets", []) if a.get("name", "").lower() == name + ".sha256"]
            checksum_url = sums[0] if sums else None
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
        "release_notes": clean_release_notes(data.get("body", "")),
        "download_url": download_url,
        "checksum_url": checksum_url,
        "asset_size": asset_size,
        "html_url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
    }


MAX_UPDATE_BYTES = 2 * 1024 * 1024 * 1024
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com")


def current_bundle() -> Path:
    """The codebone.app this code is running from (falls back to /Applications for source checkouts)."""
    for parent in Path(__file__).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return Path("/Applications/codebone.app")


def _check_zip_names(zf: zipfile.ZipFile) -> None:
    """Refuse archives that would write outside the extraction directory (zip slip)."""
    for name in zf.namelist():
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts:
            raise RuntimeError(f"Unsafe path in update package: {name!r}")


def _bundle_version(app: Path) -> Optional[str]:
    try:
        import plistlib
        with open(app / "Contents" / "Info.plist", "rb") as f:
            return plistlib.load(f).get("CFBundleShortVersionString")
    except Exception:
        return None


def download_and_install_update(
    download_url: str,
    target_app_path: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    expected_version: Optional[str] = None,
    checksum_url: Optional[str] = None,
) -> bool:
    """Download the release ZIP, verify it, and swap it in for the running bundle.

    The new bundle is fully extracted, checked (structure, version, signature) and copied next to the target
    first; only then are the two renamed, so a failure at any point leaves the working app untouched."""
    from urllib.parse import urlsplit

    parts = urlsplit(download_url)
    if parts.scheme != "https" or (parts.hostname or "") not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError("Update downloads must use HTTPS from GitHub")
    target_path = Path(target_app_path) if target_app_path else current_bundle()
    if not target_path.parent.exists() or not os.access(target_path.parent, os.W_OK):
        # Installing somewhere else would leave the running app behind as a second copy: stop and say why
        raise RuntimeError(f"No permission to replace {target_path}. Move codebone.app to /Applications or ~/Applications and try again.")

    with tempfile.TemporaryDirectory(prefix="codebone_update_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        zip_file = tmp_path / "update.zip"

        if progress_callback:
            progress_callback("Downloading update...")
        logger.info("Downloading codebone update from %s...", download_url)
        req = urllib.request.Request(download_url, headers={"User-Agent": "codebone-updater"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(zip_file, "wb") as out_f:
            length = int(resp.headers.get("Content-Length") or 0)
            if length > MAX_UPDATE_BYTES:
                raise RuntimeError("Update package is unexpectedly large")
            copied = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_UPDATE_BYTES:
                    raise RuntimeError("Update package is unexpectedly large")
                out_f.write(chunk)

        if progress_callback:
            progress_callback("Extracting package...")
        if checksum_url:  # published next to the release asset: <zip>.sha256
            import hashlib
            expected = urllib.request.urlopen(urllib.request.Request(checksum_url, headers={"User-Agent": "codebone-updater"}),
                                              timeout=30).read().decode().split()[0].lower()
            digest = hashlib.sha256()
            with open(zip_file, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError("Update package checksum does not match the published SHA-256")
        else:
            logger.warning("No published checksum for this release; relying on HTTPS and the code signature only")
        with zipfile.ZipFile(zip_file, "r") as zf:
            _check_zip_names(zf)
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        # ditto keeps symlinks and permissions; a plain zipfile extraction turns the bundled Python's symlinks into files
        subprocess.run(["ditto", "-x", "-k", str(zip_file), str(extract_dir)], check=True)
        zip_file.unlink()

        extracted_app = next((i for i in extract_dir.iterdir() if i.is_dir() and i.suffix == ".app"), None)
        if not extracted_app or not (extracted_app / "Contents" / "MacOS" / "codebone").exists():
            raise RuntimeError("Downloaded package does not contain a valid codebone.app bundle.")
        version = _bundle_version(extracted_app)
        if expected_version and (not version or parse_version(version) != parse_version(expected_version)):
            raise RuntimeError(f"Update package is version {version}, expected {expected_version}")

        if progress_callback:
            progress_callback("Verifying signature...")
        subprocess.run(["xattr", "-cr", str(extracted_app)], check=False)
        if subprocess.run(["codesign", "--verify", "--deep", str(extracted_app)], capture_output=True).returncode != 0:
            raise RuntimeError("The downloaded app bundle failed its signature check")

        if progress_callback:
            progress_callback("Replacing application bundle...")
        staged = target_path.with_name(target_path.name + ".new")
        backup = target_path.with_name(target_path.name + ".old")
        for leftover in (staged, backup):
            if leftover.exists():
                shutil.rmtree(leftover)
        subprocess.run(["ditto", str(extracted_app), str(staged)], check=True)  # full copy first: nothing is swapped yet
        try:
            if target_path.exists():
                os.rename(target_path, backup)
            os.rename(staged, target_path)
        except OSError:
            if backup.exists() and not target_path.exists():
                os.rename(backup, target_path)  # roll back
            shutil.rmtree(staged, ignore_errors=True)
            raise
        shutil.rmtree(backup, ignore_errors=True)

        subprocess.run(["xattr", "-cr", str(target_path)], check=False)
        lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
        if os.path.exists(lsregister):
            subprocess.run([lsregister, "-f", str(target_path)], check=False)
        subprocess.run(["touch", str(target_path)], check=False)
        logger.info("Update installed successfully at %s!", target_path)
        return True


def restart_app(app_path: Optional[str] = None):
    """Spawns an independent background process that quits the running instance and opens the app again.
    The path is passed as an argument (never interpolated into the script), so spaces and quotes are safe."""
    app = str(app_path or current_bundle())
    script = 'kill "$2" >/dev/null 2>&1 || true; sleep 1; open "$1"'  # by pid: no pattern matching on the path
    subprocess.Popen(["bash", "-c", script, "codebone-restart", app, str(os.getpid())], start_new_session=True)
