import json

from src import server
from src.providers import FastFallbackProvider
from src.storage import Storage

NOISY = "def handle_payload(token, query, config):\n    # api env\n    return {}\n"


def test_fallback_does_not_tag_every_file_with_every_domain():
    out = FastFallbackProvider().sniff("src/m1/plain.py", NOISY)
    assert "Payment & Billing" not in out and "Authentication & Identity" not in out


def test_fallback_summary_lists_constants_for_query_search():
    out = FastFallbackProvider().sniff("utils/calc2.py", "VAT = 0.19\n\ndef tot(items):\n    return 1\n")
    assert "VAT" in out


def test_graph_edges_skip_domain_pairs_by_default(tmp_path):
    s = Storage(tmp_path / "x.db")
    for i in range(20):
        s.update_file(f"f{i}.py", "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: Core\nFLOW: x")
    assert s.graph_edges() == []
    assert len(s.graph_edges(include_domains=True)) > 0


def test_patch_mcp_configs_never_clobbers_unparseable_config(tmp_path, monkeypatch):
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: tmp_path))
    cfg = tmp_path / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"mcpServers": {"other": {}}, // user comment\n}')
    before = cfg.read_text()
    server.patch_mcp_configs(8053)
    assert cfg.read_text() == before


def test_hybrid_edges_star_for_big_groups_and_directory_orphans(tmp_path):
    s = Storage(tmp_path / "x.db")
    s.set_meta("project_path", str(tmp_path))
    # 40 files on one table: a star is 39 edges, the old peer window spent ~6 per file and the
    # global cap then truncated whatever came next.
    for i in range(40):
        s.update_file(f"svc/m{i}.py", "TABLES: users\nROUTES: none\nEVENTS: none\nDOMAINS: none\nFLOW: x")
    # docs share no entity with anyone: the directory fallback links the orphan to its neighbour.
    s.update_file("docs/guide.py", "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: none\nFLOW: x")
    s.update_file("docs/other.md", "TABLES: none\nROUTES: none\nEVENTS: none\nDOMAINS: none\nFLOW: x")
    edges = s.graph_edges()
    star = [e for e in edges if e["entity"] == "users"]
    assert len(star) == 39
    assert len({e["from"] for e in star} | {e["to"] for e in star}) == 40
    paths = [e for e in edges if e["type"] == "path"]
    assert len(paths) == 1 and paths[0]["entity"] == "docs"
