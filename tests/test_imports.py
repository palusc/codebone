from src.imports import import_edges


def test_python_and_js_imports(tmp_path):
    files = {"pkg/a.py": "from .b import x\nimport pkg.c\n", "pkg/b.py": "", "pkg/c.py": "",
             "web/app.ts": "import { f } from './lib/util'\n", "web/lib/util.ts": ""}
    for rel, code in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(code)
    got = {(e["from"], e["to"]) for e in import_edges(str(tmp_path), list(files))}
    assert got == {("pkg/a.py", "pkg/b.py"), ("pkg/a.py", "pkg/c.py"), ("web/app.ts", "web/lib/util.ts")}
