"""The one place that knows how to obtain the base GGUF model.

Used by the app (first launch), scripts/download_model.py (installer, DMG build) so all install paths end up
with byte-identical models. Order: bundled copy inside the .app (symlink, no extra disk), else pinned download.
"""
import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .config import BASE_MODEL_FILE, BASE_MODEL_SHA256, BASE_MODEL_URL

BUNDLED_MODEL = Path(__file__).resolve().parents[2] / "models" / BASE_MODEL_FILE  # <app>/Contents/Resources/models


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid(path: Path) -> bool:
    return path.exists() and sha256_of(path) == BASE_MODEL_SHA256


def download(dest: Path, progress: Optional[Callable[[int], None]] = None) -> None:
    """Download to dest (atomic). Raises on network error or checksum mismatch."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")

    def hook(blocks, bsize, total):
        if progress and total > 0:
            progress(min(100, int(blocks * bsize * 100 / total)))

    try:
        urllib.request.urlretrieve(BASE_MODEL_URL, tmp, reporthook=hook)
        if sha256_of(tmp) != BASE_MODEL_SHA256:
            raise OSError("checksum mismatch for downloaded model")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def install(dest: Path, progress: Optional[Callable[[int], None]] = None) -> str:
    """Make dest a valid model. Returns "present", "linked" (from the app bundle) or "downloaded"."""
    if is_valid(dest):
        return "present"
    if dest.is_symlink() or dest.exists():
        dest.unlink()  # dangling link (app moved/deleted) or corrupt partial file
    if BUNDLED_MODEL.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(BUNDLED_MODEL)
        return "linked"
    download(dest, progress)
    return "downloaded"
