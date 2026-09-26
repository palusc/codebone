"""Read-time source facts: content records, call/import edges and derived entities, no rescan."""
from pathlib import Path

from src import context_format as cf
from src.imports import source_facts
from src.storage import Storage


def _fixture_project(root: Path) -> dict:
    files = {
        "app/api/subs/route.ts": "export async function POST() { await supabase.from('customers').select(); }\n",
        "app/subs/page.tsx": "import { fmt } from '@/lib/util'\nexport default function P() { fetch('/api/subs') }\n",
        "lib/util.ts": "export const fmt = (x) => x\n",
        "README.md": "# Fixture <b>Project</b>\nintro text\n",
        "secrets.json": '{"leaked": 1}',
    }
    for rel, code in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)
    return files


def _seed(s: Storage):
    s.insert_record({"path": "app/api/subs/route.ts", "summary": "Creates subscriptions.",
                     "tables": [], "routes": [], "events": [], "domains": ["Billing"]})
    s.insert_record({"path": "app/subs/page.tsx", "summary": "Shows the pricing page.",
                     "tables": [], "routes": [], "events": [], "domains": ["Billing"]})
    s.insert_record({"path": "lib/db.ts", "summary": "Database helpers.",
                     "tables": ["customers"], "routes": [], "events": [], "domains": ["Data"]})
    s.insert_record({"path": "lib/util.ts", "summary": "Formatting helpers.",
                     "tables": [], "routes": [], "events": [], "domains": ["Utilities"]})
    s.insert_record({"path": "README.md", "summary": "",
                     "tables": [], "routes": [], "events": [], "domains": []})
    s.insert_record({"path": "secrets.json", "summary": "",
                     "tables": [], "routes": [], "events": [], "domains": []})


def test_source_facts_join_content_and_edges(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    disk_files = _fixture_project(root)
    s = Storage(tmp_path / "idx.db")
    _seed(s)
    s.set_meta("project_path", str(root))

    facts = source_facts(str(root), list(disk_files), {"README.md", "secrets.json"})
    imports = {(e["from"], e["to"]) for e in facts["imports"]}
    assert ("app/subs/page.tsx", "lib/util.ts") in imports  # @/ alias resolved
    assert facts["calls"] == [{"from": "app/subs/page.tsx", "to": "app/api/subs/route.ts",
                               "type": "call", "entity": "/api/subs"}]
    assert facts["tables"]["app/api/subs/route.ts"] == ["customers"]
    assert facts["routes"]["app/api/subs/route.ts"] == ["POST /api/subs"]
    assert facts["roles"]["app/api/subs/route.ts"] == "route POST /api/subs"
    assert facts["roles"]["app/subs/page.tsx"] == "page /subs"
    assert facts["content"]["README.md"] == "Markdown: Fixture Project"  # sanitised at build: no <b>
    assert facts["content"]["secrets.json"] == "JSON file"  # secret boundary: labelled, never parsed

    files, index = s.view()
    by = {f["path"]: f for f in files}
    assert by["app/api/subs/route.ts"]["tables"] == ["customers"]
    assert by["app/api/subs/route.ts"]["role"] == "route POST /api/subs"
    assert by["app/subs/page.tsx"]["calls"] == [["/api/subs", "app/api/subs/route.ts"]]
    assert by["README.md"]["content"] == "Markdown: Fixture Project"

    edges = s.graph_edges()
    assert {"import", "call", "table"} <= {e["type"] for e in edges}

    text = cf.overview("p", files, index)
    assert "- README.md: Markdown: Fixture Project" in text
    hit = cf.search("p", files, index, query="pricing")
    assert "Calls: /api/subs -> app/api/subs/route.ts (tables: customers)" in hit


def test_without_project_path_no_facts_no_edges(tmp_path):
    s = Storage(tmp_path / "idx.db")
    _seed(s)
    assert s.source_facts() == {}
    assert s.graph_edges() == []


def test_template_fetch_keeps_depth_and_matches_deep_handler(tmp_path):
    """/api/users/${id}/posts must reach the posts handler, not collapse to the static parent."""
    files = {
        "app/api/users/route.ts": "export async function GET() {}\n",
        "app/api/users/[id]/route.ts": "export async function GET() {}\n",
        "app/api/users/[id]/posts/route.ts": "export async function GET() {}\n",
        "app/page.tsx": "export default function P() { return fetch(`/api/users/${id}/posts`) }\n",
    }
    for rel, code in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)
    facts = source_facts(str(tmp_path), list(files))
    assert facts["calls"] == [{"from": "app/page.tsx", "to": "app/api/users/[id]/posts/route.ts",
                               "type": "call", "entity": "/api/users/[*]/posts"}]


def test_sql_row_scrubs_phantom_and_keeps_regex_invisible_tables(tmp_path):
    """A .sql row unions with the derived list: old-regex junk ('public.phantom') dies, a stored
    TEMP table the regex cannot see survives."""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001_init.sql").write_text("CREATE TABLE jobs (id int);\n")
    s = Storage(tmp_path / "idx.db")
    s.insert_record({"path": "migrations/001_init.sql", "summary": "Init DDL.",
                     "tables": ["jobs", "tmp_batch", "public.phantom", "for"], "routes": [],
                     "events": [], "domains": []})
    s.set_meta("project_path", str(tmp_path))
    files, index = s.view()
    row = next(f for f in files if f["path"] == "migrations/001_init.sql")
    assert row["tables"] == ["jobs", "tmp_batch"]      # derived + real stored; junk scrubbed
    assert "public.phantom" not in index["tables"] and "for" not in index["tables"]


def test_route_and_page_entities_are_sanitised(tmp_path):
    files = {"app/<img src=x onerror=alert(1)>/route.ts": "export async function GET() {}\n"}
    for rel, code in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)
    facts = source_facts(str(tmp_path), list(files))
    assert facts["routes"] and "<" not in facts["routes"][list(facts["routes"])[0]][0]
    assert "<" not in facts["roles"][list(facts["roles"])[0]]
