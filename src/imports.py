"""File-to-file import edges plus read-time source facts: import/call edges, derived tables and
routes, path roles and one-line content records for rows whose stored summary is empty. Regex,
not a parser: it misses dynamic imports and composed URLs, but every fact it returns is a real
reference. Everything here is derived on read, so an existing index upgrades without a rescan."""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import GLOBAL_IGNORED_DIRS, _is_secret_or_junk, is_watched_file
from .prompts import sanitize_text

MAX_BYTES = 300_000
PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w, ()*]+)|import\s+([\w., ]+))", re.M)
JS_IMPORT = re.compile(r"""(?:from\s+|import\s+|require\(\s*|import\(\s*)['"](\.{1,2}/[^'"]*)['"]""")
ALIAS_IMPORT = re.compile(r"""(?:from\s+|import\s+|require\(\s*|import\(\s*)['"]([@#~]/[^'"]*)['"]""")
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
ROUTE_FILES = {"route.ts", "route.js", "route.mjs", "route.cjs"}
PAGE_FILES = {"page.tsx", "page.ts", "page.jsx", "page.js"}

FETCH = re.compile(r"""\b(?:fetch|apiFetch|publicFetch|axios(?:\.\w+)?)\s*\(\s*[`'"](/api/[^`'"\s?]+)""")
FROM = re.compile(r"""\.from\(\s*['"]([A-Za-z_][\w]*)['"]""")
VERB_FN = re.compile(r"export\s+(?:default\s+)?(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b")
VERB_CONST = re.compile(r"export\s+const\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*(?:=|:)")

# Schema-qualified names, guarded against prose: CREATE needs the column paren that real DDL has,
# every form drops SQL keywords as names ("Create table for ..." never means a table "for").
_DDL_NAME = r"['\"`]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)['\"`]?"
CREATE_SQL = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _DDL_NAME + r"\s*\(", re.I)
ALTER_SQL = re.compile(r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?" + _DDL_NAME, re.I)
DROP_SQL = re.compile(r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?" + _DDL_NAME, re.I)
INSERT_SQL = re.compile(r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+" + _DDL_NAME, re.I)
_SQL_STOP = {"for", "if", "not", "exists", "select", "from", "into", "new", "temp", "temporary",
             "unlogged", "or", "and", "the", "a", "an", "this", "that", "your", "my", "our"}

# Empty-summary rows: these extensions are read for a content note, everything else falls back to a
# name-derived label (never reads) so every scanned file ends up with a record without touching
# credential-shaped or binary files.
NOTE_EXTS = {".md", ".markdown", ".json", ".yml", ".yaml", ".sh", ".bash", ".html", ".htm"}
LABELS = {
    ".md": "Markdown document", ".markdown": "Markdown document", ".sql": "SQL script",
    ".json": "JSON file", ".yml": "YAML config", ".yaml": "YAML config",
    ".sh": "Shell script", ".bash": "Shell script", ".txt": "Text file",
    ".html": "HTML page", ".htm": "HTML page", ".css": "Stylesheet", ".scss": "Stylesheet",
    ".svg": "SVG image", ".conf": "Config file", ".ini": "Config file", ".toml": "Config file",
    ".lock": "Lockfile",
}


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


def _shared_prefix(a: str, b: str) -> int:
    """How many leading path segments two paths share (tiebreak for ambiguous resolutions)."""
    ca, cb = a.split("/"), b.split("/")
    n = 0
    for x, y in zip(ca, cb):
        if x != y:
            break
        n += 1
    return n


def _js_targets(rel: str, code: str, known: Set[str], stripped: Optional[Dict[str, str]] = None) -> Set[str]:
    out: Set[str] = set()
    folder = os.path.dirname(rel)
    for m in JS_IMPORT.finditer(code):
        p = os.path.normpath(os.path.join(folder, m.group(1))).replace("\\", "/")
        for cand in [p] + [p + e for e in JS_EXT] + [f"{p}/index{e}" for e in JS_EXT]:
            if cand in known and cand != rel:
                out.add(cand)
                break
    if stripped:
        for m in ALIAS_IMPORT.finditer(code):
            spec = m.group(1)
            target = spec[2:]
            for ext in JS_EXT:
                if target.endswith(ext):
                    target = target[: -len(ext)]
                    break
            target = target.rstrip("/")
            if not target:
                continue
            cands = [full for key, full in stripped.items()
                     if key == target or key.endswith("/" + target) or key.endswith("/" + target + "/index")]
            cands = [c for c in cands if c != rel]
            if cands:
                out.add(max(cands, key=lambda c: (_shared_prefix(rel, c), c)))
    return out


def sql_tables(text: str) -> List[str]:
    """Tables named in DDL: schema-qualified names reduced to the last segment, SQL keywords dropped
    so prose ("Create table for ...") never becomes an entity."""
    out: Set[str] = set()
    for rx in (CREATE_SQL, ALTER_SQL, DROP_SQL, INSERT_SQL):
        for m in rx.finditer(text):
            name = m.group(1).split(".")[-1]
            if name.lower() not in _SQL_STOP:
                out.add(name)
    return sorted(out)


def supabase_tables(text: str) -> List[str]:
    """Tables a JS/TS file reads through supabase-style .from('table') calls."""
    return sorted({m.group(1) for m in FROM.finditer(text)})


def _route_url(rel: str) -> Optional[str]:
    """Next.js convention: path under app/ or pages/ -> the URL the file serves."""
    parts = rel.replace("\\", "/").split("/")
    root = next((i for i, seg in enumerate(parts) if seg in ("app", "pages")), None)
    if root is None:
        return None
    segs = [s for s in parts[root + 1:] if not s.startswith("(")]
    while segs and (segs[-1].split(".")[0] in ("route", "page", "index") or "." in segs[-1]):
        segs = segs[:-1]
    return "/" + "/".join(segs) if segs else "/"


def _match_handler(url: str, caller: str, handlers: Dict[str, List[str]]) -> Optional[str]:
    if url in handlers:  # exact route wins over a dynamic neighbour
        return max(handlers[url], key=lambda c: (_shared_prefix(caller, c), c))
    cands: List[str] = []
    us = url.strip("/").split("/")
    for h_url, paths in handlers.items():
        hs = h_url.strip("/").split("/")
        hit = len(hs) == len(us) and all(
            h.startswith("[") and h.endswith("]") or h == u for h, u in zip(hs, us))
        # fetch('/api/x/${id}') normalizes to /api/x; the remaining handler segments must be dynamic
        hit = hit or (len(hs) > len(us) and all(
            (h.startswith("[") and h.endswith("]") or h == u) for h, u in zip(hs, us))
            and all(h.startswith("[") for h in hs[len(us):]))
        if hit:
            cands.extend(paths)
    if not cands:
        return None
    return max(cands, key=lambda c: (_shared_prefix(caller, c), c))


def _label(rel: str) -> str:
    """Name-derived record for a file with no summary; '' keeps code modules trivial."""
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    low = name.lower()
    if low.endswith("ignore"):
        return "Ignore rules file"
    if low in ("dockerfile", "makefile", "procfile", "jenkinsfile", "containerfile"):
        return "Build file"
    if low.startswith("license"):
        return "License"
    if ".config." in low:
        return "Config file"
    return LABELS.get(os.path.splitext(low)[1], "")


def _note(rel: str, ext: str, code: str, tables: List[str]) -> str:
    note = ""
    if ext in (".md", ".markdown"):
        m = re.search(r"^#{1,3}[ \t]+(.+)$", code, re.M)
        note = f"Markdown: {m.group(1)}" if m else ""
    elif ext == ".sql":
        note = f"SQL: defines {', '.join(tables[:6])}" if tables else ""
    elif ext == ".json":
        try:
            data = json.loads(code)
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            note = "JSON object: " + ", ".join(str(k) for k in list(data)[:5])
        elif isinstance(data, list):
            note = f"JSON array ({len(data)} items)"
    elif ext in (".yml", ".yaml"):
        keys = re.findall(r"^([A-Za-z_][\w-]*):", code, re.M)[:5]
        note = "YAML: " + ", ".join(keys) if keys else ""
    elif ext in (".sh", ".bash"):
        for line in code.splitlines():
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                note = f"Shell script: {s[1:].strip()}"
                break
    elif ext in (".html", ".htm"):
        m = re.search(r"<title[^>]*>(.*?)</title>", code, re.I | re.S)
        note = f"HTML page: {' '.join(m.group(1).split())}" if m else ""
    return note or _label(rel)


def _safe_read(root: str, rel: str) -> Optional[str]:
    """Read a source file under the project root, or None: symlink jail, secret boundary, size cap."""
    try:
        fp = Path(root) / rel
        if not is_watched_file(fp, project_path=Path(root)):
            return None
        real = fp.resolve() if fp.is_symlink() else fp
        if _is_secret_or_junk(real.name) or any(d in GLOBAL_IGNORED_DIRS for d in real.parts):
            return None
        if fp.stat().st_size > MAX_BYTES:
            return None
        return fp.read_text(errors="ignore")
    except OSError:
        return None


def source_facts(root: str, paths: List[str], need_content: Optional[Set[str]] = None) -> Dict:
    """One read pass over the indexed files -> import edges, fetch->route calls, derived tables and
    routes, path roles, and content records for the rows in need_content (summary-empty paths).
    Returns {} without a root so callers skip cleanly."""
    empty: Dict = {}
    if not root:
        return empty
    need = need_content or set()
    known = set(paths)
    by_mod: Dict[str, str] = {}
    for p in paths:
        if p.endswith(".py"):
            parts = p[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):  # every suffix, so src/pkg/a.py also answers to "pkg.a" and "a"
                by_mod.setdefault(".".join(parts[i:]), p)
    stripped: Dict[str, str] = {}
    for p in paths:
        if os.path.splitext(p)[1] in JS_EXT:
            stripped.setdefault(os.path.splitext(p)[0].replace("\\", "/"), p)

    facts: Dict = {"imports": [], "calls": [], "tables": {}, "routes": {}, "roles": {}, "content": {}}
    fetches: List[tuple] = []
    fetch_seen: Set[tuple] = set()
    handlers: Dict[str, List[str]] = {}

    for rel in sorted(known):
        ext = os.path.splitext(rel)[1].lower()
        want_note = rel in need
        # read: code files for analysis, .sql for DDL, note extensions only when a record is missing
        reads = ext in JS_EXT or ext == ".py" or ext == ".sql" or (want_note and ext in NOTE_EXTS)
        code = _safe_read(root, rel) if reads else None
        if code is not None:
            if ext == ".py":
                for t in sorted(_py_targets(rel, code, known, by_mod)):
                    facts["imports"].append({"from": rel, "to": t, "type": "import", "entity": t})
            elif ext == ".sql":
                tables = sql_tables(code)
                if tables:
                    facts["tables"][rel] = tables
                if "migrations" in rel.split("/") or re.match(r"^\d{6,8}[-_]", rel.rsplit("/", 1)[-1]):
                    facts["roles"][rel] = "migration"
            elif ext in JS_EXT:
                for t in sorted(_js_targets(rel, code, known, stripped)):
                    facts["imports"].append({"from": rel, "to": t, "type": "import", "entity": t})
                tables = sorted({m.group(1) for m in FROM.finditer(code)})
                if tables:
                    facts["tables"][rel] = tables
                for m in FETCH.finditer(code):
                    url = sanitize_text(re.sub(r"\$\{.*", "", m.group(1)).rstrip("/") or "/")
                    if (rel, url) not in fetch_seen:  # one edge per (file, endpoint), not per call site
                        fetch_seen.add((rel, url))
                        fetches.append((rel, url))
                verbs = [m.group(1).upper() for m in VERB_FN.finditer(code)]
                verbs += [m.group(1).upper() for m in VERB_CONST.finditer(code) if m.group(1).upper() not in verbs]
                name = rel.rsplit("/", 1)[-1]
                if name in ROUTE_FILES:
                    url = _route_url(rel)
                    if url:
                        facts["roles"][rel] = sanitize_text("route " + (",".join(verbs) + " " if verbs else "") + url)
                        facts["routes"][rel] = [f"{v} {url}" for v in verbs]
                        handlers.setdefault(url, []).append(rel)
                elif name in PAGE_FILES:
                    url = _route_url(rel)
                    if url:
                        facts["roles"][rel] = sanitize_text(f"page {url}")
        if want_note:
            if code is not None and (ext in NOTE_EXTS or ext == ".sql"):
                note = _note(rel, ext, code, facts["tables"].get(rel, []))
            else:
                note = _label(rel)
            facts["content"][rel] = sanitize_text(note)[:160]

    for caller, url in fetches:
        handler = _match_handler(url, caller, handlers)
        if handler and handler != caller:
            facts["calls"].append({"from": caller, "to": handler, "type": "call", "entity": url})
    return facts


def import_edges(root: str, paths: List[str]) -> List[dict]:
    """Import edges only (the historical API; the full pass lives in source_facts)."""
    return source_facts(root, paths).get("imports", [])
