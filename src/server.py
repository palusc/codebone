"""Local API server for PUG — binds strictly to localhost (127.0.0.1:3000).

Provides structured semantic codebase context over localhost HTTP.
"""
import logging
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Response

from .service import PugService

logger = logging.getLogger("pug.server")


def _format_context_markdown(service: PugService) -> str:
    storage = service.storage
    index = storage.entity_index()
    recent = storage.recent(10)
    edges = storage.graph_edges()

    lines = [
        "# PUG — Codebase Context",
        f"*Status: {service.storage.file_count()} files indexed | Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
    ]

    # Business Domains & Systems
    if index.get("domains"):
        lines.append("## 1. Business Domains & Systems")
        for domain, paths in sorted(index["domains"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
            files_str = ", ".join(f"`{p}`" for p in paths[:4])
            more = f" (+{len(paths) - 4} more)" if len(paths) > 4 else ""
            lines.append(f"- **`{domain}`** (in: {files_str}{more})")
        lines.append("")

    has_components = bool(index["tables"] or index["routes"] or index["events"])
    if has_components:
        lines.append("## 2. Components & Entities")

        # Tables
        if index["tables"]:
            lines.append("### Database Tables & Models")
            for table, paths in sorted(index["tables"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
                files_str = ", ".join(f"`{p}`" for p in paths[:3])
                more = f" (+{len(paths) - 3} more)" if len(paths) > 3 else ""
                lines.append(f"- **`{table}`** (in: {files_str}{more})")
            lines.append("")

        # Routes
        if index["routes"]:
            lines.append("### API Endpoints")
            for route, paths in sorted(index["routes"].items()):
                lines.append(f"- **`{route}`** (`{', '.join(paths)}`)")
            lines.append("")

        # Events
        if index["events"]:
            lines.append("### Events & Signals")
            for event, paths in sorted(index["events"].items()):
                lines.append(f"- **`{event}`** (`{', '.join(paths)}`)")
            lines.append("")
    elif not index.get("domains"):
        lines.append("## 2. Components & Entities")
        lines.append("*No explicit tables, routes, or events detected.*")
        lines.append("")

    # 3. Semantic System Graph
    lines.append("## 3. Semantic System Graph")
    lines.append("*Maps cross-module business relationships beyond rigid code imports.*")
    lines.append("")
    if edges:
        for edge in edges[:20]:
            lines.append(f"- `{edge['from']}` <-> `{edge['to']}` (via {edge['type']}: **{edge['entity']}**)")
        if len(edges) > 20:
            lines.append(f"- *... and {len(edges) - 20} more connections.*")
    else:
        lines.append("*No cross-file conceptual or entity connections detected.*")
    lines.append("")

    # 4. Recent logical changes
    lines.append("## 4. Recent Changes")
    if recent:
        for entry in recent:
            p = entry["path"]
            s = entry["summary"] or "No summary available."
            lines.append(f"- **`{p}`**: {s}")
    else:
        lines.append("*No changes recorded yet.*")

    return "\n".join(lines)


def create_app(service: PugService) -> FastAPI:
    app = FastAPI(title="PUG", description="Local semantic knowledge graph server")

    @app.get("/pug/status")
    def status():
        return {
            "configured": service.config.is_configured,
            "project": str(service.config.project_path) if service.config.project_path else None,
            "sniffing": service.sniffing,
            "last_synced": service.last_synced,
            "last_reconciliation": service.last_reconciliation,
            "file_count": service.storage.file_count(),
            "brain_provider": service.config.get("brain_provider"),
            "brain_available": service.provider.available,
        }

    @app.get("/pug/context")
    def context(format: str = "markdown"):
        if not service.config.is_configured:
            msg = "PUG is not configured yet. Please select a project folder in the menu bar."
            return Response(content=msg, media_type="text/plain")

        if format == "json":
            return {
                "file_count": service.storage.file_count(),
                "entities": service.storage.entity_index(),
                "graph": service.storage.graph_edges(),
                "recent_changes": service.storage.recent(15),
                "generated_at": time.time(),
            }

        return Response(content=_format_context_markdown(service), media_type="text/markdown; charset=utf-8")

    @app.get("/pug/graph")
    def graph():
        return {
            "nodes": [f["path"] for f in service.storage.all_files()],
            "edges": service.storage.graph_edges(),
        }

    @app.get("/pug/scans")
    def list_scans():
        scans = service.scans.list_scans()
        return {
            "scans": scans,
            "count": len(scans),
        }

    @app.post("/pug/scans/adopt")
    def adopt_scan(payload: dict):
        scan_id_or_path = payload.get("scan_id") or payload.get("scan_path")
        if not scan_id_or_path:
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'scan_path'")

        project_path = payload.get("project_path")
        if project_path:
            p = Path(project_path)
            if not p.exists():
                raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
            service.config.set("project_path", str(p))
            service.stop()
            service.start(auto_scan=False)

        if not service.config.is_configured:
            raise HTTPException(
                status_code=400,
                detail="No project folder configured. Provide 'project_path' or configure via menu bar.",
            )

        try:
            report = service.adopt_scan(scan_id_or_path)
            return {
                "status": "success",
                "message": "Scan adopted and reconciled successfully",
                "report": report,
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/pug/scans/export")
    def export_scan(payload: dict):
        scan_id = payload.get("scan_id")
        dest_path = payload.get("dest_path")
        if not scan_id or not dest_path:
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'dest_path'")
        try:
            out = service.scans.export_scan(scan_id, Path(dest_path))
            return {"status": "success", "exported_to": str(out)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return app


class ServerThread:
    """Runs uvicorn in a background daemon thread bound exclusively to 127.0.0.1."""

    def __init__(self, service: PugService, host: str = "127.0.0.1"):
        self.service = service
        self.host = host
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        port = self.service.config.get("server_port", 3000)
        app = create_app(self.service)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=port,
            log_level="warning",
            ws="none",
            lifespan="off",
        )
        self._server = uvicorn.Server(config)

        def _run():
            try:
                self._server.run()
            except Exception as exc:
                logger.exception("PUG server thread encountered error: %s", exc)

        self._thread = threading.Thread(target=_run, daemon=True, name="pug-uvicorn")
        self._thread.start()
        logger.info("PUG server listening on http://%s:%d", self.host, port)

    def stop(self):
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        port = self.service.config.get("server_port", 3000)
        return f"http://{self.host}:{port}"

    def curl_command(self, path: str = "/pug/context") -> str:
        return f"curl {self.url}{path}"
