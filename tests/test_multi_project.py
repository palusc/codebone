"""Multi-folder workspace: isolated parallel scans, rolling snapshots and active-project preservation."""
import threading
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
        assert set(cfg.recent_scanned_projects[:2]) == {str(a.resolve()), str(b.resolve())}

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


def test_scan_all_projects_does_not_undo_a_newer_project_switch(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b, chosen = tmp_path / "a", tmp_path / "b", tmp_path / "chosen"
    for p in (a, b, chosen):
        p.mkdir()
        (p / "one.py").write_text("x = 1\n")

    cfg.add_project_path(str(a))
    cfg.add_project_path(str(b))
    cfg.set("project_path", str(a))
    started = threading.Event()
    release = threading.Event()

    class BlockingProvider(FastFallbackProvider):
        def sniff(self, file_path, code):
            started.set()
            release.wait(timeout=3)
            return super().sniff(file_path, code)

    svc = CodeBoneService(cfg)
    svc.provider = BlockingProvider()
    try:
        scan = threading.Thread(target=svc.scan_all_projects)
        scan.start()
        assert started.wait(timeout=3)
        cfg.set("project_path", str(chosen))
        release.set()
        scan.join(timeout=5)
        assert not scan.is_alive()
        assert cfg.project_path == chosen.resolve()
    finally:
        release.set()
        svc.close()


def test_workspace_projects_are_actually_scanned_in_parallel(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b = tmp_path / "a", tmp_path / "b"
    for p in (a, b):
        p.mkdir()
        (p / "one.py").write_text("def one(): pass\n")
        cfg.add_project_path(str(p))
    cfg.set("project_path", str(a))

    class ConcurrentProvider(FastFallbackProvider):
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()
            self.gate = threading.Barrier(2)

        def sniff(self, file_path, code):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                self.gate.wait(timeout=3)
                return super().sniff(file_path, code)
            finally:
                with self.lock:
                    self.active -= 1

    svc = CodeBoneService(cfg)
    provider = ConcurrentProvider()
    svc.provider = provider
    try:
        results = svc.scan_all_projects()
        assert all(not result.get("error") for result in results)
        assert provider.max_active == 2
    finally:
        svc.close()


def test_direct_project_scan_restores_the_active_project(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    active, target = tmp_path / "active", tmp_path / "target"
    active.mkdir()
    target.mkdir()
    (active / "active.py").write_text("x = 1\n")
    (target / "first.py").write_text("x = 1\n")
    cfg.add_project_path(str(active))
    cfg.add_project_path(str(target))
    cfg.set("project_path", str(active))
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    try:
        svc.rescan_all()
        (target / "second.py").write_text("y = 2\n")

        result = svc.scan_project(target)

        assert result["total"] == 2
        assert cfg.project_path == active.resolve()
        assert [f["path"] for f in svc.storage.all_files()] == ["active.py"]
        target_stats = next(p for p in svc.workspace_stats()["projects"] if p["path"] == str(target.resolve()))
        assert target_stats["nodes"] == 2
        assert cfg.recent_scanned_projects[0] == str(target.resolve())
    finally:
        svc.close()


def test_activate_project_restores_its_map_without_rescanning(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    a, b = tmp_path / "a", tmp_path / "b"
    for project, filename in ((a, "a.py"), (b, "b.py")):
        project.mkdir()
        (project / filename).write_text("x = 1\n")
        cfg.add_project_path(str(project))
    cfg.set("project_path", str(a))
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    try:
        svc.scan_all_projects()
        (b / "not_scanned_yet.py").write_text("y = 2\n")

        svc.activate_project(b)

        assert cfg.project_path == b.resolve()
        assert [f["path"] for f in svc.storage.all_files()] == ["b.py"]
        assert svc.watching
    finally:
        svc.close()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_setting_the_active_project_joins_the_workspace(Path(d))
    print("multi-project tests passed")
