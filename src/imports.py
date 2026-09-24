"""File-to-file import edges (Python, JS/TS), resolved against the indexed paths. Regex, not a parser: it
misses dynamic imports and aliased paths, but every edge it returns is a real reference."""
import os
import re
from pathlib import Path
from typing import Dict, List, Set

MAX_BYTES = 300_000
PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w, ()*]+)|import\s+([\w., ]+))", re.M)
JS_IMPORT = re.compile(r"""(?:from\s+|import\s+|require\(\s*|import\(\s*)['"](\.{1,2}/[^'"]*)['"]""")
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")


def _py_targets(rel: str, code: str, known: Set[str], by_mod: Dict[str, str]) -> Set[str]:
    out: Set[str] = set()
    pkg = rel.replace("\\", "/").split("/")[:-1]
    for m in PY_IMPORT.finditer(code):
        mods: List[str] = []
        if m.group(3):
            mods = [x.strip().split(" as ")[0] for x in m.group(3).split(",")]
        else:
            base, names = m.group(1), [n.strip() for n in m.group(2).strip("()").split(",")]
            dots = len(base) - len(base.lstrip("."))
            if dots:
                parent = pkg[: len(pkg) - (dots - 1)] if dots > 1 else pkg
                base = ".".join(parent + ([base.lstrip(".")] if base.lstrip(".") else []))
                if base in ("",):
                    base = ""
            mods = [base] + [f"{base}.{n.split(' as ')[0]}".lstrip(".") for n in names if n and n != "*"]
        for mod in mods:
            t = by_mod.get(mod)
            if t and t != rel and not t.endswith("__init__.py"):
                out.add(t)
    return out


def _js_targets(rel: str, code: str, known: Set[str]) -> Set[str]:
    out: Set[str] = set()
    folder = os.path.dirname(rel)
    for m in JS_IMPORT.finditer(code):
        p = os.path.normpath(os.path.join(folder, m.group(1))).replace("\\", "/")
        for cand in [p] + [p + e for e in JS_EXT] + [f"{p}/index{e}" for e in JS_EXT]:
            if cand in known and cand != rel:
                out.add(cand)
                break
    return out


def import_edges(root: str, paths: List[str]) -> List[dict]:
    known = set(paths)
    by_mod: Dict[str, str] = {}
    for p in paths:
        if p.endswith(".py"):
            parts = p[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):  # every suffix, so src/pkg/a.py also answers to "pkg.a" and "a"
                by_mod.setdefault(".".join(parts[i:]), p)
    edges = []
    for rel in sorted(paths):
        ext = os.path.splitext(rel)[1]
        if ext != ".py" and ext not in JS_EXT:
            continue
        try:
            fp = Path(root) / rel
            if fp.stat().st_size > MAX_BYTES:
                continue
            code = fp.read_text(errors="ignore")
        except OSError:
            continue
        targets = _py_targets(rel, code, known, by_mod) if ext == ".py" else _js_targets(rel, code, known)
        edges += [{"from": rel, "to": t, "type": "import", "entity": "import"} for t in sorted(targets)]
    return edges
