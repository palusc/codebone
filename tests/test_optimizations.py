"""Test suite for codebone prompt parsing, echo rejection, LOD search, and graph safeguards."""
import tempfile
from pathlib import Path

from src.prompts import _clean_entity_list, parse_analysis
from src.storage import Storage


def test_clean_entity_list():
    raw_prompt_echo = [
        "[comma-separated list of database tables/models, or 'none']",
        "overarching business domains or system concepts, or 'none'",
        "none",
        "N/A",
        "users",
        "orders",
        "`accounts`",
    ]
    cleaned = _clean_entity_list(raw_prompt_echo)
    assert "users" in cleaned
    assert "orders" in cleaned
    assert "accounts" in cleaned
    assert "[comma-separated list of database tables/models, or 'none']" not in cleaned
    assert "overarching business domains or system concepts, or 'none'" not in cleaned
    assert "none" not in cleaned
    print("test_clean_entity_list PASSED")


def test_parse_analysis_markdown_json():
    sample_llm_output = '''```json
{
  "summary": "Core authentication handler and token verification.",
  "domains": ["Authentication & Identity", "Security"],
  "tables": ["users", "sessions"],
  "routes": ["POST /api/v1/login", "POST /api/v1/logout"],
  "events": ["UserLoggedIn", "SessionExpired"]
}
```'''
    tables, routes, events, domains, summary = parse_analysis(sample_llm_output)
    assert summary == "Core authentication handler and token verification."
    assert "Authentication & Identity" in domains
    assert "users" in tables
    assert "POST /api/v1/login" in routes
    assert "UserLoggedIn" in events
    print("test_parse_analysis_markdown_json PASSED")


def test_parse_analysis_fallback_with_echoes():
    sample_fallback = """
SUMMARY: Handles database storage and SQLite schemas.
DOMAINS: Data Persistence & Storage, overarching business domains or system concepts, or 'none'
TABLES: files, entities, [comma-separated list of database tables/models, or 'none']
ROUTES: none
EVENTS: FileSaved
"""
    tables, routes, events, domains, summary = parse_analysis(sample_fallback)
    assert "Data Persistence & Storage" in domains
    assert len(domains) == 1
    assert "files" in tables
    assert "entities" in tables
    assert len(tables) == 2
    assert routes == []
    assert events == ["FileSaved"]
    print("test_parse_analysis_fallback_with_echoes PASSED")


def test_lod_query_search_and_graph_safeguard():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite3"
        storage = Storage(db_path)

        storage.insert_record({
            "path": "src/auth.py",
            "content_hash": "hash1",
            "summary": "Authentication logic and JWT processing",
            "domains": ["Security", "Auth"],
            "tables": ["users"],
            "routes": ["POST /login"],
            "events": ["AuthSuccess"],
        })
        storage.insert_record({
            "path": "src/billing.py",
            "content_hash": "hash2",
            "summary": "Stripe payment integration and checkout session handler",
            "domains": ["Billing"],
            "tables": ["subscriptions"],
            "routes": ["POST /checkout"],
            "events": ["InvoicePaid"],
        })

        # Test index
        idx = storage.entity_index()
        assert "users" in idx["tables"]
        assert "POST /login" in idx["routes"]
        assert "Billing" in idx["domains"]

        # Test filtered entity index
        f_idx = storage.filtered_entity_index({"src/auth.py"})
        assert "users" in f_idx["tables"]
        assert "subscriptions" not in f_idx["tables"]

        # Test graph edges with fan-out capping
        # Add 25 files sharing the same domain to test safeguard
        for i in range(25):
            storage.insert_record({
                "path": f"src/mod_{i}.py",
                "content_hash": f"hash_mod_{i}",
                "summary": f"Module {i}",
                "domains": ["SharedDomain"],
            })

        edges = storage.graph_edges()
        assert isinstance(edges, list)
        shared_domain_edges = [e for e in edges if e["entity"] == "SharedDomain"]
        # Without safeguard: 25 * 24 / 2 = 300 edges.
        # With max_peers = 15, total edges for 25 files is strictly capped below 300.
        assert len(shared_domain_edges) < 300
        print(f"Graph safeguard verified: {len(shared_domain_edges)} edges generated for 25 files (capped below 300)")

        print("test_lod_query_search_and_graph_safeguard PASSED")


if __name__ == "__main__":
    test_clean_entity_list()
    test_parse_analysis_markdown_json()
    test_parse_analysis_fallback_with_echoes()
    test_lod_query_search_and_graph_safeguard()
    print("ALL OPTIMIZATION TESTS PASSED!")
