"""Internal SQLite store for codebone's semantic knowledge graph."""
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from .imports import source_facts as _source_facts, _SQL_STOP
from .prompts import _clean_entity_list, parse_analysis, sanitize_text

logger = logging.getLogger("codebone.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    tables TEXT NOT NULL,
    routes TEXT NOT NULL,
    events TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    updated_at REAL NOT NULL,
    mtime REAL DEFAULT 0,
    content_hash TEXT DEFAULT '',
    source TEXT DEFAULT 'model'
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Rendering limits for the graph: entity-sharing links are windowed per entity and capped overall so a
# 5000-file project does not produce a multi-megabyte payload.
MAX_PEERS_PER_ENTITY = 6
# Safety valve for the entity-edge payload, not a target: only _compute_edges is capped (imports,
# calls and orphan links come on top). A 1400-file project lands at ~1.2k entity edges, so 15000 is
# several times what real projects produce — hit it and the tail entities are dropped silently.
MAX_EDGES = 15000
MAX_DOMAIN_PEERS = 15
# Up to this many files per entity are drawn pairwise (dense and pretty); a bigger group collapses
# into a star through its most-connected member, which keeps every member linked at n-1 edges
# instead of the ~6n the peer window would spend — an edge only ever means "both share the entity",
# and a star still says that for every member.
MAX_PAIRWISE_GROUP = 10


def _dir_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


class Storage:
    def __init__(self, db_path: Path, readonly: bool = False):
        self.db_path = db_path
        self.readonly = readonly
        self._lock = threading.RLock()
        self._revision = 0
        self._cache: dict = {}
        self._has_entities_col = False
        if readonly:
            # Foreign or snapshot databases are inspected without ever modifying them
            self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            return
        try:
            self._open()
        except sqlite3.DatabaseError as exc:
            self._quarantine(exc)
            self._open()

    def _open(self):
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.execute("SELECT COUNT(*) FROM files").fetchone()  # surfaces a damaged file immediately
        self._conn.commit()

    def _quarantine(self, exc: Exception):
        """A damaged index must never keep the app from starting: move it aside and begin empty (the index is
        rebuilt from the source files anyway)."""
        try:
            self._conn.close()
        except Exception:
            pass
        stamp = int(time.time())
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(self.db_path) + suffix)
            if src.exists():
                try:
                    os.replace(src, Path(f"{self.db_path}.corrupt-{stamp}{suffix}"))
                except OSError:
                    pass
        logger.error("Index database was unreadable (%s); moved aside as %s.corrupt-%d", exc, self.db_path, stamp)

    def _migrate(self):
        columns = [row["name"] for row in self._conn.execute("PRAGMA table_info(files)").fetchall()]
        for name, ddl in (
            ("content_hash", "TEXT DEFAULT ''"),
            ("mtime", "REAL DEFAULT 0"),
            ("tables", "TEXT DEFAULT '[]'"),
            ("routes", "TEXT DEFAULT '[]'"),
            ("events", "TEXT DEFAULT '[]'"),
            ("domains", "TEXT DEFAULT '[]'"),
            ("source", "TEXT DEFAULT 'model'"),
        ):
            if name not in columns:
                self._conn.execute(f"ALTER TABLE files ADD COLUMN {name} {ddl}")
        self._has_entities_col = "entities" in columns

    # ── change tracking ─────────────────────────────────────────────────
    @property
    def revision(self) -> int:
        """Increases on every write; readers use it to know whether cached views are still valid."""
        return self._revision

    def _touch(self):
        self._revision += 1
        self._cache.clear()

    def _cached(self, key, build):
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                hit = self._cache[key] = build()
            return hit

    # ── meta ─────────────────────────────────────────────────────────────
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()
            self._touch()  # project_path gates the derived views; a cached empty one must not outlive the bind

    # ── writes ───────────────────────────────────────────────────────────
    def _upsert(self, path, tables, routes, events, domains, summary, updated_at, mtime, content_hash, source):
        cols = ["path", "tables", "routes", "events", "domains", "summary", "updated_at", "mtime", "content_hash", "source"]
        vals = [path, json.dumps(tables), json.dumps(routes), json.dumps(events), json.dumps(domains),
                summary, updated_at, mtime, content_hash, source]
        if self._has_entities_col:  # legacy schema kept a NOT NULL combined column
            cols.insert(1, "entities")
            vals.insert(1, json.dumps(tables + routes + events + domains))
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
        with self._lock:
            self._conn.execute(
                f"INSERT INTO files ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                f"ON CONFLICT(path) DO UPDATE SET {updates}",
                vals,
            )
            self._conn.commit()
            self._touch()

    def update_file(
        self,
        rel_path: str,
        raw_output: str,
        mtime: float = 0.0,
        content_hash: str = "",
        source: str = "model",
    ) -> dict:
        tables, routes, events, domains, summary = parse_analysis(raw_output)
        self._upsert(rel_path, tables, routes, events, domains, summary, time.time(), mtime, content_hash, source)
        return {
            "path": rel_path,
            "tables": tables,
            "routes": routes,
            "events": events,
            "domains": domains,
            "summary": summary,
        }

    def insert_record(self, entry: dict):
        """Insert or replace a pre-existing analysis record. Records come from snapshots and imported scan files, so
        text and entity names are cleaned the same way as fresh model output."""
        self._upsert(
            entry["path"],
            _clean_entity_list([str(x) for x in entry.get("tables", [])]),
            _clean_entity_list([str(x) for x in entry.get("routes", [])]),
            _clean_entity_list([str(x) for x in entry.get("events", [])]),
            _clean_entity_list([str(x) for x in entry.get("domains", [])]),
            sanitize_text(str(entry.get("summary", ""))),
            entry.get("updated_at", time.time()),
            entry.get("mtime", 0.0),
            entry.get("content_hash", ""),
            entry.get("source", "model"),
        )

    def set_mtime(self, rel_path: str, mtime: float):
        """Refresh the stored mtime of an unchanged file so the next rescan can skip it without reading it."""
        with self._lock:
            self._conn.execute("UPDATE files SET mtime = ? WHERE path = ?", (mtime, rel_path))
            self._conn.commit()

    def remove_file(self, rel_path: str):
        self.remove_files([rel_path])

    def remove_files(self, rel_paths: List[str]):
        if not rel_paths:
            return
        with self._lock:
            self._conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in rel_paths])
            self._conn.commit()
            self._touch()

    def reset(self):
        with self._lock:
            self._conn.execute("DELETE FROM files")
            self._conn.commit()
            self._touch()

    # ── snapshots ────────────────────────────────────────────────────────
    def snapshot_to(self, dest_path: Path):
        """Atomically copy the SQLite database to a snapshot file."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".codebone-", suffix=".tmp", dir=dest_path.parent)  # never a sibling of the user's
        os.close(fd)
        try:
            with self._lock:
                bck = sqlite3.connect(tmp_name)
                with bck:
                    self._conn.backup(bck)
                bck.close()
            os.replace(tmp_name, dest_path)
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    def restore_from(self, source_path: Path):
        """Atomically restore the SQLite database from a snapshot file."""
        src = sqlite3.connect(str(source_path))
        with self._lock:
            with self._conn:
                src.backup(self._conn)
            self._migrate()
            self._touch()
        src.close()

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # ── reads ────────────────────────────────────────────────────────────
    def get_file_mtimes(self) -> Dict[str, float]:
        with self._lock:
            rows = self._conn.execute("SELECT path, COALESCE(mtime, 0) as mtime FROM files").fetchall()
            return {r["path"]: float(r["mtime"]) for r in rows}

    def get_file_hashes(self) -> Dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT path, COALESCE(content_hash, '') as h FROM files").fetchall()
            return {r["path"]: r["h"] for r in rows}

    def get_file_sources(self) -> Dict[str, str]:
        """path -> 'model' or 'regex' (which analyser produced the row)."""
        with self._lock:
            rows = self._conn.execute("SELECT path, COALESCE(source, 'model') as s FROM files").fetchall()
            return {r["path"]: r["s"] for r in rows}

    def get_file_hash(self, rel_path: str) -> str:
        with self._lock:
            row = self._conn.execute("SELECT content_hash FROM files WHERE path = ?", (rel_path,)).fetchone()
            return (row["content_hash"] or "") if row else ""

    def get_records_by_hash(self) -> Dict[str, List[dict]]:
        """Maps content_hash to list of file records (used for rename/move detection)."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM files WHERE content_hash != ''").fetchall()
            result: Dict[str, List[dict]] = {}
            for r in rows:
                result.setdefault(r["content_hash"], []).append(self._row_to_dict(r))
            return result

    def get_file(self, rel_path: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM files WHERE path = ?", (rel_path,)).fetchone()
            return self._row_to_dict(row) if row else None

    def all_files(self) -> List[dict]:
        """All rows, newest first. The list is cached until the next write and shared: treat it as read-only."""
        def build():
            rows = self._conn.execute("SELECT * FROM files ORDER BY updated_at DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]
        return self._cached("all_files", build)

    def recent(self, limit: int = 15) -> List[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM files ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def file_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    @staticmethod
    def _build_index(files: List[dict]) -> dict:
        """Inverted indexes table/route/event/domain -> [files]. Names that differ only in case are one entity."""
        maps: Dict[str, Dict[str, List[str]]] = {"tables": {}, "routes": {}, "events": {}, "domains": {}}
        canon: Dict[str, Dict[str, str]] = {k: {} for k in maps}
        for entry in sorted(files, key=lambda f: f["path"]):  # path order: the chosen spelling is stable
            p = entry["path"]
            for cat, cat_map in maps.items():
                for name in entry.get(cat, []):
                    key = canon[cat].setdefault(name.lower(), name)
                    bucket = cat_map.setdefault(key, [])
                    if p not in bucket:
                        bucket.append(p)
        return maps

    def entity_index(self) -> dict:
        """Returns inverted indexes: table -> [files], route -> [files], event -> [files], domain -> [files].
        Cached until the next write and shared: treat it as read-only."""
        return self._cached("entity_index", lambda: self._build_index(self.all_files()))

    def all_domains(self, idx: Optional[dict] = None) -> List[str]:
        """Returns sorted list of all unique domain names across the codebase."""
        idx = idx or self.entity_index()
        return sorted(idx.get("domains", {}).keys())

    def filtered_entity_index(self, allowed_paths: set[str]) -> dict:
        """Returns inverted indexes filtered to a specific set of file paths."""
        return self._build_index([f for f in self.all_files() if f["path"] in allowed_paths])

    def graph_edges(self, index: Optional[dict] = None, include_domains: bool = False) -> List[dict]:
        """Files are logically connected if they share a DB table, API route or event (and optionally a domain),
        plus the import and fetch->route edges derived from the sources at read time. Pairwise domain edges are
        opt-in: the live graph already draws domain hub nodes, so they are noise (and quadratic). Links per
        entity are windowed and the total is capped, see MAX_EDGES. Files that ended up with no edge
        at all get one last directory link, see _link_orphans."""
        if index is None:
            def build():
                facts = self.source_facts()
                return self._link_orphans(self._compute_edges(self.view()[1], include_domains)
                                          + facts.get("imports", []) + facts.get("calls", []))
            return self._cached(("edges", include_domains), build)
        return self._link_orphans(self._compute_edges(index, include_domains))

    def _link_orphans(self, edges: List[dict]) -> List[dict]:
        """Directory fallback for files nothing connects to: one edge to a neighbour in the own
        folder, or behind the first orphan there when the folder has no linked file either — a lone
        island carries no information, and docs/config/assets share no table, route or event with
        anyone. Gated on a project root like source_facts, so rootless fixtures keep yielding pure
        edges."""
        if not self.get_meta("project_path"):
            return edges
        linked = {e["from"] for e in edges} | {e["to"] for e in edges}
        paths = sorted(f["path"] for f in self.all_files())
        anchors: Dict[str, str] = {}
        for p in paths:
            if p in linked:
                anchors.setdefault(_dir_of(p), p)
        extra = []
        for p in paths:
            if p in linked:
                continue
            d = _dir_of(p)
            anchor = anchors.get(d)
            if anchor is None:
                anchors[d] = p
                continue
            extra.append({"from": p, "to": anchor, "type": "path", "entity": d})
            linked.add(p)
        return edges + extra

    def source_facts(self) -> dict:
        """Import/call edges, derived tables/routes, roles and content records, read from the project
        files under project_path. {} without a root, so entity-less fixtures keep yielding no edges."""
        root = self.get_meta("project_path")
        if not root:
            return {}

        def build():
            files = self.all_files()
            empty = {f["path"] for f in files if not (f.get("summary") or "").strip()}
            return _source_facts(root, [f["path"] for f in files], empty)
        return self._cached("facts", build)

    def view(self) -> tuple:
        """(files, index) with the read-time facts folded into each row: derived tables/routes unioned
        with the stored ones, plus calls/content/role. Treat the rows as read-only — they are a view,
        never written back."""
        return self._cached("view", self._build_view)

    def _build_view(self) -> tuple:
        facts = self.source_facts()
        if not facts:
            files = self.all_files()
            return files, self._build_index(files)
        calls_by: Dict[str, list] = {}
        for e in facts["calls"]:
            calls_by.setdefault(e["from"], []).append([e["entity"], e["to"]])
        files = [self._annotate(f, facts, calls_by) for f in self.all_files()]
        return files, self._build_index(files)

    @staticmethod
    def _annotate(row: dict, facts: dict, calls_by: dict) -> dict:
        p = row["path"]
        out = dict(row)
        derived = facts["tables"].get(p)
        if derived:
            if p.endswith(".sql"):
                # stored .sql lists came from the old no-dot regex ('public' phantom, prose words):
                # scrub those, keep stored names the current regex may not see (TEMP/odd-quoted DDL)
                keep = [t for t in row["tables"] if t and "." not in t
                        and t.lower() not in _SQL_STOP and t.lower() != "public"]
                out["tables"] = list(dict.fromkeys(keep + derived))
            else:
                out["tables"] = list(dict.fromkeys(row["tables"] + derived))
        routes = facts["routes"].get(p)
        if routes:
            out["routes"] = list(dict.fromkeys(row["routes"] + routes))
        out["calls"] = calls_by.get(p, [])
        out["content"] = facts["content"].get(p, "")
        out["role"] = facts["roles"].get(p, "")
        return out

    @staticmethod
    def _compute_edges(index: dict, include_domains: bool) -> List[dict]:
        edges: List[dict] = []
        categories = [("table", "tables", MAX_PEERS_PER_ENTITY), ("route", "routes", MAX_PEERS_PER_ENTITY),
                      ("event", "events", MAX_PEERS_PER_ENTITY)]
        if include_domains:
            categories.insert(0, ("domain", "domains", MAX_DOMAIN_PEERS))
        degree: Dict[str, int] = {}
        for _, key, _ in categories:
            for paths in index.get(key, {}).values():
                for p in set(paths):
                    degree[p] = degree.get(p, 0) + 1
        for category, key, max_peers in categories:
            for entity_name, paths in sorted(index.get(key, {}).items()):
                unique = sorted(set(paths))
                if len(unique) > MAX_PAIRWISE_GROUP:
                    hub = min(unique, key=lambda p: (-degree.get(p, 0), p))
                    for p in unique:
                        if p == hub:
                            continue
                        if len(edges) >= MAX_EDGES:
                            return edges
                        edges.append({"from": hub, "to": p, "type": category, "entity": entity_name})
                    continue
                for i in range(len(unique)):
                    for j in range(i + 1, min(len(unique), i + 1 + max_peers)):
                        if len(edges) >= MAX_EDGES:
                            return edges
                        edges.append({"from": unique[i], "to": unique[j], "type": category, "entity": entity_name})
        return edges

    def communities(self) -> Dict[int, List[str]]:
        """Groups files by running modularity-based community detection (Louvain) over the
        table/route/event/domain co-occurrence graph, instead of one fixed bucket per domain
        keyword: two files land in the same cluster because the graph actually connects them
        (directly or through a chain of shared entities), not because a regex matched the same
        word in both paths. A project with no edges yet gets one singleton community per file.
        Community 0 is always the largest, and IDs are stable for a given graph (Louvain's own
        seed is fixed), so this is safe to call on every request."""
        return self._cached("communities", self._compute_communities)

    def _compute_communities(self) -> Dict[int, List[str]]:
        import networkx as nx

        all_paths = sorted(f["path"] for f in self.all_files())
        if not all_paths:
            return {}
        G = nx.Graph()
        G.add_nodes_from(all_paths)
        for e in self.graph_edges(include_domains=True):
            if G.has_edge(e["from"], e["to"]):
                G[e["from"]][e["to"]]["weight"] += 1
            else:
                G.add_edge(e["from"], e["to"], weight=1)
        if G.number_of_edges() == 0:
            return {i: [p] for i, p in enumerate(all_paths)}
        raw = nx.community.louvain_communities(G, weight="weight", seed=42)
        grouped = [sorted(c) for c in raw]
        grouped.sort(key=lambda nodes: (-len(nodes), nodes))
        return {i: nodes for i, nodes in enumerate(grouped)}

    def community_labels(self, communities: Optional[Dict[int, List[str]]] = None) -> Dict[int, str]:
        """Names each community after its highest-degree member (the structural hub it's built
        around) instead of a bare number, e.g. "server.py" rather than "Community 3". A cataloged
        asset (image, compiled binary, ...) is only picked as the hub when no analysed file in the
        community has an edge at all — a naming placeholder for the cluster, not a competitor for
        it. Ties break by path for determinism."""
        communities = communities if communities is not None else self.communities()
        degree: Dict[str, int] = {}
        for e in self.graph_edges(include_domains=True):
            degree[e["from"]] = degree.get(e["from"], 0) + 1
            degree[e["to"]] = degree.get(e["to"], 0) + 1
        is_asset = {f["path"]: f.get("source") == "asset" for f in self.all_files()}
        labels: Dict[int, str] = {}
        for cid, members in communities.items():
            if not members:
                labels[cid] = f"Community {cid}"
                continue
            hub = min(members, key=lambda p: (is_asset.get(p, False), -degree.get(p, 0), p))
            labels[cid] = Path(hub).name
        return labels

    def _row_to_dict(self, row) -> dict:
        def _parse(val):
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        keys = row.keys()
        return {
            "path": row["path"],
            "tables": _parse(row["tables"]),
            "routes": _parse(row["routes"]),
            "events": _parse(row["events"]),
            "domains": _parse(row["domains"]) if "domains" in keys else [],
            "summary": row["summary"],
            "updated_at": row["updated_at"],
            "mtime": row["mtime"],
            "content_hash": row["content_hash"] if "content_hash" in keys else "",
            "source": (row["source"] if "source" in keys else None) or "model",
        }
