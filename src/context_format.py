"""Renders the indexed project as compact, deterministic context for AI assistants.

Two views, both bounded in size regardless of project size:
  overview()  the map: layout, domains, key entities and a one-line summary per (important) file
  search()    the drill-down: ranked matches for domain / file / query with entities and linked files

Everything here is a pure function of the stored rows plus the read-time source facts folded into
them, so identical index state gives identical text.
"""
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

MAX_OVERVIEW_FILES = 60      # files listed with a summary in the overview
MAX_DOMAINS = 8
MAX_ENTITIES = 15
MAX_MATCHES = 12             # files rendered in full by search()
MAX_SUMMARY = 110
MAX_JSON_FILES = 200

_TOKEN = re.compile(r"[a-z0-9_./&-]+")


def _clip(text: str, limit: int = MAX_SUMMARY) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _tokens(text: str) -> List[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if len(t) > 1]


def _more(items: List[str], cap: int) -> str:
    shown = ", ".join(items[:cap])
    return shown + (f" (+{len(items) - cap})" if len(items) > cap else "")


def _analysis_label(files: List[dict]) -> str:
    regex = sum(1 for f in files if f.get("source") == "regex")
    if not files or not regex:
        return "model analysis"
    if regex == len(files):
        return "heuristic analysis (no model)"
    return f"model analysis, {regex} files heuristic"


def _layout(files: List[dict]) -> str:
    counts = Counter(f["path"].split("/", 1)[0] if "/" in f["path"] else "." for f in files)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    return ", ".join(f"{name}/ ({n})" if name != "." else f"root ({n})" for name, n in top)


def _degree(files: List[dict], index: dict) -> Dict[str, int]:
    """How connected a file is: entities it declares plus how many other files share them."""
    score: Dict[str, int] = {f["path"]: 0 for f in files}
    for cat in ("tables", "routes", "events"):
        for paths in index.get(cat, {}).values():
            for p in paths:
                if p in score:
                    score[p] += len(paths)
    for f in files:
        score[f["path"]] += len(f.get("tables", [])) + len(f.get("routes", [])) + len(f.get("events", []))
    return score


def overview(project_name: str, files: List[dict], index: dict) -> str:
    n = len(files)
    lines = [f"# codebone: {project_name} | {n} files | {_analysis_label(files)}"]
    if not n:
        lines.append("Nothing indexed yet.")
        return "\n".join(lines)
    lines.append(f"Layout: {_layout(files)}")

    domains = sorted(index.get("domains", {}).items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))
    if domains:
        lines += ["", "## Domains"]
        for name, paths in domains[:MAX_DOMAINS]:
            lines.append(f"- {name} ({len(paths)}): {_more(sorted(paths), 4)}")
        if len(domains) > MAX_DOMAINS:
            lines.append(f"- (+{len(domains) - MAX_DOMAINS} more domains)")

    entity_lines = []
    for label, cat in (("Tables", "tables"), ("Routes", "routes"), ("Events", "events")):
        names = sorted(index.get(cat, {}))
        if names:
            entity_lines.append(f"- {label}: {_more(names, MAX_ENTITIES)}")
    if entity_lines:
        lines += ["", "## Entities"] + entity_lines

    # Files with no summary, content record and no entities (empty __init__.py ...) tell an assistant
    # nothing: count, do not list
    informative = [f for f in files if f.get("summary") or f.get("content") or f.get("tables") or f.get("routes") or f.get("events")]
    trivial = n - len(informative)
    n_listed = len(informative)
    ranked = sorted(informative, key=lambda f: f["path"])
    truncated = n_listed > MAX_OVERVIEW_FILES
    if truncated:
        degree = _degree(files, index)
        ranked = sorted(informative, key=lambda f: (-degree[f["path"]], f["path"]))[:MAX_OVERVIEW_FILES]
        ranked.sort(key=lambda f: f["path"])
    lines += ["", "## Files" + (f" (top {MAX_OVERVIEW_FILES} of {n_listed} by connectivity)" if truncated else "")]
    for f in ranked:
        text = _clip(f.get("summary") or f.get("content", ""))
        line = f"- {f['path']}" + (f": {text}" if text else "")
        if f.get("role"):
            line += f" [{f['role']}]"
        lines.append(line)

    if trivial:
        lines.append(f"(+{trivial} files without notable content omitted)")
    lines += ["", 'Drill down: cb(query="billing invoice"), cb(file="auth"), cb(domain="Payment"); links: codebone_graph(file="...")']
    return "\n".join(lines)


def _match_files(files: List[dict], index: dict, domain: str, file: str, query: str) -> Tuple[List[dict], bool]:
    """Returns (ranked files, partial). Terms must all match (AND); if that finds nothing, any term (OR) is used."""
    pool = files
    if domain:
        wanted = _tokens(domain) or [domain.lower()]
        pool = [f for f in pool if any(all(t in d.lower() for t in wanted) for d in f.get("domains", []))]
    if file:
        wanted = _tokens(file) or [file.lower()]
        pool = [f for f in pool if all(t in f["path"].lower() for t in wanted)]
    if not query:
        return sorted(pool, key=lambda f: f["path"]), False

    terms = _tokens(query)
    if not terms:
        return [], False

    def score(f: dict) -> Tuple[int, int]:
        path = f["path"].lower()
        base = path.rsplit("/", 1)[-1]
        entities = [e.lower() for cat in ("tables", "routes", "events") for e in f.get(cat, [])]
        doms = [d.lower() for d in f.get("domains", [])]
        summary = ((f.get("summary") or "") + " " + (f.get("content") or "")).lower()
        total = hit_terms = 0
        for t in terms:
            s = 0
            if t in base:
                s += 5
            elif t in path:
                s += 3
            if any(t in e for e in entities):
                s += 3
            if any(t in d for d in doms):
                s += 2
            if t in summary:
                s += 1
            if s:
                hit_terms += 1
            total += s
        return hit_terms, total

    scored = [(f, *score(f)) for f in pool]
    strict = [(f, h, s) for f, h, s in scored if h == len(terms)]
    partial = False
    if strict:
        hits = strict
    else:
        hits = [(f, h, s) for f, h, s in scored if h > 0]
        partial = bool(hits)
    hits.sort(key=lambda x: (-x[1], -x[2], x[0]["path"]))
    return [f for f, _, _ in hits], partial


def _lookup(index: dict, cat: str, name: str) -> List[str]:
    """Files declaring an entity. The index folds names that differ only in case into one entry."""
    bucket = index.get(cat, {})
    if name in bucket:
        return bucket[name]
    low = name.lower()
    return next((paths for key, paths in bucket.items() if key.lower() == low), [])


def _links(path: str, rec: dict, index: dict, limit: int = 5) -> List[Tuple[str, str]]:
    seen: Dict[str, str] = {}
    for cat in ("tables", "routes", "events"):
        for name in rec.get(cat, []):
            for other in _lookup(index, cat, name):
                if other != path and other not in seen:
                    seen[other] = name
    return sorted(seen.items())[:limit]


def search(project_name: str, files: List[dict], index: dict, domain: str = "", file: str = "", query: str = "") -> str:
    label = " ".join(f'{k}="{v}"' for k, v in (("domain", domain), ("file", file), ("query", query)) if v)
    matches, partial = _match_files(files, index, domain, file, query)
    lines = [f"# codebone: {project_name} | {label} | {len(matches)} match{'es' if len(matches) != 1 else ''}"]
    if partial:
        lines.append("(no file matches every term; showing files matching some)")
    if not matches:
        lines.append("No match. Try fewer or different words, or cb() for the overview.")
        return "\n".join(lines)

    shown = matches[:MAX_MATCHES]
    by_path = {f["path"]: f for f in files}
    for f in shown:
        doms = f.get("domains", [])
        header = f"### {f['path']}" + (f" [{', '.join(doms[:2])}]" if doms else "")
        if f.get("role"):
            header += f" [{f['role']}]"
        lines += ["", header]
        body = f.get("summary") or f.get("content") or ""
        if body:
            lines.append(_clip(body, 200))
        for label_, cat in (("Tables", "tables"), ("Routes", "routes"), ("Events", "events")):
            if f.get(cat):
                lines.append(f"{label_}: {_more(f[cat], 8)}")
        if f.get("calls"):
            chains = []
            for route, handler in f["calls"]:
                h_tables = by_path.get(handler, {}).get("tables", [])
                chains.append(f"{route} -> {handler}" + (f" (tables: {_more(h_tables, 3)})" if h_tables else ""))
            lines.append("Calls: " + _more(chains, 4))
        links = _links(f["path"], f, index)
        if links:
            lines.append("Linked: " + ", ".join(f"{p} (via {via})" for p, via in links))
    if len(matches) > len(shown):
        rest = [f["path"] for f in matches[len(shown): len(shown) + 10]]
        lines += ["", f"(+{len(matches) - len(shown)} more: {', '.join(rest)}{' ...' if len(matches) - len(shown) > 10 else ''})"]
    return "\n".join(lines)


def links(project_name: str, files: List[dict], index: dict, file: str = "", facts: Optional[dict] = None) -> str:
    """Files connected through shared tables, routes or events, plus imports and API calls when the
    caller passes the read-time facts."""
    by_path = {f["path"]: f for f in files}
    facts = facts or {}
    imports_by: Dict[str, List[str]] = {}
    imported_by: Dict[str, List[str]] = {}
    for e in facts.get("imports", []):
        imports_by.setdefault(e["from"], []).append(e["to"])
        imported_by.setdefault(e["to"], []).append(e["from"])
    calls_by: Dict[str, List[list]] = {}
    for e in facts.get("calls", []):
        calls_by.setdefault(e["from"], []).append([e["entity"], e["to"]])
    if file:
        wanted = _tokens(file) or [file.lower()]
        targets = [p for p in sorted(by_path) if all(t in p.lower() for t in wanted)][:3]
        if not targets:
            return f"# codebone links: no file matches {file!r}"
        lines = [f"# codebone links: {project_name}"]
        for p in targets:
            rec = by_path[p]
            lines += ["", f"## {p}"]
            found = False
            for label, cat in (("table", "tables"), ("route", "routes"), ("event", "events")):
                for name in rec.get(cat, []):
                    others = [o for o in _lookup(index, cat, name) if o != p]
                    if others:
                        found = True
                        lines.append(f"- {label} {name}: {_more(sorted(others), 6)}")
            calls = calls_by.get(p) or rec.get("calls") or []
            for route, handler in calls[:5]:
                found = True
                h_tables = by_path.get(handler, {}).get("tables", [])
                lines.append(f"- calls {route} -> {handler}" + (f" ({_more(h_tables, 3)})" if h_tables else ""))
            out = imports_by.get(p, [])
            if out:
                found = True
                lines.append(f"- imports: {_more(sorted(out), 4)}")
            incoming = imported_by.get(p, [])
            if incoming:
                found = True
                lines.append(f"- imported by: {_more(sorted(incoming), 4)}")
            if not found:
                lines.append("- shares no table, route, event or import with other files")
        return "\n".join(lines)

    degree = _degree(files, index)
    for e in facts.get("imports", []) + facts.get("calls", []):
        degree[e["from"]] = degree.get(e["from"], 0) + 1
        degree[e["to"]] = degree.get(e["to"], 0) + 1
    hubs = [p for p, d in sorted(degree.items(), key=lambda kv: (-kv[1], kv[0])) if d][:15]
    lines = [f"# codebone links: {project_name} | most connected files"]
    lines += [f"- {p} ({degree[p]})" for p in hubs] or ["- no shared entities found"]
    lines.append('Use codebone_graph(file="...") for the links of one file.')
    return "\n".join(lines)


def overview_json(project_name: str, files: List[dict], index: dict, revision: int) -> dict:
    return {
        "project": project_name,
        "revision": revision,
        "file_count": len(files),
        "analysis": _analysis_label(files),
        "domains": {d: len(p) for d, p in sorted(index.get("domains", {}).items())},
        "entities": {cat: sorted(index.get(cat, {})) for cat in ("tables", "routes", "events")},
        "files": [
            {"path": f["path"], "summary": _clip(f.get("summary", "")), "domains": f.get("domains", []),
             "content": f.get("content", ""), "role": f.get("role", ""), "calls": f.get("calls", [])}
            for f in sorted(files, key=lambda f: f["path"])[:MAX_JSON_FILES]
        ],
        "truncated": len(files) > MAX_JSON_FILES,
    }


def search_json(project_name: str, files: List[dict], index: dict, revision: int, domain="", file="", query="") -> dict:
    matches, partial = _match_files(files, index, domain, file, query)
    return {
        "project": project_name,
        "revision": revision,
        "filter": {"domain": domain, "file": file, "query": query},
        "match_count": len(matches),
        "partial": partial,
        "files": [
            {**{k: f.get(k) for k in ("path", "summary", "domains", "tables", "routes", "events")},
             "content": f.get("content") or "", "role": f.get("role") or "", "calls": f.get("calls") or []}
            for f in matches[:50]
        ],
        "truncated": len(matches) > 50,
    }
