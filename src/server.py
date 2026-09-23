"""Local API server for codebone — binds strictly to localhost (127.0.0.1:8053+).

Provides structured semantic codebase context over localhost HTTP.
"""
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Response

from .config import find_free_port
from .feedback import list_recent_feedback, record_feedback
from .service import CodeBoneService, PugService

logger = logging.getLogger("codebone.server")


def patch_mcp_configs(port: int, project_path: Optional[Path] = None):
    """Automatically patches Claude Desktop, Cursor, and Gemini/Antigravity MCP configs with the active port."""
    claude_cfg = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    cursor_global_cfg = Path.home() / ".cursor" / "mcp.json"
    gemini_global_cfg = Path.home() / ".gemini" / "config" / "mcp_config.json"
    gemini_ide_cfg = Path.home() / ".gemini" / "antigravity-ide" / "mcp_config.json"

    targets = [claude_cfg, cursor_global_cfg, gemini_global_cfg, gemini_ide_cfg]
    if project_path:
        targets.append(Path(project_path) / ".cursor" / "mcp.json")
        targets.append(Path(project_path) / ".gemini" / "mcp_config.json")
        targets.append(Path(project_path) / ".agents" / "mcp_config.json")

    # Ensure venv symlink if installed from DMG or App bundle
    app_support_venv = Path.home() / "Library" / "Application Support" / "codebone" / "venv"
    app_bundle_venv = Path("/Applications/codebone.app/Contents/Resources/venv")
    if not app_support_venv.exists() and app_bundle_venv.exists():
        try:
            app_support_venv.parent.mkdir(parents=True, exist_ok=True)
            app_support_venv.symlink_to(app_bundle_venv)
        except Exception:
            pass

    python_candidates = [
        app_support_venv / "bin" / "python3",
        app_support_venv / "bin" / "python",
        app_bundle_venv / "bin" / "python3",
        Path(__file__).resolve().parents[1] / "venv" / "bin" / "python3",
    ]
    python_cmd = "python3"
    for cand in python_candidates:
        if cand.exists():
            try:
                cand.chmod(cand.stat().st_mode | 0o755)
            except Exception:
                pass
            python_cmd = str(cand)
            break

    for target in targets:
        try:
            target_dir = target.parent
            if not target_dir.exists():
                if any(part in (".cursor", ".gemini", ".agents", "antigravity-ide") for part in target.parts):
                    target_dir.mkdir(parents=True, exist_ok=True)
                else:
                    continue

            data = {}
            if target.exists():
                try:
                    data = json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    data = {}

            if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                data["mcpServers"] = {}

            # Update or create 'codebone' entry
            codebone_entry = data["mcpServers"].get("codebone", {})
            if not codebone_entry or not isinstance(codebone_entry, dict):
                codebone_entry = {}

            codebone_entry["command"] = python_cmd
            codebone_entry["args"] = ["-m", "codebone_mcp.server"]
            env = codebone_entry.setdefault("env", {})
            env["CODEBONE_PORT"] = str(port)
            data["mcpServers"]["codebone"] = codebone_entry

            # If legacy 'pug' entry exists, update its port too
            if "pug" in data["mcpServers"]:
                pug_env = data["mcpServers"]["pug"].setdefault("env", {})
                pug_env["CODEBONE_PORT"] = str(port)
                pug_env["PUG_PORT"] = str(port)

            target.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("Auto-patched MCP config at %s with port %d", target, port)
        except Exception as exc:
            logger.warning("Could not auto-patch MCP config at %s: %s", target, exc)



def _format_context_markdown(service: CodeBoneService) -> str:
    storage = service.storage
    index = storage.entity_index()
    all_domains = service.storage.all_domains() or sorted(index.get("domains", {}).keys())
    file_count = service.storage.file_count()
    tables_count = len(index.get("tables", {}))
    routes_count = len(index.get("routes", {}))
    events_count = len(index.get("events", {}))
    edges_count = len(service.storage.graph_edges())

    lines = [
        "# codebone — High-Level Codebase Architecture",
        f"*Project: `{service.config.project_path}` | Files indexed: {file_count} | Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## 1. System Metrics & Architecture Summary",
        f"- **Indexed Files:** {file_count} source files",
        f"- **Business Domains:** {len(all_domains)} overarching domain categories",
        f"- **Database Models / Tables:** {tables_count} total detected across modules",
        f"- **API Routes / Endpoints:** {routes_count} total endpoints",
        f"- **Events & Logic Hooks:** {events_count} event triggers/handlers",
        f"- **Cross-Module Semantic Relationships:** {edges_count} conceptual links",
        "",
        "## 2. Business Domains & Systems",
        "Overarching functional domains discovered across the project:",
    ]

    if index.get("domains"):
        for domain, paths in sorted(index["domains"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
            files_str = ", ".join(f"`{p}`" for p in paths[:5])
            more = f" *(+{len(paths) - 5} more)*" if len(paths) > 5 else ""
            lines.append(f"- **`{domain}`** ({len(paths)} files: {files_str}{more})")
        lines.append("")
    elif all_domains:
        for d in all_domains:
            lines.append(f"- **`{d}`**")
        lines.append("")
    else:
        lines.append("*(No distinct business domains detected yet.)*")
        lines.append("")

    lines.extend([
        "---",
        "## 💡 Level-of-Detail (LOD) — Token-Saving Deep Dive",
        "To inspect lower-level entities, models, endpoints, and file summaries without wasting tokens on the full repository graph, call `codebone_context` with focused parameters:",
        "- **By Domain:** `codebone_context(domain=\"<domain_name>\")` *(e.g. `domain=\"Billing\"`)*",
        "- **By File/Module:** `codebone_context(file=\"<filename_or_path>\")` *(e.g. `file=\"service.py\"`)*",
        "- **By Entity/Keyword:** `codebone_context(query=\"<keyword>\")` *(e.g. `query=\"stripe\"` or `query=\"User\"`)*",
    ])

    return "\n".join(lines)


from .graph_ui import build_live_graph_html


def _build_live_graph_html(port: int) -> str:
    """Returns a self-contained interactive modern HTML5 canvas graph."""
    return build_live_graph_html(port)


def create_app(service: CodeBoneService) -> FastAPI:
    app = FastAPI(title="codebone", description="Local semantic knowledge graph server")

    @app.get("/codebone/status")
    @app.get("/pug/status")
    def status():
        return {
            "configured": service.config.is_configured,
            "project": str(service.config.project_path) if service.config.project_path else None,
            "sniffing": service.sniffing,
            "scan_progress": getattr(service, "scan_progress", None),
            "last_synced": service.last_synced,
            "last_error": getattr(service, "last_error", None),
            "last_reconciliation": service.last_reconciliation,
            "file_count": service.storage.file_count(),
            "brain_provider": service.config.get("brain_provider"),
            "brain_available": service.provider.available,
            "is_first_days": service.config.is_first_days(),
            "mcp_guide_url": "https://github.com/palusc/codebone#mcp-setup",
        }

    @app.get("/codebone/baseline")
    @app.get("/pug/baseline")
    def baseline():
        return service.inspect_baseline()

    @app.get("/codebone/context")
    @app.get("/pug/context")
    def context(format: str = "markdown", domain: str = "", file: str = "", query: str = ""):
        if not service.config.is_configured:
            msg = "codebone is not configured yet. Please select a project folder in the menu bar."
            return Response(content=msg, media_type="text/plain")

        # Level-of-Detail (LOD) filtering
        lod_filter = (domain or file or query).strip()
        if lod_filter:
            index = service.storage.entity_index()
            filtered_files: set[str] | None = None
            # Filter by domain
            if domain:
                domain_lower = domain.lower()
                matching_domains = [d for d in index.get("domains", {}) if domain_lower in d.lower()]
                filtered_files = set()
                for d in matching_domains:
                    filtered_files.update(index["domains"][d])
            # Filter by file substring
            if file:
                candidates = set(f["path"] for f in service.storage.all_files() if file.lower() in f["path"].lower())
                filtered_files = (filtered_files & candidates) if filtered_files is not None else candidates
            # Filter by query: match tables/routes/events/domains as well as file summary & path
            if query:
                query_lower = query.lower()
                q_files: set[str] = set()
                for cat in ("tables", "routes", "events", "domains"):
                    for entity, paths in index.get(cat, {}).items():
                        if query_lower in entity.lower():
                            q_files.update(paths)
                for f in service.storage.all_files():
                    if query_lower in f.get("summary", "").lower() or query_lower in f.get("path", "").lower():
                        q_files.add(f["path"])
                filtered_files = (filtered_files & q_files) if filtered_files is not None else q_files

            if format == "json":
                all_f = service.storage.all_files()
                filtered = [f for f in all_f if f["path"] in (filtered_files or set())]
                return {
                    "file_count": len(filtered),
                    "filter": {"domain": domain, "file": file, "query": query},
                    "files": filtered,
                    "generated_at": time.time(),
                }

            # Markdown LOD response
            filtered_index = service.storage.filtered_entity_index(filtered_files or set())
            active_domain_names = sorted(filtered_index.get("domains", {}).keys())
            models = sorted(filtered_index.get("tables", {}).keys())
            routes = sorted(filtered_index.get("routes", {}).keys())
            events = sorted(filtered_index.get("events", {}).keys())

            out_lines = [
                f"# codebone — Filtered Context (`{lod_filter}`)",
                f"Project: `{service.config.project_path}`",
                f"Matching files: {len(filtered_files or set())}",
                "",
                "## Matching Business Domains",
            ]
            out_lines.extend([f"- **{d}**" for d in active_domain_names] if active_domain_names else ["*(none)*"])
            out_lines.extend(["", "## Matching Database Models / Tables"])
            out_lines.extend([f"- `{m}`" for m in models] if models else ["*(none)*"])
            out_lines.extend(["", "## Matching API Routes / Endpoints"])
            out_lines.extend([f"- `{r}`" for r in routes] if routes else ["*(none)*"])
            out_lines.extend(["", "## Matching Events & Logic Hooks"])
            out_lines.extend([f"- `{e}`" for e in events] if events else ["*(none)*"])
            out_lines.extend(["", "## Filtered Source Files"])
            all_files_map = {f["path"]: f for f in service.storage.all_files()}
            for fp in sorted(filtered_files or set()):
                f_data = all_files_map.get(fp, {})
                f_domains = f_data.get("domains", [])
                out_lines.append(f"### `{fp}`" + (f" *({', '.join(f_domains)})*" if f_domains else ""))
                summary = f_data.get("summary", "")
                if summary:
                    out_lines.append(summary)
                f_routes = f_data.get("routes", [])
                if f_routes:
                    out_lines.append("**Routes:** " + ", ".join(f"`{r}`" for r in f_routes))
                f_tables = f_data.get("tables", [])
                if f_tables:
                    out_lines.append("**Tables:** " + ", ".join(f"`{t}`" for t in f_tables))
                out_lines.append("")

            return Response(content="\n".join(out_lines), media_type="text/markdown; charset=utf-8")

        if format == "json":
            entity_index = service.storage.entity_index()
            return {
                "file_count": service.storage.file_count(),
                "domains": service.storage.all_domains(),
                "entities": entity_index,
                "files": service.storage.all_files(),
                "graph_edges": service.storage.graph_edges(),
                "generated_at": time.time(),
            }

        return Response(content=_format_context_markdown(service), media_type="text/markdown; charset=utf-8")

    @app.get("/codebone/graph")
    @app.get("/pug/graph")
    def graph():
        all_files = service.storage.all_files()
        return {
            "nodes": [f["path"] for f in all_files],
            "files": {f["path"]: f for f in all_files},
            "edges": service.storage.graph_edges(),
        }

    @app.get("/codebone/graph/ui", response_class=Response)
    @app.get("/pug/graph/ui", response_class=Response)
    def graph_ui():
        port = service.config.get("active_port") or service.config.get("server_port", 8053)
        html = _build_live_graph_html(port)
        return Response(content=html, media_type="text/html; charset=utf-8")

    @app.get("/codebone/scans")
    @app.get("/pug/scans")
    def list_scans():
        scans = service.scans.list_scans()
        return {
            "scans": scans,
            "count": len(scans),
        }

    @app.post("/codebone/scans/adopt")
    @app.post("/pug/scans/adopt")
    def adopt_scan(payload: dict):
        scan_id = payload.get("scan_id")
        if scan_id and (".." in str(scan_id) or "/" in str(scan_id) or "\\" in str(scan_id)):
            raise HTTPException(status_code=400, detail="Invalid scan_id format (path traversal rejected)")

        scan_id_or_path = scan_id or payload.get("scan_path")
        if not scan_id_or_path:
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'scan_path'")

        project_path = payload.get("project_path")
        if project_path:
            p = Path(project_path).resolve()
            if not p.exists() or not p.is_dir():
                raise HTTPException(status_code=404, detail=f"Project path does not exist or is not a directory: {project_path}")
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

    @app.post("/codebone/scans/export")
    @app.post("/pug/scans/export")
    def export_scan(payload: dict):
        scan_id = payload.get("scan_id")
        dest_path = payload.get("dest_path")
        if not scan_id or not dest_path:
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'dest_path'")
        
        # Sanitize scan_id against directory traversal
        if ".." in str(scan_id) or "/" in str(scan_id) or "\\" in str(scan_id):
            raise HTTPException(status_code=400, detail="Invalid scan_id format (path traversal rejected)")

        dest = Path(dest_path).resolve()
        if not dest.parent.exists():
            raise HTTPException(status_code=400, detail="Destination directory does not exist")

        try:
            out = service.scans.export_scan(scan_id, dest)
            return {"status": "success", "exported_to": str(out)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/codebone/rescan")
    @app.post("/pug/rescan")
    def trigger_rescan():
        if not service.config.is_configured:
            raise HTTPException(status_code=400, detail="codebone is not configured with a project path.")
        threading.Thread(target=service.rescan_all, daemon=True, name="codebone-api-rescan").start()
        return {"status": "started", "message": "Full codebase rescan triggered in background."}

    @app.post("/codebone/feedback")
    @app.post("/pug/feedback")
    def submit_feedback(payload: dict):
        f_type = payload.get("type", "bug")
        title = payload.get("title", "")
        desc = payload.get("description", "")
        include_logs = bool(payload.get("include_logs", True))
        email = payload.get("email")

        extra_diag = {
            "project": str(service.config.project_path) if service.config.project_path else "none",
            "brain_provider": service.config.get("brain_provider"),
            "file_count": service.storage.file_count() if service.config.is_configured else 0,
            "connection_count": len(service.storage.graph_edges()) if service.config.is_configured else 0,
        }

        res = record_feedback(
            feedback_type=f_type,
            title=title,
            description=desc,
            include_logs=include_logs,
            email=email,
            extra_diagnostics=extra_diag,
        )
        return res

    @app.get("/codebone/feedback")
    @app.get("/pug/feedback")
    def get_feedback():
        return {
            "feedback": list_recent_feedback(20)
        }

    @app.post("/codebone/reset")
    @app.post("/pug/reset")
    def trigger_reset():
        service.reset_map()
        if service.config.is_configured:
            threading.Thread(target=service.rescan_all, daemon=True, name="codebone-api-reset-rescan").start()
        return {"status": "reset", "message": "Knowledge graph reset and re-indexing initiated."}

    return app



class ServerThread:
    """Runs uvicorn in a background daemon thread bound exclusively to 127.0.0.1."""

    def __init__(self, service: CodeBoneService, host: str = "127.0.0.1"):
        self.service = service
        self.host = host
        self.port = self.service.config.get("active_port") or self.service.config.get("server_port", 8053)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        desired_port = self.service.config.get("server_port", 8053)
        self.port = find_free_port(start_port=desired_port)
        self.service.config.set("active_port", self.port)
        app = create_app(self.service)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            ws="none",
            lifespan="off",
        )
        self._server = uvicorn.Server(config)

        def _run():
            try:
                self._server.run()
            except (Exception, SystemExit) as exc:
                logger.debug("codebone server stopped: %s", exc)

        self._thread = threading.Thread(target=_run, daemon=True, name="codebone-uvicorn")
        self._thread.start()
        logger.info("codebone server listening on http://%s:%d", self.host, self.port)

        try:
            patch_mcp_configs(self.port, self.service.config.project_path)
        except Exception as exc:
            logger.warning("Could not auto-patch MCP configs: %s", exc)

    def stop(self):
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def curl_command(self, path: str = "/codebone/context") -> str:
        return f"curl {self.url}{path}"

