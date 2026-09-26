"""Read-time text search over the indexed source: the word half of cb(query=...).

Regex over lines, not a parser: symbol definitions and their callers are name matches, not
type-resolved references. Nothing is stored; every query reads the files, so results are as
fresh as the disk (the index freshness line says how far the summaries lag behind).
"""
import os
import re
import time
from typing import Dict, List, Tuple

from .imports import _safe_read

MAX_FILES = 6000  # ponytail: linear scan per query; build a persistent word index if a repo outgrows this
DEF = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:pub\s+)?(?:async\s+)?"
    r"(?:def|class|function\*?|const|let|var|interface|type|enum|struct|fn|func)\s+([A-Za-z_$][\w$]*)")
COMMENT = ("#", "//", "/*", "*", "--")


def read_texts(root: str, files: List[dict]) -> Dict[str, str]:
    """path -> source text for every non-asset indexed file that may be read (secret boundary, size cap)."""
    out: Dict[str, str] = {}
    for f in files:
        if f.get("source") == "asset" or len(out) >= MAX_FILES:
            continue
        text = _safe_read(root, f["path"])
        if text:
            out[f["path"]] = text
    return out


def text_score(text: str, terms: List[str]) -> Tuple[List[int], List[Tuple[int, int, str]]]:
    """Per-term weight (definition name 6/4, comment 2, code 1) and the best matching lines."""
    weights = [0] * len(terms)
    low_all = text.lower()
    if not any(t in low_all for t in terms):
        return weights, []
    best: List[Tuple[int, int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        present = [j for j, t in enumerate(terms) if t in low]
        if not present:
            continue
        m = DEF.match(line)
        name = m.group(1).lower() if m else ""
        comment = low.lstrip().startswith(COMMENT)
        for j in present:
            w = (6 if name == terms[j] else 4 if terms[j] in name else 1) if name else 2 if comment else 1
            weights[j] = max(weights[j], w)
        best.append((len(present) + bool(name), i, line))
    best.sort(key=lambda b: (-b[0], b[1]))
    return weights, best


def symbols(terms: List[str], texts: Dict[str, str], limit: int = 6) -> List[dict]:
    """For each term that names a defined symbol: where it is defined and which other lines use it."""
    out = []
    for t in dict.fromkeys(x for x in terms if len(x) > 2):
        defs = []
        for p, text in texts.items():
            if t in text.lower():
                defs += [(p, i, m.group(1)) for i, line in enumerate(text.splitlines(), 1)
                         if (m := DEF.match(line)) and m.group(1).lower() == t]
        if not defs:
            continue
        name = defs[0][2]
        rx = re.compile(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])")
        skip = {(p, i) for p, i, _ in defs}
        uses = [(p, i, line.strip()) for p, text in texts.items() if name in text
                for i, line in enumerate(text.splitlines(), 1) if rx.search(line) and (p, i) not in skip]
        home = {p for p, _, _ in defs}
        uses.sort(key=lambda u: (u[0] in home, u[0], u[1]))
        out.append({"name": name, "defs": defs[:3], "uses": uses[:limit], "more": max(0, len(uses) - limit)})
    return out


def freshness(root: str, files: List[dict]) -> str:
    """'Index: synced <age> ago, N files changed on disk since' from stored vs current mtimes."""
    stamps = [f["updated_at"] for f in files if f.get("updated_at")]
    if not stamps:
        return ""
    changed = []
    for f in files:
        if not f.get("mtime"):
            continue
        try:
            if os.stat(os.path.join(root, f["path"])).st_mtime > f["mtime"] + 1:
                changed.append(f["path"])
        except OSError:
            changed.append(f["path"])  # deleted since
    age = int(time.time() - max(stamps))
    ago = f"{age // 86400}d" if age >= 86400 else f"{age // 3600}h" if age >= 3600 else f"{max(age // 60, 0)}min"
    tail = f", {len(changed)} files changed on disk since ({', '.join(sorted(changed)[:3])}{' ...' if len(changed) > 3 else ''})" if changed else ", no changes on disk since"
    return f"Index: last update {ago} ago{tail}"
