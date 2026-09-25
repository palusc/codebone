"""File filtering, tree walking, battery cache, debounce and config persistence."""
import os
import time
from pathlib import Path

import pytest

from src import battery, watcher
from src.config import Config, is_watched_file, list_watched_files


def test_ignore_rules_only_look_inside_the_project(tmp_path):
    # codebone maps every real project file now, including node_modules — but a directory the project
    # merely happens to live under (here "build", an ancestor of proj) must never affect what's ignored.
    proj = tmp_path / "build" / "app"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.py").write_text("x = 1\n")
    (proj / "node_modules" / "dep").mkdir(parents=True)
    (proj / "node_modules" / "dep" / "b.py").write_text("x = 1\n")
    found = list_watched_files(proj)
    assert sorted(p.name for p in found) == ["a.py", "b.py"]


def test_secret_and_junk_names_are_still_nodes(tmp_path):
    for name in (".env", "prod.env", ".env.local", "id_rsa", "server.pem", "credentials.json", "secrets.yaml",
                 "app.min.js", "._a.py", "bundle.js.map"):
        (tmp_path / name).write_text("SECRET=1\n")
    (tmp_path / "ok.py").write_text("x = 1\n")
    assert len(list_watched_files(tmp_path)) == 11  # content is not read, see service._path_only


def test_deleted_files_are_recognised_by_name_alone(tmp_path):
    gone = tmp_path / "gone.py"
    assert not is_watched_file(gone, project_path=tmp_path)  # does not exist
    assert is_watched_file(gone, project_path=tmp_path, check_exists=False)
    assert is_watched_file(tmp_path / "gone.png", project_path=tmp_path, check_exists=False)


def test_symlink_leading_outside_the_project_is_rejected(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "link.py").symlink_to(outside)
    assert list_watched_files(proj) == []


def test_unlistable_root_raises_instead_of_looking_empty(tmp_path):
    with pytest.raises(OSError):
        list_watched_files(tmp_path / "missing")


def test_gitignore_is_not_applied(tmp_path):
    from src.config import load_gitignore_spec
    (tmp_path / ".gitignore").write_text("generated/\n*.tmp.py\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "g.py").write_text("x = 1\n")
    (tmp_path / "a.tmp.py").write_text("x = 1\n")
    (tmp_path / "keep.py").write_text("x = 1\n")
    found = list_watched_files(tmp_path, gitignore_spec=load_gitignore_spec(tmp_path))
    assert sorted(p.name for p in found) == [".gitignore", "a.tmp.py", "g.py", "keep.py"]


def test_battery_state_is_cached(monkeypatch):
    calls = []

    class R:
        stdout = "Now drawing from 'Battery Power'"

    monkeypatch.setattr(battery.subprocess, "run", lambda *a, **k: calls.append(1) or R())
    battery._cached_at = 0.0
    assert battery.on_battery_power() is True
    for _ in range(50):
        battery.on_battery_power()
    assert len(calls) == 1


def test_debounce_flushes_even_while_events_keep_arriving(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, "DEBOUNCE_SECONDS", 0.05)
    monkeypatch.setattr(watcher, "on_battery_power", lambda: False)
    monkeypatch.setattr(watcher._SnifferHandler, "MAX_WAIT_FACTOR", 4)
    batches = []
    h = watcher._SnifferHandler(lambda p: None, lambda p: None, {".py"}, set(),
                                on_batch=lambda c, d: batches.append((set(c), set(d))), project_path=tmp_path)
    try:
        for i in range(30):  # one event every 20 ms: the quiet period is never reached
            h._record(changed=tmp_path / f"f{i}.py")
            time.sleep(0.02)
        assert batches, "a steady stream of events must not starve indexing"
    finally:
        h.close()


def test_config_is_private_and_a_corrupt_file_is_kept(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(path)
    cfg.set("brain_cloud_api_key", "sk-secret")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    path.write_text("{ not json")
    Config(path)
    assert list(tmp_path.glob("config.json.corrupt-*"))


def test_project_path_is_resolved(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    cfg = Config(tmp_path / "config.json")
    cfg.set("project_path", str(link))
    assert cfg.project_path == real.resolve()


def test_more_secret_shaped_files_and_credential_directories_are_skipped(tmp_path):
    for name in ("service-account.json", "serviceAccountKey.json", "client_secret_123.json", "auth.json", "token.json",
                 "secrets.py", "passwords.txt", "deploy_keys.txt"):
        (tmp_path / name).write_text("x = 1\n")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "db.py").write_text("x = 1\n")
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config.txt").write_text("Host x\n")
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").symlink_to(tmp_path / ".env")  # a harmless-looking link to a secret
    (tmp_path / "app.py").write_text("x = 1\n")
    # All files are listed as watched nodes; content reading is skipped at sniff time
    assert len(list_watched_files(tmp_path)) == 13
