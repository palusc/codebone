"""Guards that every install path (DMG, install.sh, brew, npm bridge) ships the same versions."""
import json
import re
from pathlib import Path

from src import __version__, config, updater

ROOT = Path(__file__).resolve().parents[1]


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def test_version_is_the_same_everywhere():
    assert updater.CURRENT_VERSION == __version__
    assert json.loads((ROOT / "package.json").read_text())["version"] == __version__
    assert f"version-{__version__}-" in (ROOT / "README.md").read_text()
    assert f"/v{__version__}/" in (ROOT / "Formula" / "codebone.rb").read_text()
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text()


def test_every_requirement_is_pinned_in_the_lock():
    pins = {}
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        name, _, ver = line.partition("==")
        assert ver, f"unpinned line in requirements.lock: {line!r}"
        pins[_norm(name)] = ver
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)", line.strip())
        if m and not line.strip().startswith("#"):
            assert _norm(m.group(1)) in pins, f"{m.group(1)} missing from requirements.lock"


def test_model_is_pinned_by_revision_and_checksum():
    assert re.search(r"/resolve/[0-9a-f]{40}/", config.BASE_MODEL_URL)
    assert re.fullmatch(r"[0-9a-f]{64}", config.BASE_MODEL_SHA256)


def test_installers_share_the_single_bundle_recipe():
    assert "build_bundle.sh" in (ROOT / "install.sh").read_text()
    assert "build_bundle.sh" in (ROOT / "scripts" / "build_dmg.sh").read_text()
    assert not (ROOT / "setup.py").exists()  # a py2app path would build a different app
    assert not (ROOT / "scripts" / "build_uninstaller.sh").exists()  # uninstalling is done in-app (src/uninstall.py)
