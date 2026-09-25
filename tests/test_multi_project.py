"""Multi-folder workspace: the config queue, and scanning every folder one after another while the
active project is restored from its snapshot at the end."""
from pathlib import Path

from src.config import Config
from src.providers import FastFallbackProvider
from src.service import CodeBoneService


def test_old_config_seeds_the_workspace_from_project_path(tmp_path):
    """Configs written before the workspace existed start with their known folder in it."""
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text('{"project_path": "/somewhere/proj"}')

    cfg = Config(cfg_dir / "config.json")
    assert [str(p) for p in cfg.project_paths] == [str(Path("/somewhere/proj").resolve())]


def test_setting_the_active_project_joins_the_workspace(tmp_path):
    """Every writer of project_path (menu, MCP adopt, first run) lands in the scan queue."""
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()

    cfg.set("project_path", str(a))
    cfg.set("project_path", str(b))
    cfg.set("project_path", str(b))  # re-activating must not duplicate the folder

    assert [str(p) for p in cfg.project_paths] == [str(a.resolve()), str(b.resolve())]


def test_add_and_remove_workspace_folders(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()

    cfg.add_project_path(str(a))
    cfg.add_project_path(str(a))  # duplicates collapse
    cfg.add_project_path(str(b))
    assert [str(p) for p in cfg.project_paths] == [str(a.resolve()), str(b.resolve())]

    cfg.remove_project_path(str(a))
    assert [str(p) for p in cfg.project_paths] == [str(b.resolve())]
    # A folder that leaves the workspace stays out across reloads
    assert [str(p) for p in Config(cfg.config_file).project_paths] == [str(b.resolve())]


def test_scan_all_projects_scans_each_folder_and_restores_the_active_one(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "one.py").write_text("def one(): pass\n")
    (b / "two.py").write_text("def two(): pass\n")

    cfg.add_project_path(str(a))
    cfg.add_project_path(str(b))
    cfg.set("project_path", str(a))
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()

    try:
        results = svc.scan_all_projects()
        assert [Path(r["project_path"]).name for r in results] == ["a", "b"]
        assert results[0]["total"] == 1 and results[1]["total"] == 1

        # The project that was active before the pass is active again — and serves its own rows,
        # not the last-scanned folder's
        assert cfg.project_path == a.resolve()
        assert [f["path"] for f in svc.storage.all_files()] == ["one.py"]

        # Both folders left a rolling snapshot behind, so switching is an adopt instead of a rescan
        assert svc.scans.find_matching_scan(a) is not None
        assert svc.scans.find_matching_scan(b) is not None

        # A second pass is idempotent: same folders scanned, same active project at the end
        again = svc.scan_all_projects()
        assert [Path(r["project_path"]).name for r in again] == ["a", "b"]
        assert all(r["total"] == 1 for r in again)
        assert cfg.project_path == a.resolve()
        assert [f["path"] for f in svc.storage.all_files()] == ["one.py"]
    finally:
        svc.close()


def test_scan_all_projects_skips_missing_folders(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    present = tmp_path / "here"
    present.mkdir()
    (present / "x.py").write_text("x = 1\n")
    cfg.add_project_path(str(present))
    cfg.add_project_path(str(tmp_path / "unmounted-volume"))
    cfg.set("project_path", str(present))

    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    try:
        results = svc.scan_all_projects()
        assert [Path(r["project_path"]).name for r in results] == ["here"]
        assert cfg.project_path == present.resolve()
    finally:
        svc.close()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_setting_the_active_project_joins_the_workspace(Path(d))
    print("multi-project tests passed")
