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

from .codesearch import symbols, text_score

MAX_OVERVIEW_FILES = 60      # files listed with a summary in the overview
MAX_DOMAINS = 8
MAX_ENTITIES = 15
MAX_MATCHES = 8              # result groups rendered in full by search()
MAX_SUMMARY = 110
MAX_JSON_FILES = 200
OFFER_MIN_CHARS = 1600       # a full answer below this (~400 tokens) is returned directly, no offer step

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


def overview(project_name: str, files: List[dict], index: dict, fresh: str = "") -> str:
    n = len(files)
    lines = [f"# codebone: {project_name} | {n} files | {_analysis_label(files)}"]
    if not n:
        lines.append("Nothing indexed yet.")
        return "\n".join(lines)
    if fresh:
        lines.append(fresh)
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
    lines += ["", 'Drill down: cb(query="billing invoice"), cb(file="auth"), cb(domain="Payment"); a symbol name in query shows definition and references, file= shows imports']
    return "\n".join(lines)


def _match_files(files: List[dict], index: dict, domain: str, file: str, query: str,
                 texts: Optional[Dict[str, str]] = None, assets: bool = False) -> Tuple[List[Tuple[dict, int]], bool, dict]:
    """Returns ([(file, score)] best first, partial, info).

    With a query, domain and file are boosts, never filters: a file that matches the words but sits in
    another domain still ranks, and info["domain_hits"] says how the hits split. Without a query they
    filter. Terms must all match (AND); if that finds nothing, any term (OR) is used. Asset rows only
    count with assets=True (info["assets_hidden"] tells how many matched anyway)."""
    info: dict = {}
    pool = files
    dw = _tokens(domain) or ([domain.lower()] if domain else [])
    fw = _tokens(file) or ([file.lower()] if file else [])

    def in_dom(f: dict) -> bool:
        return bool(dw) and any(all(t in d.lower() for t in dw) for d in f.get("domains", []))

    def in_file(f: dict) -> bool:
        return bool(fw) and all(t in f["path"].lower() for t in fw)

    terms = _tokens(query)
    if not terms:
        if query:
            return [], False, info
        pool = [f for f in pool if (not dw or in_dom(f)) and (not fw or in_file(f))]
        if not assets:
            pool = [f for f in pool if f.get("source") != "asset"]
        return [(f, 0) for f in sorted(pool, key=lambda f: f["path"])], False, info

    def score(f: dict) -> Tuple[int, int]:
        path = f["path"].lower()
        base = path.rsplit("/", 1)[-1]
        entities = [e.lower() for cat in ("tables", "routes", "events") for e in f.get(cat, [])]
        doms = [d.lower() for d in f.get("domains", [])]
        summary = ((f.get("summary") or "") + " " + (f.get("content") or "")).lower()
        body = text_score(texts[f["path"]], terms)[0] if texts and f["path"] in texts else [0] * len(terms)
        total = hit_terms = 0
        for t, w in zip(terms, body):
            s = w
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
        if hit_terms:
            total += 4 * in_dom(f) + 4 * in_file(f)
        return hit_terms, total

    scored = [(f, *score(f)) for f in pool]
    strict = [(f, h, s) for f, h, s in scored if h == len(terms)]
    partial = False
    if strict:
        hits = strict
    else:
        hits = [(f, h, s) for f, h, s in scored if h > 0]
        partial = bool(hits)
    if not assets:
        info["assets_hidden"] = sum(1 for f, _, _ in hits if f.get("source") == "asset")
        hits = [x for x in hits if x[0].get("source") != "asset"]
    hits.sort(key=lambda x: (-x[1], -x[2], x[0]["path"]))
    if dw:
        info["domain_hits"] = sum(1 for f, _, _ in hits if in_dom(f))
    return [(f, s) for f, _, s in hits], partial, info


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


def _groups(ranked: List[Tuple[dict, int]]) -> List[Tuple[dict, int, List[str]]]:
    """Same file name and same description in several places (logo.png in three apps) -> one entry."""
    seen: Dict[tuple, list] = {}
    out: List[Tuple[dict, int, List[str]]] = []
    for f, sc in ranked:
        key = (f["path"].rsplit("/", 1)[-1], f.get("summary") or f.get("content") or "")
        if key in seen:
            seen[key].append(f["path"])
        else:
            seen[key] = others = []
            out.append((f, sc, others))
    return out


def search(project_name: str, files: List[dict], index: dict, domain: str = "", file: str = "", query: str = "",
           texts: Optional[Dict[str, str]] = None, assets: bool = False, fresh: str = "",
           facts: Optional[dict] = None) -> str:
    """texts (path -> source) adds the word search: code lines, symbol names and comments join the ranking and
    the best matching lines are quoted. facts adds imports / imported by per file."""
    label = " ".join(f'{k}="{v}"' for k, v in (("domain", domain), ("file", file), ("query", query)) if v)
    ranked, partial, info = _match_files(files, index, domain, file, query, texts, assets)
    groups = _groups(ranked)
    lines = [f"# codebone: {project_name} | {label} | {len(ranked)} match{'es' if len(ranked) != 1 else ''}"]
    if fresh:
        lines.append(fresh)
    if partial:
        lines.append("(no file matches every term; showing files matching some)")
    if domain and query and ranked:
        k = info.get("domain_hits", 0)
        lines.append(f'Domain "{domain}": {k} hit{"" if k == 1 else "s"} in it, {len(ranked) - k} elsewhere (ranked together)')
    if info.get("assets_hidden"):
        lines.append(f"({info['assets_hidden']} asset files also match; add assets=true to list them)")
    terms = _tokens(query)
    if not ranked:
        if domain and not query:
            known = sorted(index.get("domains", {}).items(), key=lambda kv: -len(kv[1]))[:6]
            lines.append(f'0 files in domain "{domain}"; domains: ' + ", ".join(f"{d} ({len(p)})" for d, p in known))
        lines.append("No match. Try fewer or different words, or cb() for the overview.")
        return "\n".join(lines)

    if texts and terms:
        for sym in symbols(terms, texts):
            d = sym["defs"][0]
            lines += ["", f"### symbol {sym['name']}: defined at {d[0]}:{d[1]}" + (f" (+{len(sym['defs']) - 1} more)" if len(sym["defs"]) > 1 else "")]
            lines += [f"- {p}:{i} {_clip(text, 110)}" for p, i, text in sym["uses"]]
            if sym["more"]:
                lines.append(f"(+{sym['more']} more references)")
            if not sym["uses"]:
                lines.append("- no other references found")

    shown = groups[:MAX_MATCHES]
    by_path = {f["path"]: f for f in files}
    imports_by: Dict[str, List[str]] = {}
    imported_by: Dict[str, List[str]] = {}
    for e in (facts or {}).get("imports", []):
        imports_by.setdefault(e["from"], []).append(e["to"])
        imported_by.setdefault(e["to"], []).append(e["from"])
    for f, sc, same in shown:
        doms = f.get("domains", [])
        header = f"### {f['path']}" + (f" [{', '.join(doms[:2])}]" if doms else "")
        if f.get("role"):
            header += f" [{f['role']}]"
        if query:
            header += f" (score {sc})"
        lines += ["", header]
        if same:
            lines.append(f"Same file in {len(same)} more place{'s' if len(same) != 1 else ''}: {_more(same, 4)}")
        body = f.get("summary") or f.get("content") or ""
        if body:
            lines.append(_clip(body, 200))
        if texts and terms and f["path"] in texts:
            for _, i, text in text_score(texts[f["path"]], terms)[1][:2]:
                lines.append(f"L{i}: {_clip(text, 140)}")
        for label_, cat in (("Tables", "tables"), ("Routes", "routes"), ("Events", "events")):
            if f.get(cat):
                lines.append(f"{label_}: {_more(f[cat], 8)}")
        if f.get("calls"):
            chains = []
            for route, handler in f["calls"]:
                h_tables = by_path.get(handler, {}).get("tables", [])
                chains.append(f"{route} -> {handler}" + (f" (tables: {_more(h_tables, 3)})" if h_tables else ""))
            lines.append("Calls: " + _more(chains, 4))
        if imports_by.get(f["path"]):
            lines.append("Imports: " + _more(sorted(imports_by[f["path"]]), 4))
        if imported_by.get(f["path"]):
            lines.append("Imported by: " + _more(sorted(imported_by[f["path"]]), 4))
        links = _links(f["path"], f, index)
        if links:
            lines.append("Linked: " + ", ".join(f"{p} (via {via})" for p, via in links))
    if len(groups) > len(shown):
        rest = [g[0]["path"] for g in groups[len(shown): len(shown) + 10]]
        lines += ["", f"(+{len(groups) - len(shown)} more: {', '.join(rest)}{' ...' if len(groups) - len(shown) > 10 else ''})"]
    return "\n".join(lines)


def offer(project_name: str, files: List[dict], index: dict, domain: str = "", file: str = "", query: str = "",
          texts: Optional[Dict[str, str]] = None, assets: bool = False, fresh: str = "",
          facts: Optional[dict] = None) -> str:
    """The short first answer to a query: best file, confidence, a size estimate of the full answer and how to
    ask for it. Enough to finish a small change; the caller decides whether the full search is worth its tokens."""
    ranked, partial, _ = _match_files(files, index, domain, file, query, texts, assets)
    full = search(project_name, files, index, domain, file, query, texts, assets, fresh, facts)
    if not ranked or len(full) < OFFER_MIN_CHARS:
        return full
    top = ranked[0]
    lead = top[1] >= 2 * ranked[1][1] if len(ranked) > 1 else True
    conf = "low" if partial else "high" if lead else "medium"
    head = top[0]["path"]
    if texts and top[0]["path"] in texts:
        best = text_score(texts[top[0]["path"]], _tokens(query))[1]
        if best:
            head += f":{best[0][1]} {_clip(best[0][2], 90)}"
    lines = [f'# codebone: {project_name} | query="{query}" | {len(ranked)} match{"es" if len(ranked) != 1 else ""}, confidence {conf}']
    if fresh:
        lines.append(fresh)
    lines.append(f"Top: {head}")
    others = [f["path"] for f, _ in ranked[1:4] if "test" not in f["path"].lower()]
    tests = [f["path"] for f, _ in ranked if "test" in f["path"].lower()][:2]
    if others:
        lines.append("Also: " + ", ".join(others))
    if tests:
        lines.append("Tests: " + ", ".join(tests))
    lines.append(f"Tip ~{len(full) // 4} tokens (references, imports, matching lines): repeat the call with whisper=true.")
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
    lines.append('Use cb(file="...") for the links of one file.')
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


def search_json(project_name: str, files: List[dict], index: dict, revision: int, domain="", file="", query="",
                texts: Optional[Dict[str, str]] = None, assets: bool = False) -> dict:
    matches, partial, _ = _match_files(files, index, domain, file, query, texts, assets)
    matches = [f for f, _ in matches]
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
