"""Guards that every install path (DMG, install.sh, brew, npm bridge) ships the same versions."""
import json
import re
from pathlib import Path

import pytest

from scripts.npm_version import npm_version
from src import __version__, config, updater

ROOT = Path(__file__).resolve().parents[1]


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def test_version_is_the_same_everywhere():
    assert updater.CURRENT_VERSION == __version__
    assert json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"] == npm_version(__version__)
    assert f"version-{__version__}-" in (ROOT / "README.md").read_text(encoding="utf-8")
    # Homebrew stays on the last built archive until release CI computes a new checksum.
    formula = (ROOT / "Formula" / "codebone.rb").read_text(encoding="utf-8")
    assert re.search(r"/v[0-9][^/]+/codebone-macos-arm64.zip", formula)
    assert re.search(r'sha256 "[0-9a-f]{64}"', formula)
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package['name'] == 'cb1'
    assert package['bin'] == {'cb1': 'bin/cbone.js', 'cbone': 'bin/cbone.js'}
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_every_requirement_is_pinned_in_the_lock():
    pins = {}
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        name, _, ver = line.partition("==")
        assert ver, f"unpinned line in requirements.lock: {line!r}"
        pins[_norm(name)] = ver
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)", line.strip())
        if m and not line.strip().startswith("#"):
            assert _norm(m.group(1)) in pins, f"{m.group(1)} missing from requirements.lock"


def test_model_is_pinned_by_revision_and_checksum():
    assert re.search(r"/resolve/[0-9a-f]{40}/", config.BASE_MODEL_URL)
    assert re.fullmatch(r"[0-9a-f]{64}", config.BASE_MODEL_SHA256)


def test_installers_share_the_single_bundle_recipe():
    assert "build_bundle.sh" in (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "build_bundle.sh" in (ROOT / "scripts" / "build_dmg.sh").read_text(encoding="utf-8")
    assert not (ROOT / "setup.py").exists()  # a py2app path would build a different app
    assert not (ROOT / "scripts" / "build_uninstaller.sh").exists()  # uninstalling is done in-app (src/uninstall.py)


@pytest.mark.parametrize("app,expected", [("1.8a", "1.8.0-a"), ("1.8b", "1.8.0-b"), ("1.8", "1.8.0"), ("1.8.1", "1.8.1")])
def test_npm_release_mapping(app, expected):
    assert npm_version(app) == expected


def test_npm_release_mapping_rejects_invalid_input():
    with pytest.raises(ValueError):
        npm_version("1.8a; exit 0")
