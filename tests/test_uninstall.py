"""Tests for the complete uninstaller (src/uninstall.py, uninstall.sh).

Everything runs against a fake HOME below tmp_path. Machine-wide helpers (ps, kill, brew, launchctl, ...) are
replaced by recorders, so no test can touch the real machine or the user's running codebone.
"""
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from src import uninstall as un

REPO = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _json(path: Path, data: dict, indent: int = 2, newline: bool = False) -> Path:
    return _write(path, json.dumps(data, indent=indent, ensure_ascii=False) + ("\n" if newline else ""))


def _snapshot(root: Path) -> dict:
    """path -> (type, content) for the whole tree, symlinks recorded as links (never followed)."""
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            if p.is_symlink():
                snap[rel] = ("l", os.readlink(p))
            elif p.is_dir():
                snap[rel] = ("d", None)
            else:
                snap[rel] = ("f", p.read_bytes())
    return snap


_REAL_RUN, _REAL_PS = un._run, un._ps  # the autouse fixture below swaps both out for every test
SERVER = {"command": "/x/python3", "args": ["-m", "codebone_mcp.server"], "env": {"CODEBONE_PORT": "8053"}}
OTHER = {"command": "npx", "args": ["-y", "some-server"], "env": {"NAME": "Zoë"}}


@pytest.fixture(params=["home", "Zoë Ünï [x]*?{a,b}"])
def world(tmp_path, request):
    """A realistic fake machine: every location codebone ever used, plus neighbours that must survive.
    Runs once with a plain home and once with a home full of spaces, unicode and glob characters."""
    home = tmp_path / request.param
    lib = home / "Library"
    outside = _write(tmp_path / "outside" / "precious.txt", "keep me")
    user_model = _write(tmp_path / "Downloads" / "qwen-7b.gguf", "user model")

    # the app bundle lives somewhere unusual, with a space in the path
    bundle = tmp_path / "Other Place" / "codebone.app"
    res = bundle / "Contents" / "Resources"
    _write(res / "venv" / "bin" / "python3", "p" * 300_000)
    _write(res / "src" / "src" / "uninstall.py")
    _write(res / "models" / "m.gguf", "m" * 300_000)
    (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.codebone.app"}))

    # projects: one clean, one with legacy per-project MCP files
    clean = tmp_path / "proj_clean"
    _write(clean / "main.py", "print('hi')\n")
    _write(clean / ".gitignore", "*.pyc\n")
    _write(clean / "src" / "app.py", "x = 1\n")
    legacy = tmp_path / "proj_legacy"
    _write(legacy / "main.py", "print('legacy')\n")
    _json(legacy / ".cursor" / "mcp.json", {"mcpServers": {"codebone": SERVER, "keep": OTHER}})
    _json(legacy / ".gemini" / "mcp_config.json", {"mcpServers": {"codebone": SERVER}})
    _json(legacy / ".agents" / "mcp_config.json", {"mcpServers": {"pug": SERVER}})
    _write(legacy / ".agents" / "notes.md", "user notes")

    # Application Support (with symlinks into the bundle and out of the tree)
    support = lib / "Application Support" / "codebone"
    _write(support / "codebone.sqlite3", "db")
    _write(support / "codebone.sqlite3-wal", "wal")
    _write(support / "codebone.sqlite3-shm", "shm")
    _write(support / "scans" / "a.sqlite3", "scan")
    _write(support / "feedback.jsonl", "{}\n")
    _write(support / "models" / "own.gguf", "o" * 1000)
    (support / "models" / "m.gguf").symlink_to(res / "models" / "m.gguf")
    (support / "venv").symlink_to(res / "venv")
    (support / "src").symlink_to(res / "src")
    (support / "external-link").symlink_to(outside.parent)
    _json(support / "config.json", {
        "project_path": str(clean),
        "recent_projects": [str(clean), str(legacy), str(tmp_path / "gone")],
        "known_models": [{"name": "7B", "path": str(user_model)}],
    })
    _write(lib / "Application Support" / "CodeBone" / "old.sqlite3", "old")
    _write(lib / "Application Support" / "PUG" / "pug.sqlite3", "old")
    _write(lib / "Application Support" / "Unrelated" / "keep.txt")

    # logs, caches, prefs, state
    _write(lib / "Logs" / "codebone" / "codebone.log", "log")
    _write(lib / "Logs" / "OtherApp" / "keep.log")
    _write(lib / "Caches" / "codebone-build" / "model.gguf", "c" * 1000)
    _write(lib / "Caches" / "com.codebone.app" / "Cache.db", "c")
    _write(lib / "Caches" / "com.other.app" / "keep.db")
    _write(lib / "Preferences" / "com.codebone.app.plist", "plist")
    _write(lib / "Preferences" / "com.other.app.plist", "keep")
    _write(lib / "Saved Application State" / "com.codebone.app.savedState" / "data.data")
    _write(lib / "HTTPStorages" / "com.codebone.app" / "x")
    _write(lib / "WebKit" / "com.codebone.app" / "x")
    _write(lib / "Containers" / "com.codebone.app" / "x")
    _write(lib / "Group Containers" / "ABCDE.com.codebone.app" / "x")
    _write(lib / "Group Containers" / "ABCDE.com.other.app" / "keep")
    _write(lib / "LaunchAgents" / "com.codebone.app.plist", "agent")
    _write(lib / "LaunchAgents" / "com.pug.app.plist", "agent")
    _write(lib / "LaunchAgents" / "com.pugsley.other.plist", "keep")
    _write(lib / "LaunchAgents" / "com.other.app.plist", "keep")

    # app bundles
    _write(home / "Applications" / "codebone.app" / "Contents" / "Info.plist")
    _write(home / "Applications" / "Uninstall codebone.app" / "Contents" / "Info.plist")
    _write(home / "Applications" / "PUG.app" / "Contents" / "Info.plist")
    _write(home / "Applications" / "Other.app" / "Contents" / "Info.plist")

    # MCP configs of other tools
    desktop = _json(lib / "Application Support" / "Claude" / "claude_desktop_config.json",
                    {"theme": "dark", "mcpServers": {"first": OTHER, "codebone": SERVER, "pug": SERVER, "last": OTHER}},
                    indent=4, newline=True)
    claude_json = _json(home / ".claude.json", {
        "numStartups": 7,
        "mcpServers": {"alpha": OTHER, "codebone": SERVER, "pug": SERVER},
        "projects": {"/some/proj": {"mcpServers": {"codebone": SERVER, "beta": OTHER}}, "/other": {"allowedTools": []}},
    })
    os.chmod(claude_json, 0o600)
    _json(home / ".cursor" / "mcp.json", {"mcpServers": {"codebone": SERVER}})
    _write(home / ".cursor" / "extensions" / "ext.txt")
    _json(home / ".gemini" / "config" / "mcp_config.json", {"mcpServers": {"codebone": SERVER}})
    _json(home / ".gemini" / "antigravity-ide" / "mcp_config.json", {"mcpServers": {"codebone": SERVER, "keep": OTHER}})

    return {
        "tmp": tmp_path, "home": home, "lib": lib, "bundle": bundle, "support": support, "clean": clean,
        "legacy": legacy, "outside": outside, "user_model": user_model, "desktop": desktop, "claude_json": claude_json,
    }


@pytest.fixture(autouse=True)
def calls(monkeypatch):
    """No test may run a real helper command or look at real processes: record instead."""
    log = []
    monkeypatch.setattr(un, "_run", lambda cmd, *a, **k: (log.append(list(cmd)), (0, ""))[1])
    monkeypatch.setattr(un, "_ps", lambda: [])
    return log


def _all_removed(w):
    lib, home = w["lib"], w["home"]
    gone = [
        w["support"], lib / "Application Support" / "CodeBone", lib / "Application Support" / "PUG",
        lib / "Logs" / "codebone", lib / "Caches" / "codebone-build", lib / "Caches" / "com.codebone.app",
        lib / "Preferences" / "com.codebone.app.plist", lib / "Saved Application State" / "com.codebone.app.savedState",
        lib / "HTTPStorages" / "com.codebone.app", lib / "WebKit" / "com.codebone.app",
        lib / "Containers" / "com.codebone.app", lib / "Group Containers" / "ABCDE.com.codebone.app",
        lib / "LaunchAgents" / "com.codebone.app.plist", lib / "LaunchAgents" / "com.pug.app.plist",
        home / "Applications" / "codebone.app", home / "Applications" / "Uninstall codebone.app",
        home / "Applications" / "PUG.app", w["bundle"],
    ]
    return gone


def _survivors(w):
    lib, home = w["lib"], w["home"]
    return [
        w["outside"], w["user_model"], w["clean"] / "main.py", lib / "Application Support" / "Unrelated" / "keep.txt",
        lib / "Logs" / "OtherApp" / "keep.log", lib / "Caches" / "com.other.app" / "keep.db",
        lib / "Preferences" / "com.other.app.plist", lib / "Group Containers" / "ABCDE.com.other.app" / "keep",
        lib / "LaunchAgents" / "com.pugsley.other.plist", lib / "LaunchAgents" / "com.other.app.plist",
        home / "Applications" / "Other.app" / "Contents" / "Info.plist", w["legacy"] / "main.py",
    ]


# ── plan and dry run ────────────────────────────────────────────────────────


def test_collect_targets_lists_what_exists(world):
    targets = un.collect_targets(home=world["home"], bundle=world["bundle"])
    kinds = {t.kind for t in targets}
    assert {"data", "logs", "cache", "prefs", "state", "service", "mcp", "app"} <= kinds
    assert all(t.exists for t in targets)
    paths = [t.path for t in targets]
    assert str(world["support"]) in paths and str(world["bundle"]) in paths
    assert str(world["home"] / "Applications" / "Other.app") not in paths
    assert not any(t.kind in ("process", "package") for t in targets)  # machine-wide steps stay off for a fake home
    assert len({os.lstat(p).st_ino for p in paths if os.path.lexists(p)}) == len(paths)  # one row per inode
    by_path = {t.path: t for t in targets}
    assert by_path[str(world["support"])].size_bytes < 100_000  # symlinks into the 600 KB bundle are not followed
    assert by_path[str(world["bundle"])].size_bytes >= 600_000


def test_dry_run_changes_nothing(world, calls):
    before = _snapshot(world["tmp"])
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"], dry_run=True)
    assert _snapshot(world["tmp"]) == before
    assert report.dry_run and report.removed and not report.errors
    assert "Would remove" in report.format() and "Dry run" in report.format()
    assert calls == []


# ── full run ────────────────────────────────────────────────────────────────


def test_full_uninstall_removes_everything_and_keeps_the_rest(world, calls):
    clean_before = _snapshot(world["clean"])
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert not report.errors, report.errors
    for path in _all_removed(world):
        assert not os.path.lexists(path), path
    for path in _survivors(world):
        assert path.exists(), path
    assert _snapshot(world["clean"]) == clean_before  # project folder byte-identical
    assert (world["outside"]).read_text() == "keep me"  # symlink out of Application Support was not followed
    assert calls == []  # fake home: no helper command ran


def test_second_run_finds_nothing(world):
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert un.collect_targets(home=world["home"], bundle=world["bundle"]) == []
    again = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert again.nothing_to_remove
    assert "Nothing to remove" in again.format()


def test_keep_app_leaves_bundles(world):
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"], remove_app=False)
    assert world["bundle"].exists() and (world["home"] / "Applications" / "codebone.app").exists()
    assert not world["support"].exists()
    assert any("kept" in s for s in report.skipped)


def test_bundle_inside_a_project_folder_is_left_alone(world):
    """A dist/codebone.app build inside an indexed project is a project file, even if the venv link points at it."""
    build = world["clean"] / "dist" / "codebone.app"
    _write(build / "Contents" / "Resources" / "venv" / "bin" / "python3", "p")
    (build / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.codebone.app"}))
    for link in ("venv", "src"):
        (world["support"] / link).unlink()
    (world["support"] / "venv").symlink_to(build / "Contents" / "Resources" / "venv")
    clean_before = _snapshot(world["clean"])
    assert not any("dist" in t.path for t in un.collect_targets(home=world["home"]))
    report = un.run_uninstall(home=world["home"])
    assert _snapshot(world["clean"]) == clean_before
    assert any("inside one of your project folders" in s for s in report.skipped)
    # naming it explicitly is the caller's call
    un.run_uninstall(home=world["home"], bundle=build)
    assert not build.exists()


def test_bundle_must_be_an_app(world):
    before = _snapshot(world["home"])
    report = un.run_uninstall(home=world["home"], bundle=world["home"], dry_run=True)
    assert any("must be a .app" in e for e in report.errors)
    assert _snapshot(world["home"]) == before


# ── MCP configs ─────────────────────────────────────────────────────────────


def test_mcp_entries_removed_and_everything_else_kept(world):
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    home = world["home"]

    # keeps the file's 4-space indent and trailing newline, other servers and their order
    expected = {"theme": "dark", "mcpServers": {"first": OTHER, "last": OTHER}}
    assert world["desktop"].read_text(encoding="utf-8") == json.dumps(expected, indent=4, ensure_ascii=False) + "\n"

    cj = world["claude_json"]
    assert json.loads(cj.read_text()) == {
        "numStartups": 7,
        "mcpServers": {"alpha": OTHER},
        "projects": {"/some/proj": {"mcpServers": {"beta": OTHER}}, "/other": {"allowedTools": []}},
    }
    assert stat.S_IMODE(cj.stat().st_mode) == 0o600
    assert not cj.read_text().endswith("\n")  # it had none

    # only codebone in the file: file deleted, directory kept because it holds other things
    assert not (home / ".cursor" / "mcp.json").exists() and (home / ".cursor" / "extensions" / "ext.txt").exists()
    # only codebone in it: file and the directory codebone created are gone, .gemini stays for antigravity-ide
    assert not (home / ".gemini" / "config").exists()
    ide = json.loads((home / ".gemini" / "antigravity-ide" / "mcp_config.json").read_text())
    assert ide == {"mcpServers": {"keep": OTHER}}

    # legacy per-project files
    legacy = world["legacy"]
    assert json.loads((legacy / ".cursor" / "mcp.json").read_text()) == {"mcpServers": {"keep": OTHER}}
    assert not (legacy / ".gemini").exists()
    assert not (legacy / ".agents" / "mcp_config.json").exists() and (legacy / ".agents" / "notes.md").exists()


def test_empty_config_dirs_are_removed_only_when_empty(world):
    home = world["home"]
    shutil.rmtree(home / ".gemini" / "antigravity-ide")
    un.run_uninstall(home=home, bundle=world["bundle"])
    assert not (home / ".gemini").exists()  # config/ and .gemini/ were only ours


def test_unparsable_configs_are_never_written(world):
    desktop_text = '// my notes\n{"mcpServers": {"codebone": {}, "other": {}}}\n'
    world["desktop"].write_text(desktop_text, encoding="utf-8")
    cursor = world["home"] / ".cursor" / "mcp.json"
    cursor.write_text('["codebone"]', encoding="utf-8")
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert world["desktop"].read_text(encoding="utf-8") == desktop_text
    assert cursor.read_text(encoding="utf-8") == '["codebone"]'
    assert any("claude_desktop_config.json" in s for s in report.skipped)
    assert not world["support"].exists()  # the rest still ran


def test_symlinked_config_is_edited_through_the_link(world):
    real = _json(world["tmp"] / "dotfiles" / "claude.json", {"mcpServers": {"codebone": SERVER, "keep": OTHER}})
    world["claude_json"].unlink()
    world["claude_json"].symlink_to(real)
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert world["claude_json"].is_symlink()
    assert json.loads(real.read_text()) == {"mcpServers": {"keep": OTHER}}


def test_read_only_trees_and_dangling_links_are_removed(world):
    locked = _write(world["support"] / "scans" / "locked" / "x.sqlite3")
    os.chmod(locked.parent, 0o500)
    dangling = world["home"] / "Applications" / "PUG.app"
    shutil.rmtree(dangling)
    dangling.symlink_to(world["tmp"] / "does-not-exist.app")
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert not report.errors, report.errors
    assert not world["support"].exists() and not os.path.lexists(dangling)


# ── hostile and unusual input ───────────────────────────────────────────────


def test_symlinked_config_directory_is_never_removed(world):
    """~/.cursor kept in a dotfiles repo: the file with only codebone in it goes, the linked directory stays."""
    home = world["home"]
    dot = _json(world["tmp"] / "dotfiles" / "cursor" / "mcp.json", {"mcpServers": {"codebone": SERVER}}).parent
    shutil.rmtree(home / ".cursor")
    (home / ".cursor").symlink_to(dot)
    report = un.run_uninstall(home=home, bundle=world["bundle"])
    assert not report.errors, report.errors
    assert (home / ".cursor").is_symlink() and dot.is_dir() and not (dot / "mcp.json").exists()


def test_data_directory_that_is_a_symlink_only_loses_the_link(world):
    real = world["tmp"] / "elsewhere" / "codebone-data"
    real.parent.mkdir()
    shutil.move(str(world["support"]), str(real))
    world["support"].symlink_to(real)
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert not os.path.lexists(world["support"])
    assert (real / "codebone.sqlite3").exists()  # never followed out of Application Support


def test_a_symlinked_app_is_unlinked_not_followed(world):
    """Homebrew style: ~/Applications/codebone.app is a link to a bundle somebody else owns."""
    brewed = world["tmp"] / "Cellar" / "codebone.app"
    _write(brewed / "Contents" / "MacOS" / "codebone")
    link = world["home"] / "Applications" / "codebone.app"
    shutil.rmtree(link)
    link.symlink_to(brewed)
    un.run_uninstall(home=world["home"])
    assert not os.path.lexists(link) and (brewed / "Contents" / "MacOS" / "codebone").exists()


def test_a_foreign_pug_server_is_not_ours(world, system, calls):
    """`pug` is codebone's legacy name but also a template engine: only an entry that points at this app goes."""
    foreign = {"command": "npx", "args": ["-y", "pug-template-mcp"], "env": {"PUG_LEVEL": "1"}}
    _json(world["desktop"], {"mcpServers": {"pug": foreign, "codebone": SERVER}})
    _json(world["claude_json"], {"mcpServers": {"pug": foreign}})
    legacy = {"command": "/x/venv/bin/python3", "args": ["/x/src/pug_mcp/server.py"], "env": {"PUG_PORT": "8053"}}
    _json(world["home"] / ".cursor" / "mcp.json", {"mcpServers": {"pug": legacy, "keep": OTHER}})
    targets = [t.label for t in un.collect_targets(home=world["home"], bundle=world["bundle"], system=True)]
    assert not any("Claude Code" in label for label in targets)
    un.run_uninstall(home=world["home"], bundle=world["bundle"], system=True)
    assert json.loads(world["desktop"].read_text())["mcpServers"] == {"pug": foreign}
    assert json.loads(world["claude_json"].read_text()) == {"mcpServers": {"pug": foreign}}
    assert json.loads((world["home"] / ".cursor" / "mcp.json").read_text()) == {"mcpServers": {"keep": OTHER}}
    removed_by_cli = [c[-1] for c in calls if c[:3] == ["/fake/claude", "mcp", "remove"]]
    assert "pug" not in removed_by_cli and "codebone" not in removed_by_cli  # nothing of ours left in ~/.claude.json


def test_undecodable_and_absurdly_nested_configs_are_reported_and_untouched(world):
    cursor = world["home"] / ".cursor" / "mcp.json"
    cursor.write_bytes(b'{"mcpServers": {"codebone": {}, "n": "caf\xe9"}}')
    deep = "[" * 100_000 + '"codebone"'  # nested deeper than the JSON parser allows
    world["desktop"].write_text(deep, encoding="utf-8")
    un.collect_targets(home=world["home"], bundle=world["bundle"])  # the confirmation dialog must not crash
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert cursor.read_bytes() == b'{"mcpServers": {"codebone": {}, "n": "caf\xe9"}}'
    assert world["desktop"].read_text() == deep
    assert sum("not a valid JSON object" in s for s in report.skipped) == 2
    assert not report.errors and not world["support"].exists()


def test_hostile_app_config_does_not_break_the_run(world):
    (world["support"] / "config.json").write_text("[" * 100_000, encoding="utf-8")
    (world["support"] / "config.json").chmod(0o600)
    assert un.collect_targets(home=world["home"], bundle=world["bundle"])
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert not report.errors and not world["support"].exists()


def test_unreadable_config_is_reported(world):
    os.chmod(world["desktop"], 0)
    try:
        if os.access(world["desktop"], os.R_OK):
            pytest.skip("permissions are not enforced for this user")
        report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    finally:
        os.chmod(world["desktop"], 0o600)
    assert any("could not be read" in s and "claude_desktop_config.json" in s for s in report.skipped)


def test_explicit_bundle_must_be_a_codebone_app(world):
    other = world["home"] / "Applications" / "Other.app"
    report = un.run_uninstall(home=world["home"], bundle=other)
    assert any("not a codebone app bundle" in e for e in report.errors)
    assert other.exists() and not world["support"].exists()  # nothing else is held back
    renamed = world["tmp"] / "Copy of codebone.app"
    _write(renamed / "Contents" / "MacOS" / "codebone")
    (renamed / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.codebone.app"}))
    un.run_uninstall(home=world["home"], bundle=renamed)
    assert not renamed.exists()  # recognised by its bundle id, not only by its name


def test_empty_relative_or_root_home_is_refused(world, monkeypatch, capsys):
    """An empty $HOME becomes "/" (Python 3.13) or the current directory (3.9): /Applications, /Library or a
    project folder would be in reach."""
    for bad in ("", "/", "//", "relative/home"):
        monkeypatch.setenv("HOME", bad)
        for call in (lambda: un.run_uninstall(dry_run=True), lambda: un.collect_targets()):
            with pytest.raises(ValueError, match="home directory"):
                call()
        assert un.main(["--dry-run"]) == 2
        assert "home directory" in capsys.readouterr().err
    with pytest.raises(ValueError, match="home directory"):
        un.run_uninstall(home="/", dry_run=True)
    assert un._home(str(world["home"]) + "/") == world["home"]


def test_project_that_is_the_home_directory_is_handled_once(world):
    home = world["home"]
    _json(world["support"] / "config.json", {"project_path": str(home), "recent_projects": [str(home)]})
    mine = lambda text: text.count("~/.cursor/mcp.json") if "~" in text else 0  # noqa: E731
    report = un.run_uninstall(home=home, bundle=world["bundle"], dry_run=True)
    assert sum(mine(r) for r in report.removed) == 1
    assert sum(t.path == str(home / ".cursor" / "mcp.json") for t in un.collect_targets(home=home)) == 1


def test_login_items_are_matched_by_bundle_id(world):
    agents = world["lib"] / "LaunchAgents"
    mine = [_write(agents / n, "agent") for n in ("com.codebone.app.login.plist", "com.pug.app-helper.plist")]
    keep = [_write(agents / n, "keep") for n in ("com.pug.helper.plist", "com.codebone.other.plist", "com.pugs.app.plist")]
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert not any(os.path.lexists(p) for p in mine)
    assert all(p.exists() for p in keep)


def test_bundle_on_a_read_only_volume_is_left_and_reported(world, monkeypatch):
    monkeypatch.setattr(un, "_read_only", lambda p: p == world["bundle"])
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert world["bundle"].exists() and not report.errors
    assert any("read-only" in s for s in report.skipped)


def test_one_failing_bundle_does_not_keep_the_others(world, monkeypatch):
    first = world["home"] / "Applications" / "codebone.app"
    monkeypatch.setattr(un, "_hosts_this_process", lambda app: app == first)
    monkeypatch.setattr(un, "schedule_bundle_removal", lambda *a: (_ for _ in ()).throw(OSError("fork failed")))
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert any("fork failed" in e for e in report.errors)
    assert not (world["home"] / "Applications" / "PUG.app").exists() and not world["bundle"].exists()


def test_report_says_when_a_project_file_was_edited(world):
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert report.project_files_edited and "only codebone's own MCP entries" in report.format()
    fresh = un.Report(removed=["x"])
    assert "Your project folders were not touched" in fresh.format()


def test_sudo_hint_is_shell_quoted():
    assert "rm -rf '/x/o'\"'\"'brien'" in un._why(PermissionError(), Path("/x/o'brien"))


def test_ps_joins_executable_and_command_line(monkeypatch):
    bundle = "/Users/x/Other Place/codebone.app/Contents/MacOS/codebone"
    outputs = {
        "pid=,comm=": f"  10 {bundle}\n  11 /usr/bin/vim\n   x junk\n",
        "pid=,ppid=,command=": f"  10     1 {bundle}\n  11    10 vim codebone_main.py\n  12 1 died-before-comm\n",
    }
    monkeypatch.setattr(un, "_run", lambda cmd, *a, **k: (0, outputs[cmd[-1]]))
    assert _REAL_PS() == [(10, 1, bundle, bundle), (11, 10, "/usr/bin/vim", "vim codebone_main.py")]
    assert un._is_codebone_process(bundle, bundle)
    assert not un._is_codebone_process("/usr/bin/vim", "vim codebone_main.py")


def test_helper_commands_get_no_stdin():
    """A helper that prompts (sudo, keychain) must not sit on our terminal: with stdin closed it ends at once."""
    code = "import sys; from src import uninstall as un; print(un._run(['/bin/cat'], timeout=8), flush=True)"
    proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            cwd=str(REPO), env=dict(os.environ, PYTHONPATH=str(REPO)))
    try:
        start = time.monotonic()
        line = proc.stdout.readline()
        assert time.monotonic() - start < 6, "helper waited for input"
        assert line.strip() == "(0, '')"
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


def test_schedule_bundle_removal_gets_an_absolute_path(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(un.subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    monkeypatch.chdir(tmp_path)
    un.schedule_bundle_removal("rel/codebone.app", 123)
    assert seen[0][-2:] == ["123", os.path.abspath("rel/codebone.app")]


# ── independence of steps ───────────────────────────────────────────────────


def test_failures_are_reported_and_do_not_stop_other_steps(world, monkeypatch):
    real_delete = un._delete

    def flaky(path):
        if path.name == "codebone" and path.parent.name == "Logs":
            raise PermissionError("denied")
        real_delete(path)

    monkeypatch.setattr(un, "_delete", flaky)
    monkeypatch.setattr(un, "_launch_agents", lambda home: (_ for _ in ()).throw(RuntimeError("boom")))
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert any("permission denied" in e and "Logs" in e for e in report.errors)
    assert any(e.startswith("services: boom") for e in report.errors)
    assert not world["support"].exists() and not world["bundle"].exists()
    assert (world["lib"] / "Logs" / "codebone").exists()


# ── machine-wide steps (system=True, all helpers faked) ─────────────────────


@pytest.fixture
def system(world, monkeypatch, calls):
    apps = world["tmp"] / "SystemApplications"
    _write(apps / "codebone.app" / "Contents" / "Info.plist")
    brew = world["tmp"] / "brew"
    _write(brew / "Cellar" / "codebone" / "1.2.2" / "file")
    monkeypatch.setattr(un, "SYSTEM_APPS", apps)
    monkeypatch.setattr(un, "BREW_PREFIXES", (brew,))
    monkeypatch.setattr(un, "_find_tool", lambda name, home: f"/fake/{name}")

    def fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if cmd[1:] == ["tap"]:
            return 0, "homebrew/core\npalusc/codebone\n"
        if cmd[0].endswith("npm") and cmd[1] == "ls":
            return 0, "/lib\n`-- codebone-mcp@1.2.2\n"
        return 0, ""

    monkeypatch.setattr(un, "_run", fake_run)
    return apps


def test_system_steps_run_the_expected_commands(world, system, calls):
    un.run_uninstall(home=world["home"], bundle=world["bundle"], system=True)
    joined = [" ".join(c) for c in calls]

    def ran(text):
        return any(text in c for c in joined)

    assert ran("/fake/claude mcp remove -s user codebone") and ran("/fake/claude mcp remove -s user pug")
    assert ran("/fake/brew uninstall codebone") and ran("/fake/brew untap palusc/codebone")
    assert ran("/fake/npm uninstall -g codebone-mcp")
    assert ran("launchctl bootout") and ran("com.pug.app.plist")
    assert ran("defaults delete com.codebone.app")
    assert ran(f"{un.LSREGISTER} -u {world['bundle']}")
    assert ran("tccutil reset All com.codebone.app")
    assert not (system / "codebone.app").exists()  # /Applications is only a target for the real account home


def test_system_dry_run_only_probes(world, system, calls):
    before = _snapshot(world["tmp"])
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"], system=True, dry_run=True)
    assert _snapshot(world["tmp"]) == before
    changing = ("uninstall", "untap", "remove", "bootout", "unload", "delete", "reset", "-u")
    assert not [c for c in calls if any(word in c[1:3] or word in c for word in changing)], calls
    assert report.dry_run and any("Homebrew" in r for r in report.removed)


def test_fake_home_never_reaches_system_locations(world, monkeypatch, tmp_path):
    marker = _write(tmp_path / "SystemApplications" / "codebone.app" / "Contents" / "x")
    monkeypatch.setattr(un, "SYSTEM_APPS", tmp_path / "SystemApplications")
    monkeypatch.setattr(un, "_ps", lambda: pytest.fail("ps must not run for a fake home"))
    un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert marker.exists()


def test_processes_are_stopped_but_never_this_one(world, system, monkeypatch):
    me, parent = os.getpid(), os.getppid()
    app = "/Applications/codebone.app/Contents"
    rows = [  # (pid, ppid, executable, command line)
        (me, parent, f"{app}/Resources/venv/bin/python3", f"{app}/Resources/venv/bin/python3 -m src.uninstall"),
        (parent, 1, f"{app}/MacOS/codebone", f"{app}/MacOS/codebone"),
        (900, 1, f"{app}/MacOS/codebone", f"{app}/MacOS/codebone"),
        (901, 1, "/Users/x/Library/Application Support/codebone/venv/bin/python3",
         "/Users/x/Library/Application Support/codebone/venv/bin/python3 -m codebone_mcp.server"),
        (902, 1, "/opt/homebrew/bin/node", "node /opt/homebrew/lib/node_modules/codebone-mcp/bin/codebone-mcp.js"),
        (903, 1, "/Users/x/Other Place/PUG.app/Contents/MacOS/PUG", "/Users/x/Other Place/PUG.app/Contents/MacOS/PUG"),
        (904, 1, "/usr/bin/vim", "vim notes.txt"),
        (905, 1, "/usr/bin/python3", "/usr/bin/python3 pug_main.py"),
        (906, 1, "/opt/homebrew/bin/node", "npm exec codebone-mcp"),
        (907, 1, "/usr/bin/grep", "/usr/bin/grep codebone-mcp-notes"),
        # somebody editing or searching codebone's files is not codebone
        (908, 1, "/usr/bin/vim", "vim codebone_main.py"),
        (909, 1, "/usr/bin/vim", "vim codebone_mcp/server.py"),
        (910, 1, "/usr/bin/vim", f"/usr/bin/vim {app}/Info.plist"),
        (911, 1, "/usr/bin/grep", "grep -r codebone-mcp ."),
    ]
    monkeypatch.setattr(un, "_ps", lambda: rows)
    killed = []
    monkeypatch.setattr(un, "_kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(un, "_alive", lambda pid: pid not in killed)
    targets = un.collect_targets(home=world["home"], bundle=world["bundle"], system=True)
    assert sorted(t.path for t in targets if t.kind == "process") == [f"pid {p}" for p in (900, 901, 902, 903, 905, 906)]
    un.run_uninstall(home=world["home"], bundle=world["bundle"], system=True)
    assert sorted(set(killed)) == [900, 901, 902, 903, 905, 906]
    assert me not in killed and parent not in killed


def test_a_process_that_will_not_die_is_an_error(world, system, monkeypatch):
    exe = "/Applications/codebone.app/Contents/MacOS/codebone"
    monkeypatch.setattr(un, "_ps", lambda: [(900, 1, exe, exe)])
    monkeypatch.setattr(un, "_kill", lambda pid, sig: None)
    monkeypatch.setattr(un, "_alive", lambda pid: True)
    clock = iter(range(0, 10_000, 5))
    monkeypatch.setattr(un, "time", types.SimpleNamespace(sleep=lambda s: None, monotonic=lambda: next(clock)))
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"], system=True)
    assert any("process 900 could not be stopped" in e for e in report.errors)


# ── the bundle this process runs from ───────────────────────────────────────


def test_running_bundle_is_removed_after_exit(world, monkeypatch):
    scheduled = []
    monkeypatch.setattr(un, "_hosts_this_process", lambda app: app == world["bundle"])
    monkeypatch.setattr(un, "schedule_bundle_removal", lambda app, pid: scheduled.append((app, pid)))
    report = un.run_uninstall(home=world["home"], bundle=world["bundle"])
    assert world["bundle"].exists()
    assert scheduled == [(world["bundle"], os.getpid())]
    assert any("deleted when this process exits" in r for r in report.removed)
    assert not (world["home"] / "Applications" / "codebone.app").exists()  # other copies go right away


def test_schedule_bundle_removal_waits_for_the_pid_and_handles_odd_paths(tmp_path):
    app = tmp_path / "My Apps" / "co'de bone $1.app"
    _write(app / "Contents" / "MacOS" / "x")
    not_an_app = _write(tmp_path / "precious dir" / "file")
    waiter = subprocess.Popen(["sleep", "1"])
    helper = un.schedule_bundle_removal(app, waiter.pid)
    helper2 = un.schedule_bundle_removal(not_an_app.parent, waiter.pid)
    time.sleep(0.5)
    assert app.exists()  # the process is still alive
    waiter.wait()
    for _ in range(60):
        if not app.exists():
            break
        time.sleep(0.2)
    assert not app.exists()
    helper.wait(timeout=10)
    helper2.wait(timeout=10)
    assert not_an_app.exists()  # only *.app paths are ever deleted


def test_uninstall_started_inside_the_bundle_deletes_it_after_exit(world):
    """The real flow of `python -m src.uninstall` from the app's own Python: the bundle outlives the process."""
    res = world["bundle"] / "Contents" / "Resources"
    shutil.copy(REPO / "src" / "uninstall.py", res / "src" / "src" / "uninstall.py")
    _write(res / "src" / "src" / "__init__.py", "")
    env = dict(os.environ, HOME=str(world["home"]), PYTHONPATH=str(res / "src"))
    proc = subprocess.run([sys.executable, "-P", "-m", "src.uninstall", "--yes"], capture_output=True, text=True,
                          env=env, cwd=str(world["tmp"]), timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "deleted when this process exits" in proc.stdout
    for _ in range(60):
        if not world["bundle"].exists():
            break
        time.sleep(0.2)
    assert not world["bundle"].exists()
    assert not world["support"].exists()


# ── command line ────────────────────────────────────────────────────────────


def test_cli_dry_run_yes_and_refusal(world, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(world["home"]))
    before = _snapshot(world["tmp"])
    assert un.main(["--dry-run"]) == 0
    assert "Would remove" in capsys.readouterr().out
    assert _snapshot(world["tmp"]) == before

    assert un.main([]) == 2  # no terminal to confirm on
    assert _snapshot(world["tmp"]) == before

    apps = world["home"] / "Applications"
    assert un.main(["--yes", "--keep-app"]) == 0
    assert (apps / "codebone.app").exists() and not world["support"].exists()
    assert "Removed" in capsys.readouterr().out

    assert un.main(["--yes"]) == 0  # the kept bundles go now
    assert not (apps / "codebone.app").exists() and (apps / "Other.app").exists()
    assert un.main(["--yes"]) == 0
    assert "Nothing to remove" in capsys.readouterr().out


def test_cli_asks_for_confirmation(world, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(world["home"]))
    monkeypatch.setattr(un.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    before = _snapshot(world["tmp"])
    assert un.main([]) == 1
    assert _snapshot(world["tmp"]) == before
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert un.main([]) == 0
    assert not world["support"].exists()


def test_module_runs_as_script_with_an_isolated_home(world):
    env = dict(os.environ, HOME=str(world["home"]), PYTHONPATH=str(REPO))
    res = subprocess.run([sys.executable, "-m", "src.uninstall", "--dry-run"], capture_output=True, text=True,
                         env=env, cwd=str(world["tmp"]), timeout=60)
    assert res.returncode == 0, res.stderr
    assert "Would remove" in res.stdout and str(world["support"]).replace(str(world["home"]), "~") in res.stdout


# ── terminal fallback ───────────────────────────────────────────────────────


def _shell(world, *args, stdin=""):
    """uninstall.sh forced onto its shell path, with an isolated HOME (so it never reaches system locations)."""
    env = dict(os.environ, HOME=str(world["home"]), CODEBONE_UNINSTALL_SHELL_ONLY="1")
    return subprocess.run(["/bin/bash", str(REPO / "uninstall.sh"), *args], input=stdin, capture_output=True,
                          text=True, env=env, cwd=str(world["tmp"]), timeout=120)


def test_shell_fallback_dry_run_changes_nothing(world):
    before = _snapshot(world["tmp"])
    res = _shell(world, "--dry-run")
    assert res.returncode == 0, res.stderr
    assert _snapshot(world["tmp"]) == before


def test_shell_fallback_removes_the_same_things(world):
    res = _shell(world, "--yes", "--keep-app")
    assert res.returncode == 0, res.stdout + res.stderr
    home, lib = world["home"], world["lib"]
    kept = [world["bundle"]] + [home / "Applications" / n for n in ("codebone.app", "PUG.app", "Uninstall codebone.app")]
    for path in _all_removed(world):
        assert path.exists() == (path in kept), path  # --keep-app leaves only the bundles
    for path in _survivors(world):
        assert path.exists(), path
    assert json.loads(world["claude_json"].read_text())["mcpServers"] == {"alpha": OTHER}
    assert json.loads(world["desktop"].read_text())["mcpServers"] == {"first": OTHER, "last": OTHER}
    assert not (home / ".cursor" / "mcp.json").exists() and (home / ".cursor" / "extensions").exists()
    assert not (home / ".gemini" / "config").exists() and (home / ".gemini" / "antigravity-ide").exists()
    assert not (world["legacy"] / ".gemini").exists()
    assert (world["legacy"] / ".agents" / "notes.md").exists()
    assert world["outside"].read_text() == "keep me"
    last = _shell(world, "--yes")  # the kept bundles in ~/Applications go now
    assert last.returncode == 0 and not (home / "Applications" / "codebone.app").exists()
    assert (home / "Applications" / "Other.app").exists()
    again = _shell(world, "--yes")
    assert again.returncode == 0 and "nothing to remove" in again.stdout.lower()


def test_shell_finds_a_bundle_kept_elsewhere_through_the_symlinks(world):
    assert _shell(world, "--yes").returncode == 0
    assert not world["bundle"].exists() and not world["support"].exists()


def test_shell_prefers_the_python_module(world):
    before = _snapshot(world["tmp"])
    env = dict(os.environ, HOME=str(world["home"]))
    res = subprocess.run(["/bin/bash", str(REPO / "uninstall.sh"), "--dry-run"], capture_output=True, text=True,
                         env=env, cwd=str(world["tmp"]), timeout=120)
    assert res.returncode == 0, res.stderr
    assert "Would remove (" in res.stdout  # the module's report format, not the shell path's
    assert _snapshot(world["tmp"]) == before


def test_shell_help_prints_the_whole_header():
    res = subprocess.run(["/bin/bash", str(REPO / "uninstall.sh"), "--help"], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0 and res.stdout.rstrip().endswith("over the same locations.")
    assert "set -o" not in res.stdout


def test_shell_rejects_unknown_options(world):
    res = _shell(world, "--wipe-everything")
    assert res.returncode == 2 and "unknown option" in res.stderr


def test_shell_fallback_asks_first(world):
    before = _snapshot(world["tmp"])
    res = _shell(world, stdin="n\n")
    assert res.returncode != 0
    assert _snapshot(world["tmp"]) == before


def _shell_env(world, **extra):
    return dict(os.environ, HOME=str(world["home"]), CODEBONE_UNINSTALL_SHELL_ONLY="1", **extra)


def test_shell_refuses_an_empty_relative_or_root_home(world):
    """--dry-run on purpose: a regression here must not be able to delete anything. "Library" exists below the cwd."""
    for bad in ("", "/", "Library"):
        res = subprocess.run(["/bin/bash", str(REPO / "uninstall.sh"), "--dry-run"], capture_output=True, text=True,
                             env=dict(_shell_env(world), HOME=bad), cwd=str(world["home"]), timeout=60)
        assert res.returncode == 2 and "refusing to run" in res.stderr, res.stdout + res.stderr
        assert res.stdout == ""


def test_shell_fallback_works_when_the_app_is_already_gone(world):
    """Only the script is left (downloaded on its own), the bundle was dragged to the Trash before."""
    lonely = world["tmp"] / "standalone" / "uninstall.sh"
    lonely.parent.mkdir()
    shutil.copy(REPO / "uninstall.sh", lonely)
    shutil.rmtree(world["bundle"])
    res = subprocess.run(["/bin/bash", str(lonely), "--yes"], capture_output=True, text=True,
                         env=_shell_env(world), cwd=str(world["tmp"]), timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Traceback" not in res.stderr and not world["support"].exists()
    assert not (world["home"] / ".cursor" / "mcp.json").exists()
    assert world["outside"].read_text() == "keep me"


def test_shell_fallback_is_as_careful_with_configs_as_the_module(world):
    home = world["home"]
    foreign = {"command": "npx", "args": ["-y", "pug-template-mcp"]}
    legacy = {"command": "/x/venv/bin/python3", "args": ["/x/src/pug_mcp/server.py"]}
    _json(world["desktop"], {"mcpServers": {"pug": foreign, "codebone": SERVER}})
    _json(home / ".cursor" / "mcp.json", {"mcpServers": {"pug": legacy, "keep": OTHER}})
    dot = _json(world["tmp"] / "dotfiles" / "gemini" / "mcp_config.json", {"mcpServers": {"codebone": SERVER}}).parent
    shutil.rmtree(home / ".gemini" / "config")
    (home / ".gemini" / "config").symlink_to(dot)
    undecodable = home / ".gemini" / "antigravity-ide" / "mcp_config.json"
    undecodable.write_bytes(b'{"mcpServers": {"codebone": {}, "n": "caf\xe9"}}')
    res = _shell(world, "--yes", "--keep-app")
    assert res.returncode == 0, res.stdout + res.stderr
    assert json.loads(world["desktop"].read_text())["mcpServers"] == {"pug": foreign}
    assert json.loads((home / ".cursor" / "mcp.json").read_text()) == {"mcpServers": {"keep": OTHER}}
    assert (home / ".gemini" / "config").is_symlink() and dot.is_dir() and not (dot / "mcp_config.json").exists()
    assert undecodable.read_bytes() == b'{"mcpServers": {"codebone": {}, "n": "caf\xe9"}}'
    assert "not valid JSON" in res.stdout
    assert "only codebone's own MCP entries" in res.stdout  # the legacy project files were edited


def test_shell_project_that_is_the_home_directory_is_handled_once(world):
    home = world["home"]
    _json(world["support"] / "config.json", {"project_path": str(home), "recent_projects": [str(home)]})
    res = _shell(world, "--dry-run")
    assert res.returncode == 0, res.stderr
    assert res.stdout.count(f"{home / '.cursor' / 'mcp.json'}") == 1


def test_shell_login_items_are_matched_by_bundle_id(world):
    agents = world["lib"] / "LaunchAgents"
    mine = [_write(agents / n, "agent") for n in ("com.codebone.app.login.plist", "com.pug.app-helper.plist")]
    keep = [_write(agents / n, "keep") for n in ("com.pug.helper.plist", "com.codebone.other.plist", "com.pugs.app.plist")]
    assert _shell(world, "--yes", "--keep-app").returncode == 0
    assert not any(os.path.lexists(p) for p in mine) and all(p.exists() for p in keep)


def test_shell_removes_read_only_trees(world):
    locked = _write(world["support"] / "scans" / "locked" / "x.sqlite3")
    os.chmod(locked.parent, 0o500)
    res = _shell(world, "--yes", "--keep-app")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not world["support"].exists()


def test_shell_process_pattern_matches_launchers_but_not_editors():
    script = (REPO / "uninstall.sh").read_text(encoding="utf-8")
    pattern = re.search(r"^PROC_RE='(.*)'$", script, re.M).group(1)
    app = "/Applications/codebone.app/Contents"
    mine = [
        f"{app}/MacOS/codebone",
        f"{app}/Resources/venv/bin/python3 {app}/Resources/src/codebone_main.py",
        "/Users/x/Library/Application Support/codebone/venv/bin/python3 -m codebone_mcp.server",
        "python3 -m pug_mcp.server", "/usr/bin/python3 pug_main.py",
        "node /opt/homebrew/lib/node_modules/codebone-mcp/bin/codebone-mcp.js", "node /opt/homebrew/bin/npm exec codebone-mcp",
        "/Users/x/Other Place/PUG.app/Contents/MacOS/PUG",
    ]
    others = [
        "vim codebone_main.py", "/usr/bin/vim codebone_mcp/server.py", "/usr/bin/grep -r codebone-mcp .",
        "/usr/bin/grep codebone-mcp-notes", "/usr/bin/tail -f /Users/x/Library/Logs/codebone/codebone.log", "vim notes.txt",
    ]
    lines = [f"{i + 100:>6} {1:>5} {cmd}" for i, cmd in enumerate(mine + others)]
    out = subprocess.run(["grep", "-E", pattern], input="\n".join(lines) + "\n", capture_output=True, text=True).stdout
    assert out.splitlines() == lines[: len(mine)]
