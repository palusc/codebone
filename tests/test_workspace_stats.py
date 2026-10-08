"""Workspace-wide stats: the menu HUD counts every workspace folder — the live index for the active
project, its rolling scan snapshot for the others, never a fake zero."""
from src.config import Config
from src.providers import FastFallbackProvider
from src.service import CodeBoneService


def make(tmp_path, *names):
    cfg = Config(tmp_path / "cfg" / "config.json")
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    paths = []
    for n in names:
        p = tmp_path / n
        p.mkdir()
        paths.append(p)
    return svc, paths


def test_workspace_stats_counts_every_scanned_project(tmp_path):
    svc, (a, b) = make(tmp_path, "a", "b")
    (a / "one.py").write_text("def one(): pass\n")
    (b / "two.py").write_text("def two(): pass\n")
    svc.config.add_project_path(str(a))
    svc.config.add_project_path(str(b))

    svc.config.set("project_path", str(a))
    svc.rescan_all()          # a indexed and snapshotted
    svc.config.set("project_path", str(b))
    svc.rescan_all()          # b is active now; a's rows are gone from the live index

    stats = svc.workspace_stats()
    by_name = {p["name"]: p for p in stats["projects"]}
    assert set(by_name) == {"a", "b"}
    assert by_name["b"]["active"] is True
    assert by_name["a"]["active"] is False
    assert by_name["a"]["nodes"] == 1, "a must be counted from its snapshot although b is the live index"
    assert by_name["b"]["nodes"] == 1
    assert stats["total_nodes"] == 2


def test_workspace_stats_refresh_when_the_index_changes(tmp_path):
    svc, (a,) = make(tmp_path, "a")
    (a / "one.py").write_text("def one(): pass\n")
    svc.config.add_project_path(str(a))
    svc.config.set("project_path", str(a))
    svc.rescan_all()
    assert svc.workspace_stats()["total_nodes"] == 1

    (a / "two.py").write_text("def two(): pass\n")
    svc.rescan_all()
    assert svc.workspace_stats()["total_nodes"] == 2, "the cached totals must follow the live index"


def test_workspace_stats_ignores_folders_that_left_the_disk(tmp_path):
    svc, (a, gone) = make(tmp_path, "a", "gone")
    (a / "one.py").write_text("def one(): pass\n")
    svc.config.add_project_path(str(a))
    svc.config.add_project_path(str(gone))
    svc.config.set("project_path", str(a))
    svc.rescan_all()
    gone.rmdir()

    stats = svc.workspace_stats()
    assert [p["name"] for p in stats["projects"]] == ["a"]
    assert stats["total_nodes"] == 1


def test_scan_progress_names_the_project_being_scanned(tmp_path):
    """During a multi-project scan the HUD must say which folder the numbers belong to."""
    svc, (a,) = make(tmp_path, "a")
    (a / "one.py").write_text("def one(): pass\n")
    svc.config.add_project_path(str(a))
    svc.config.set("project_path", str(a))

    seen = []
    svc.rescan_all(on_progress=lambda cur, tot, f: seen.append(dict(svc.scan_progress or {})))
    assert seen and seen[0]["project"] == "a"


def test_project_tldr_can_summarize_an_inactive_workspace_snapshot(tmp_path):
    svc, (a, b) = make(tmp_path, "a", "b")
    (a / "one.py").write_text("def one(): pass\n")
    (b / "billing.py").write_text("class InvoiceModel: pass\n")
    svc.config.add_project_path(str(a))
    svc.config.add_project_path(str(b))
    svc.config.set("project_path", str(a))
    try:
        svc.scan_all_projects()
        result = svc.project_tldr("b")
        assert result["project"] == "b"
        assert result["file_count"] == 1
        assert "1-file software project" in result["text"]
        assert svc.config.project_path == a.resolve()
    finally:
        svc.close()
