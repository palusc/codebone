from pathlib import Path

from src import permissions


def test_protected_user_folder_detection(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setattr(permissions.Path, "home", lambda: home)

    assert permissions.is_protected_user_folder(home / "Desktop" / "project")
    assert permissions.is_protected_user_folder(home / "Documents")
    assert not permissions.is_protected_user_folder(tmp_path / "work" / "project")


def test_full_disk_access_probe_never_leaks_contents(monkeypatch):
    class Probe:
        def open(self, mode):
            assert mode == "rb"
            raise PermissionError("denied")

    monkeypatch.setattr(permissions, "Path", lambda _: Probe())
    assert permissions.has_full_disk_access() is False
