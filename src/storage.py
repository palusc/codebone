"""Internal SQLite store for PUG's semantic knowledge graph."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from .prompts import parse_analysis

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    tables TEXT NOT NULL,
    routes TEXT NOT NULL,
    events TEXT NOT NULL,
    summary TEXT NOT NULL,
    updated_at REAL NOT NULL,
    mtime REAL DEFAULT 0,
    content_hash TEXT DEFAULT ''
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
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
        self._has_entities_col = "entities" in columns

    def update_file(
        self,
        rel_path: str,
        raw_output: str,
        mtime: float = 0.0,
        content_hash: str = "",
    ) -> dict:
        tables, routes, events, summary = parse_analysis(raw_output)

        if self._has_entities_col:
            all_entities = json.dumps(tables + routes + events)
            self._conn.execute(
                """
                INSERT INTO files (path, entities, tables, routes, events, summary, updated_at, mtime, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    entities = excluded.entities,
                    tables = excluded.tables,
                    routes = excluded.routes,
                    events = excluded.events,
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
                    summary,
                    time.time(),
                    mtime,
                    content_hash,
                ),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO files (path, tables, routes, events, summary, updated_at, mtime, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    tables = excluded.tables,
                    routes = excluded.routes,
                    events = excluded.events,
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
            "summary": summary,
        }

    def get_file_mtimes(self) -> Dict[str, float]:
        rows = self._conn.execute("SELECT path, COALESCE(mtime, 0) as mtime FROM files").fetchall()
        return {r["path"]: float(r["mtime"]) for r in rows}

    def get_file_hashes(self) -> Dict[str, str]:
        rows = self._conn.execute("SELECT path, COALESCE(content_hash, '') as h FROM files").fetchall()
        return {r["path"]: r["h"] for r in rows}

    def remove_file(self, rel_path: str):
        self._conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        self._conn.commit()

    def remove_files(self, rel_paths: List[str]):
        if not rel_paths:
            return
        self._conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in rel_paths])
        self._conn.commit()

    def reset(self):
        self._conn.execute("DELETE FROM files")
        self._conn.commit()

    def get_file(self, rel_path: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM files WHERE path = ?", (rel_path,)).fetchone()
        return self._row_to_dict(row) if row else None

    def all_files(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM files ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def recent(self, limit: int = 15) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM files ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def file_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def entity_index(self) -> dict:
        """Returns inverted indexes: table -> [files], route -> [files], event -> [files]."""
        tables_map: Dict[str, List[str]] = {}
        routes_map: Dict[str, List[str]] = {}
        events_map: Dict[str, List[str]] = {}

        for entry in self.all_files():
            p = entry["path"]
            for t in entry.get("tables", []):
                tables_map.setdefault(t, []).append(p)
            for r in entry.get("routes", []):
                routes_map.setdefault(r, []).append(p)
            for e in entry.get("events", []):
                events_map.setdefault(e, []).append(p)

        return {
            "tables": tables_map,
            "routes": routes_map,
            "events": events_map,
        }

    def graph_edges(self) -> List[dict]:
        """Files are logically connected if they share a DB table, API route, or event."""
        edges = []
        index = self.entity_index()

        for category, cat_map in [
            ("table", index["tables"]),
            ("route", index["routes"]),
            ("event", index["events"]),
        ]:
            for entity_name, paths in cat_map.items():
                unique = sorted(set(paths))
                for i in range(len(unique)):
                    for j in range(i + 1, len(unique)):
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
            "summary": row["summary"],
            "updated_at": row["updated_at"],
            "mtime": row["mtime"],
        }
