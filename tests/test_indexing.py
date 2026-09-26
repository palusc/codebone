"""Indexing pipeline: project binding, deletions, unreadable folders, size limits, rows from the regex fallback."""
import json
import sqlite3
from pathlib import Path

from src import service as service_mod
from src.config import Config
from src.providers import FastFallbackProvider
from src.scans import ScanManager
from src.service import CodeBoneService
from src.storage import Storage


def make(tmp_path, name="proj"):
    proj = tmp_path / name
    proj.mkdir(exist_ok=True)
    cfg = Config(tmp_path / "cfg" / "config.json")
    cfg.set("project_path", str(proj))
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    return svc, proj.resolve()


def test_switching_projects_drops_the_previous_projects_rows(tmp_path):
    svc, a = make(tmp_path, "a")
    (a / "one.py").write_text("def one(): pass\n")
    svc.rescan_all()
    assert svc.storage.file_count() == 1

    b = tmp_path / "b"
    b.mkdir()
    (b / "two.py").write_text("def two(): pass\n")
    svc.config.set("project_path", str(b))
    svc.rescan_all()
    assert [f["path"] for f in svc.storage.all_files()] == ["two.py"]


def test_batch_removes_deleted_files_but_not_recreated_ones(tmp_path):
    svc, proj = make(tmp_path)
    gone, back = proj / "gone.py", proj / "back.py"
    gone.write_text("def g(): pass\n")
    back.write_text("def b(): pass\n")
    svc.rescan_all()
    gone.unlink()
    svc._handle_batch(set(), {gone, back})  # "back.py" still exists: a stale delete event must not drop it
    assert {f["path"] for f in svc.storage.all_files()} == {"back.py"}


def test_unreadable_project_root_does_not_wipe_the_index(tmp_path, monkeypatch):
    svc, proj = make(tmp_path)
    (proj / "keep.py").write_text("def k(): pass\n")
    svc.rescan_all()

    def boom(*a, **k):
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(service_mod, "list_watched_files", boom)
    assert svc.rescan_all() == (0, 0, 0)
    assert svc.storage.file_count() == 1
    assert "Cannot read project folder" in svc.last_error


def test_binary_and_oversized_files_are_catalogued_not_analysed(tmp_path):
    """A file too big or binary to read as code still gets a node in the map (the project isn't fully
    mapped without its assets), just catalogued by category/size instead of sniffed for tables/routes/events."""
    svc, proj = make(tmp_path)
    (proj / "blob.py").write_bytes(b"\x00\x01\x02" * 100)
    (proj / "huge.json").write_text('{"a": "' + "x" * 1_100_000 + '"}')
    (proj / "ok.py").write_text("def ok(): pass\n")
    svc.rescan_all()
    paths = sorted(f["path"] for f in svc.storage.all_files())
    assert paths == ["blob.py", "huge.json", "ok.py"]
    blob = svc.storage.get_file("blob.py")
    assert blob["tables"] == [] and blob["routes"] == [] and blob["events"] == []
    assert "binary" in blob["summary"]


def test_new_file_with_syntax_error_is_indexed_but_edits_keep_old_analysis(tmp_path):
    svc, proj = make(tmp_path)
    broken = proj / "new.py"
    broken.write_text("def broken(:\n")
    assert svc._sniff_file(broken, live=True) == "sniffed"  # never seen before: analyse it anyway
    before = svc.storage.get_file("new.py")["content_hash"]
    broken.write_text("def broken(:  # still typing\n")
    assert svc._sniff_file(broken, live=True) == "skipped"  # mid-edit: keep the last good analysis ...
    assert svc.storage.get_file("new.py")["content_hash"] == before
    service_mod.BROKEN_GRACE_SECONDS = 0.0
    try:
        assert svc._sniff_file(broken, live=True) == "sniffed"  # ... but not forever (JSONC, Python 2, templates)
    finally:
        service_mod.BROKEN_GRACE_SECONDS = 20.0
    assert svc._sniff_file(proj / "new.py") == "unchanged"


def test_forced_rescan_never_replaces_model_rows_with_regex_output(tmp_path):
    svc, proj = make(tmp_path)
    f = proj / "m.py"
    f.write_text("def m(): pass\n")
    svc.storage.update_file("m.py", "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: X\nFLOW: model summary here.",
                            mtime=1.0, content_hash="old", source="model")
    assert svc._sniff_file(f, force=True) == "skipped"
    assert svc.storage.get_file("m.py")["summary"] == "model summary here."


def test_touched_but_identical_file_refreshes_mtime_without_reanalysis(tmp_path):
    svc, proj = make(tmp_path)
    f = proj / "t.py"
    f.write_text("def t(): pass\n")
    svc._sniff_file(f)
    import os
    os.utime(f, (1_000_000_000, 1_000_000_000))
    assert svc._sniff_file(f) == "unchanged"
    assert svc.storage.get_file("t.py")["mtime"] == 1_000_000_000


def test_storage_cache_follows_writes_and_folds_case(tmp_path):
    s = Storage(tmp_path / "x.db")
    s.update_file("a.py", "TABLES: Invoice\nROUTES: none\nEVENTS: none\nDOMAINS: Billing\nFLOW: a")
    s.update_file("b.py", "TABLES: invoice\nROUTES: none\nEVENTS: none\nDOMAINS: billing\nFLOW: b")
    idx = s.entity_index()
    assert idx is s.entity_index()  # cached until the next write
    assert list(idx["tables"]) == ["Invoice"] and sorted(idx["tables"]["Invoice"]) == ["a.py", "b.py"]
    assert list(idx["domains"]) == ["Billing"]
    rev = s.revision
    s.remove_file("b.py")
    assert s.revision > rev and s.entity_index() is not idx


def test_corrupt_database_is_moved_aside_instead_of_crashing(tmp_path):
    db = tmp_path / "codebone.sqlite3"
    db.write_bytes(b"this is not a sqlite database" * 50)
    s = Storage(db)
    assert s.file_count() == 0
    assert list(tmp_path.glob("codebone.sqlite3.corrupt-*"))


def test_snapshot_is_one_rolling_file_per_project_and_export_never_overwrites(tmp_path):
    cfg = Config(tmp_path / "cfg" / "config.json")
    mgr = ScanManager(cfg)
    st = Storage(tmp_path / "live.db")
    st.update_file("a.py", "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: none\nFLOW: a")
    first = mgr.save_snapshot("proj", tmp_path / "proj", st)
    second = mgr.save_snapshot("proj", tmp_path / "proj", st)
    assert first["id"] == second["id"] and len(mgr.list_scans()) == 1

    out = tmp_path / "out.sqlite3"
    mgr.export_scan(first["id"], out)
    for bad, exc in ((out, FileExistsError), (tmp_path / "x.txt", ValueError)):
        try:
            mgr.export_scan(first["id"], bad)
        except exc:
            pass
        else:
            raise AssertionError(f"export to {bad} should have failed")


def test_foreign_database_is_opened_read_only(tmp_path):
    foreign = tmp_path / "other.sqlite3"
    con = sqlite3.connect(foreign)
    con.execute("CREATE TABLE unrelated (x)")
    con.commit()
    con.close()
    try:
        Storage(foreign, readonly=True).file_count()
    except sqlite3.OperationalError:
        pass  # no 'files' table: fine, and nothing was created in it
    con = sqlite3.connect(foreign)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master")]
    assert tables == ["unrelated"]


def test_files_outside_the_project_are_never_indexed_and_recreated_files_survive_a_scan(tmp_path):
    svc, proj = make(tmp_path)
    outside = tmp_path / "elsewhere" / "z.py"
    outside.parent.mkdir()
    outside.write_text("def z(): pass\n")
    assert svc._sniff_file(outside) == "skipped" and svc.storage.file_count() == 0

    f = proj / "a.py"
    f.write_text("def a(): pass\n")
    svc.rescan_all()
    svc.storage.set_mtime("a.py", 1.0)  # scan snapshot says: known file
    f.write_text("def a(): return 1\n")
    assert svc.rescan_all()[1] == 1 and svc.storage.get_file("a.py")


def test_rescan_drops_stale_rows_under_dependency_trees_that_still_exist(tmp_path):
    """Rows written by an older version that mapped node_modules must go away even though the files are
    still on disk — the walk never lists them any more, so existence alone must not keep them alive."""
    svc, proj = make(tmp_path)
    (proj / "keep.py").write_text("def k(): pass\n")
    dep = proj / "node_modules" / "dep" / "index.js"
    dep.parent.mkdir(parents=True)
    dep.write_text("module.exports = {}\n")
    svc.rescan_all()
    svc.storage.update_file("node_modules/dep/index.js",
                            "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: X\nFLOW: legacy row",
                            mtime=dep.stat().st_mtime, content_hash="old", source="regex")
    svc.rescan_all()
    assert [f["path"] for f in svc.storage.all_files()] == ["keep.py"]


def test_a_request_made_during_a_scan_gets_its_own_pass(tmp_path):
    import threading
    svc, proj = make(tmp_path)
    (proj / "a.py").write_text("def a(): pass\n")
    entered, release, passes = threading.Event(), threading.Event(), []
    original = svc._rescan_once

    def slow(on_progress, force):
        passes.append(1)
        entered.set()
        release.wait(2)
        return original(on_progress, force)

    svc._rescan_once = slow
    t = threading.Thread(target=svc.rescan_all)
    t.start()
    entered.wait(2)
    assert svc.rescan_all() == (0, 0, 0)  # busy: queued, not dropped
    release.set()
    t.join(5)
    assert len(passes) == 2
