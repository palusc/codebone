"""Internal SQLite store for codebone's semantic knowledge graph."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from .prompts import parse_analysis

import threading

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
    content_hash TEXT DEFAULT ''
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        cursor = self._conn.execute("PRAGMA table_info(files)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "content_hash" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN content_hash TEXT DEFAULT ''")
        if "tables" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN tables TEXT DEFAULT '[]'")
        if "routes" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN routes TEXT DEFAULT '[]'")
        if "events" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN events TEXT DEFAULT '[]'")
        if "domains" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN domains TEXT DEFAULT '[]'")
        self._has_entities_col = "entities" in columns

    def update_file(
        self,
        rel_path: str,
        raw_output: str,
        mtime: float = 0.0,
        content_hash: str = "",
    ) -> dict:
        tables, routes, events, domains, summary = parse_analysis(raw_output)

        with self._lock:
            if self._has_entities_col:
                all_entities = json.dumps(tables + routes + events + domains)
                self._conn.execute(
                    """
                    INSERT INTO files (path, entities, tables, routes, events, domains, summary, updated_at, mtime, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        entities = excluded.entities,
                        tables = excluded.tables,
                        routes = excluded.routes,
                        events = excluded.events,
                        domains = excluded.domains,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at,
                        mtime = excluded.mtime,
                        content_hash = excluded.content_hash
                    """,
                    (
                        rel_path,
                        all_entities,
                        json.dumps(tables),
                        json.dumps(routes),
                        json.dumps(events),
                        json.dumps(domains),
                        summary,
                        time.time(),
                        mtime,
                        content_hash,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO files (path, tables, routes, events, domains, summary, updated_at, mtime, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        tables = excluded.tables,
                        routes = excluded.routes,
                        events = excluded.events,
                        domains = excluded.domains,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at,
                        mtime = excluded.mtime,
                        content_hash = excluded.content_hash
                    """,
                    (
                        rel_path,
                        json.dumps(tables),
                        json.dumps(routes),
                        json.dumps(events),
                        json.dumps(domains),
                        summary,
                        time.time(),
                        mtime,
                        content_hash,
                    ),
                )
            self._conn.commit()

        return {
            "path": rel_path,
            "tables": tables,
            "routes": routes,
            "events": events,
            "domains": domains,
            "summary": summary,
        }

    def get_file_mtimes(self) -> Dict[str, float]:
        with self._lock:
            rows = self._conn.execute("SELECT path, COALESCE(mtime, 0) as mtime FROM files").fetchall()
            return {r["path"]: float(r["mtime"]) for r in rows}

    def get_file_hashes(self) -> Dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT path, COALESCE(content_hash, '') as h FROM files").fetchall()
            return {r["path"]: r["h"] for r in rows}

    def remove_file(self, rel_path: str):
        with self._lock:
            self._conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
            self._conn.commit()

    def remove_files(self, rel_paths: List[str]):
        if not rel_paths:
            return
        with self._lock:
            self._conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in rel_paths])
            self._conn.commit()

    def reset(self):
        with self._lock:
            self._conn.execute("DELETE FROM files")
            self._conn.commit()

    def snapshot_to(self, dest_path: Path):
        """Atomically copy the SQLite database to a snapshot file."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = dest_path.with_suffix(".tmp")
        with self._lock:
            bck = sqlite3.connect(str(tmp_dest))
            with bck:
                self._conn.backup(bck)
            bck.close()
        import os
        os.replace(tmp_dest, dest_path)

    def restore_from(self, source_path: Path):
        """Atomically restore the SQLite database from a snapshot file."""
        src = sqlite3.connect(str(source_path))
        with self._lock:
            with self._conn:
                src.backup(self._conn)
            self._migrate()
        src.close()

    def get_records_by_hash(self) -> Dict[str, List[dict]]:
        """Maps content_hash to list of file records (used for rename/move detection)."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM files WHERE content_hash != ''").fetchall()
            result: Dict[str, List[dict]] = {}
            for r in rows:
                d = self._row_to_dict(r)
                result.setdefault(r["content_hash"], []).append(d)
            return result

    def insert_record(self, entry: dict):
        """Insert or replace a pre-existing analysis record."""
        path = entry["path"]
        tables = entry.get("tables", [])
        routes = entry.get("routes", [])
        events = entry.get("events", [])
        domains = entry.get("domains", [])
        summary = entry.get("summary", "")
        updated_at = entry.get("updated_at", time.time())
        mtime = entry.get("mtime", 0.0)
        content_hash = entry.get("content_hash", "")

        with self._lock:
            if self._has_entities_col:
                all_entities = json.dumps(tables + routes + events + domains)
                self._conn.execute(
                    """
                    INSERT INTO files (path, entities, tables, routes, events, domains, summary, updated_at, mtime, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        entities = excluded.entities,
                        tables = excluded.tables,
                        routes = excluded.routes,
                        events = excluded.events,
                        domains = excluded.domains,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at,
                        mtime = excluded.mtime,
                        content_hash = excluded.content_hash
                    """,
                    (
                        path,
                        all_entities,
                        json.dumps(tables),
                        json.dumps(routes),
                        json.dumps(events),
                        json.dumps(domains),
                        summary,
                        updated_at,
                        mtime,
                        content_hash,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO files (path, tables, routes, events, domains, summary, updated_at, mtime, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        tables = excluded.tables,
                        routes = excluded.routes,
                        events = excluded.events,
                        domains = excluded.domains,
                        summary = excluded.summary,
                        updated_at = excluded.updated_at,
                        mtime = excluded.mtime,
                        content_hash = excluded.content_hash
                    """,
                    (
                        path,
                        json.dumps(tables),
                        json.dumps(routes),
                        json.dumps(events),
                        json.dumps(domains),
                        summary,
                        updated_at,
                        mtime,
                        content_hash,
                    ),
                )
            self._conn.commit()

    def get_file(self, rel_path: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM files WHERE path = ?", (rel_path,)).fetchone()
            return self._row_to_dict(row) if row else None

    def all_files(self) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM files ORDER BY updated_at DESC"
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def recent(self, limit: int = 15) -> List[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM files ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def file_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def entity_index(self) -> dict:
        """Returns inverted indexes: table -> [files], route -> [files], event -> [files], domain -> [files]."""
        tables_map: Dict[str, List[str]] = {}
        routes_map: Dict[str, List[str]] = {}
        events_map: Dict[str, List[str]] = {}
        domains_map: Dict[str, List[str]] = {}

        for entry in self.all_files():
            p = entry["path"]
            for t in entry.get("tables", []):
                tables_map.setdefault(t, []).append(p)
            for r in entry.get("routes", []):
                routes_map.setdefault(r, []).append(p)
            for e in entry.get("events", []):
                events_map.setdefault(e, []).append(p)
            for d in entry.get("domains", []):
                domains_map.setdefault(d, []).append(p)

        return {
            "tables": tables_map,
            "routes": routes_map,
            "events": events_map,
            "domains": domains_map,
        }

    def all_domains(self) -> List[str]:
        """Returns sorted list of all unique domain names across the codebase."""
        idx = self.entity_index()
        return sorted(list(idx.get("domains", {}).keys()))

    def filtered_entity_index(self, allowed_paths: set[str]) -> dict:
        """Returns inverted indexes filtered to a specific set of file paths."""
        tables_map: Dict[str, List[str]] = {}
        routes_map: Dict[str, List[str]] = {}
        events_map: Dict[str, List[str]] = {}
        domains_map: Dict[str, List[str]] = {}

        for entry in self.all_files():
            p = entry["path"]
            if p not in allowed_paths:
                continue
            for t in entry.get("tables", []):
                tables_map.setdefault(t, []).append(p)
            for r in entry.get("routes", []):
                routes_map.setdefault(r, []).append(p)
            for e in entry.get("events", []):
                events_map.setdefault(e, []).append(p)
            for d in entry.get("domains", []):
                domains_map.setdefault(d, []).append(p)

        return {
            "tables": tables_map,
            "routes": routes_map,
            "events": events_map,
            "domains": domains_map,
        }

    def graph_edges(self) -> List[dict]:
        """Files are logically connected if they share an overarching domain, DB table, API route, or event."""
        edges = []
        index = self.entity_index()

        for category, cat_map in [
            ("domain", index.get("domains", {})),
            ("table", index.get("tables", {})),
            ("route", index.get("routes", {})),
            ("event", index.get("events", {})),
        ]:
            for entity_name, paths in cat_map.items():
                unique = sorted(set(paths))
                # Fan-out safeguard: cap neighbor pairs per entity to avoid O(N^2) browser freezing
                max_peers = 15 if category == "domain" else 25
                for i in range(len(unique)):
                    limit = min(len(unique), i + 1 + max_peers)
                    for j in range(i + 1, limit):
                        edges.append({
                            "from": unique[i],
                            "to": unique[j],
                            "type": category,
                            "entity": entity_name,
                        })
        return edges

    def _row_to_dict(self, row) -> dict:
        def _parse(val):
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        return {
            "path": row["path"],
            "tables": _parse(row["tables"]),
            "routes": _parse(row["routes"]),
            "events": _parse(row["events"]),
            "domains": _parse(row["domains"]) if "domains" in row.keys() else [],
            "summary": row["summary"],
            "updated_at": row["updated_at"],
            "mtime": row["mtime"],
            "content_hash": row["content_hash"] if "content_hash" in row.keys() else "",
        }
