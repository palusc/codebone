from src.imports import import_edges, sql_tables


def test_python_and_js_imports(tmp_path):
    files = {"pkg/a.py": "from .b import x\nimport pkg.c\n", "pkg/b.py": "", "pkg/c.py": "",
             "web/app.ts": "import { f } from './lib/util'\n", "web/lib/util.ts": ""}
    for rel, code in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(code)
    got = {(e["from"], e["to"]) for e in import_edges(str(tmp_path), list(files))}
    assert got == {("pkg/a.py", "pkg/b.py"), ("pkg/a.py", "pkg/c.py"), ("web/app.ts", "web/lib/util.ts")}


def test_sql_tables_mixed_ddl_ctas_and_prose():
    text = (
        "CREATE TABLE audit_log (id int);\n"
        "CREATE TABLE report AS SELECT * FROM audit_log;\n"
        "CREATE OR REPLACE TABLE mv_totals AS(SELECT 1);\n"
        "CREATE TEMP TABLE tmp_batch (id int);\n"
        "CREATE TABLE IF NOT EXISTS public.events (name text);\n"
        "CREATE TABLE ONLY invoices (id int);\n"
        "Create table backups as needed for the report\n"
    )
    got = sql_tables(text)
    # every real DDL spelling counts: column paren, CTAS, AS(, OR REPLACE, TEMP, ONLY, qualified
    assert {"audit_log", "report", "mv_totals", "tmp_batch", "events", "invoices"} <= set(got)
    # prose never does: "backups" would match a bare " AS " alternation, stopwords are dropped
    assert not ({"backups", "for", "the", "public"} & set(got))
