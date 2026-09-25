"""Local API server for codebone — binds strictly to localhost (127.0.0.1:8053+).

Provides structured semantic codebase context over localhost HTTP.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import anthropic_bridge, context_format
from .config import find_free_port
from .feedback import list_recent_feedback, record_feedback
from .graph_ui import build_live_graph_html
from .service import CodeBoneService, PugService

logger = logging.getLogger("codebone.server")


def _resolve_python_cmd() -> str:
    """Interpreter MCP clients should launch. Also links Application Support/venv to the bundle so DMG installs
    look the same as install.sh installs (the npm bridge and old configs look there)."""
    app_support_venv = Path.home() / "Library" / "Application Support" / "codebone" / "venv"
    app_bundle_venv = Path(__file__).resolve().parents[2] / "venv"  # <app>/Contents/Resources/venv (any install dir)
    if not app_bundle_venv.is_dir():
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
    return python_cmd


def register_claude_cli(python_cmd: str):
    """Register codebone with Claude Code (user scope) so `cb` works in the terminal / VS Code no matter how
    codebone was installed. Idempotent; runs in the background because the claude CLI can be slow."""
    import shutil
    import subprocess

    def _run():
        claude = shutil.which("claude") or next(
            (str(p) for p in (Path.home() / ".local" / "bin" / "claude", Path("/opt/homebrew/bin/claude"),
                              Path("/usr/local/bin/claude"), Path.home() / ".claude" / "local" / "claude") if p.exists()),
            None,
        )
        if not claude:
            return
        try:
            cfg = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
            entry = (cfg.get("mcpServers") or {}).get("codebone") or {}
            if entry.get("command") == python_cmd and entry.get("args") == ["-m", "codebone_mcp.server"]:
                return
        except Exception:
            pass
        try:
            subprocess.run([claude, "mcp", "remove", "-s", "user", "codebone"], capture_output=True, timeout=30)
            subprocess.run([claude, "mcp", "add", "-s", "user", "codebone", "--", python_cmd, "-m", "codebone_mcp.server"],
                           capture_output=True, timeout=30)
            logger.info("Registered codebone with Claude Code")
        except Exception as exc:
            logger.warning("Could not register with Claude Code: %s", exc)

    threading.Thread(target=_run, daemon=True, name="codebone-claude-register").start()


def patch_mcp_configs(port: int, project_path: Optional[Path] = None):
    """Keep the global MCP client configs (Claude Desktop, Cursor, Gemini/Antigravity) pointing at this install's
    interpreter. Only clients that are installed are touched, nothing is written into project folders, and the
    port is deliberately not pinned: the MCP server reads the live port from codebone's config on every launch.
    (port and project_path are accepted for compatibility.)"""
    if os.environ.get("CODEBONE_NO_MCP_PATCH"):
        return
    home = Path.home()
    targets = [
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        home / ".cursor" / "mcp.json",
        home / ".gemini" / "config" / "mcp_config.json",
        home / ".gemini" / "antigravity-ide" / "mcp_config.json",
    ]

    python_cmd = _resolve_python_cmd()
    register_claude_cli(python_cmd)

    for target in targets:
        try:
            if not target.parent.exists():
                continue  # that client is not installed
            data = {}
            if target.exists():
                try:
                    data = json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    # Never overwrite a config we cannot parse (user edits, comments): it may hold other servers.
                    logger.warning("Skipping unreadable MCP config %s", target)
                    continue
                if not isinstance(data, dict):
                    continue

            servers = data.get("mcpServers")
            if not isinstance(servers, dict):
                servers = data["mcpServers"] = {}

            entry = servers.get("codebone")
            if not isinstance(entry, dict):
                entry = {}
            entry["command"] = python_cmd
            entry["args"] = ["-m", "codebone_mcp.server"]
            env = entry.get("env")
            if isinstance(env, dict):
                env.pop("CODEBONE_PORT", None)  # older versions pinned the port, which goes stale
                if not env:
                    entry.pop("env")
            servers["codebone"] = entry

            new_text = json.dumps(data, indent=2)
            if target.exists() and target.read_text(encoding="utf-8") == new_text:
                continue
            target.write_text(new_text, encoding="utf-8")
            logger.info("Updated MCP config %s", target)
        except Exception as exc:
            logger.warning("Could not update MCP config at %s: %s", target, exc)


_SAFE_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_TEXT = 5000


def _text(payload: dict, key: str, limit: int = _MAX_TEXT) -> str:
    val = payload.get(key, "")
    return val[:limit] if isinstance(val, str) else ""


def _reject_unsafe_id(value) -> None:
    if value and (".." in str(value) or "/" in str(value) or "\\" in str(value)):
        raise HTTPException(status_code=400, detail="Invalid scan_id format (path traversal rejected)")


def create_app(service: CodeBoneService, allowed_hosts: Optional[set] = None) -> FastAPI:
    # No interactive docs: they load Swagger UI from a CDN and add nothing for a local tool.
    app = FastAPI(title="codebone", description="Local semantic knowledge graph server",
                  docs_url=None, redoc_url=None, openapi_url=None)
    hosts = _SAFE_HOSTS | set(allowed_hosts or ())

    @app.middleware("http")
    async def guard(request: Request, call_next):
        """Any web page can send requests to 127.0.0.1. Refuse DNS-rebinding (foreign Host header) and
        cross-origin browser requests (foreign Origin/Referer); local tools (curl, MCP) send neither."""
        host_header = (request.headers.get("host") or "").lower()
        hostname = urlsplit("//" + host_header).hostname or ""
        if hostname not in hosts:
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
        for header in ("origin", "referer"):
            value = request.headers.get(header)
            if value and urlsplit(value).netloc.lower() != host_header:
                return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def project_name() -> str:
        p = service.config.project_path
        return p.name if p else "project"

    @app.get("/codebone/status")
    @app.get("/pug/status")
    def status():
        return {
            "configured": service.config.is_configured,
            "project": str(service.config.project_path) if service.config.project_path else None,
            "sniffing": service.sniffing,
            "scanning": service.scanning,
            "scan_progress": service.scan_progress,
            "last_synced": service.last_synced,
            "last_error": service.last_error,
            "last_reconciliation": service.last_reconciliation,
            "file_count": service.storage.file_count(),
            "revision": service.storage.revision,
            "brain_provider": service.config.get("brain_provider"),
            "brain_available": service.provider.ready,  # never loads the model
            "model_status": service.model_status,
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

        storage = service.storage
        files, index = storage.view()
        name = project_name()
        domain, file, query = domain.strip(), file.strip(), query.strip()
        filtered = bool(domain or file or query)

        if format == "json":
            if filtered:
                return context_format.search_json(name, files, index, storage.revision, domain, file, query)
            return context_format.overview_json(name, files, index, storage.revision)
        text = (context_format.search(name, files, index, domain, file, query) if filtered
                else context_format.overview(name, files, index))
        return Response(content=text, media_type="text/markdown; charset=utf-8")

    @app.get("/codebone/links")
    def links(file: str = ""):
        if not service.config.is_configured:
            return Response(content="codebone is not configured yet.", media_type="text/plain")
        storage = service.storage
        files, index = storage.view()
        text = context_format.links(project_name(), files, index, file.strip(), facts=storage.source_facts())
        return Response(content=text, media_type="text/markdown; charset=utf-8")

    @app.get("/codebone/graph")
    @app.get("/pug/graph")
    def graph():
        storage = service.storage
        all_files = storage.view()[0]
        communities = storage.communities()
        return {
            "revision": storage.revision,
            "nodes": [f["path"] for f in all_files],
            "files": {f["path"]: f for f in all_files},
            "edges": storage.graph_edges(),
            # Real graph structure (modularity clustering over shared tables/routes/events/domains),
            # not a fixed bucket per domain keyword — see Storage.communities().
            "communities": [
                {"id": cid, "label": label, "files": communities[cid]}
                for cid, label in storage.community_labels(communities).items()
            ],
        }

    @app.get("/codebone/graph/ui", response_class=Response)
    @app.get("/pug/graph/ui", response_class=Response)
    def graph_ui():
        port = service.config.get("active_port") or service.config.get("server_port", 8053)
        return Response(
            content=build_live_graph_html(port),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                           "img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'",
            },
        )

    @app.get("/codebone/scans")
    @app.get("/pug/scans")
    def list_scans():
        scans = service.scans.list_scans()
        return {"scans": scans, "count": len(scans)}

    @app.post("/codebone/scans/adopt")
    @app.post("/pug/scans/adopt")
    def adopt_scan(payload: dict):
        scan_id = payload.get("scan_id")
        _reject_unsafe_id(scan_id)
        scan_id_or_path = scan_id or payload.get("scan_path")
        if not scan_id_or_path or not isinstance(scan_id_or_path, str):
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'scan_path'")
        if service.scanning:
            raise HTTPException(status_code=409, detail="A scan is already running")

        project_path = payload.get("project_path")
        if project_path:
            if not isinstance(project_path, str):
                raise HTTPException(status_code=400, detail="'project_path' must be a string")
            p = Path(project_path).expanduser().resolve()
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
            return {"status": "success", "message": "Scan adopted and reconciled successfully", "report": report}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/codebone/scans/export")
    @app.post("/pug/scans/export")
    def export_scan(payload: dict):
        scan_id = payload.get("scan_id")
        dest_path = payload.get("dest_path")
        if not scan_id or not dest_path or not isinstance(dest_path, str):
            raise HTTPException(status_code=400, detail="Missing 'scan_id' or 'dest_path'")
        _reject_unsafe_id(scan_id)

        dest = Path(dest_path).expanduser().resolve()
        if not dest.parent.exists():
            raise HTTPException(status_code=400, detail="Destination directory does not exist")
        try:
            out = service.scans.export_scan(scan_id, dest)
            return {"status": "success", "exported_to": str(out)}
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/codebone/rescan")
    @app.post("/pug/rescan")
    def trigger_rescan():
        if not service.config.is_configured:
            raise HTTPException(status_code=400, detail="codebone is not configured with a project path.")
        if service.scanning:
            return {"status": "running", "message": "A scan is already running."}
        threading.Thread(target=service.rescan_all, daemon=True, name="codebone-api-rescan").start()
        return {"status": "started", "message": "Full codebase rescan triggered in background."}

    @app.post("/codebone/feedback")
    @app.post("/pug/feedback")
    def submit_feedback(payload: dict):
        f_type = _text(payload, "type", 20) or "bug"
        extra_diag = {
            "project": str(service.config.project_path) if service.config.project_path else "none",
            "brain_provider": service.config.get("brain_provider"),
            "file_count": service.storage.file_count() if service.config.is_configured else 0,
            "connection_count": len(service.storage.graph_edges(include_domains=True)) if service.config.is_configured else 0,
        }
        return record_feedback(
            feedback_type=f_type,
            title=_text(payload, "title", 200),
            description=_text(payload, "description"),
            include_logs=bool(payload.get("include_logs", True)),
            email=_text(payload, "email", 200) or None,
            extra_diagnostics=extra_diag,
        )

    @app.get("/codebone/feedback")
    @app.get("/pug/feedback")
    def get_feedback():
        return {"feedback": list_recent_feedback(20)}

    @app.post("/codebone/reset")
    @app.post("/pug/reset")
    def trigger_reset():
        if service.scanning:
            return {"status": "running", "message": "A scan is running; reset after it finishes."}
        service.reset_map()
        if service.config.is_configured:
            threading.Thread(target=service.rescan_all, daemon=True, name="codebone-api-reset-rescan").start()
        return {"status": "reset", "message": "Knowledge graph reset and re-indexing initiated."}

    anthropic_bridge.register(app, service.config)

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
                logger.error("codebone server stopped: %s", exc)

        self._thread = threading.Thread(target=_run, daemon=True, name="codebone-uvicorn")
        self._thread.start()
        for _ in range(100):  # wait until the socket is really open (or the thread died)
            if self._server.started or not self._thread.is_alive():
                break
            time.sleep(0.05)
        if not self._server.started:
            self.service.last_error = f"Local server could not start on port {self.port}"
            logger.error("%s", self.service.last_error)
            return
        logger.info("codebone server listening on http://%s:%d", self.host, self.port)

        try:
            patch_mcp_configs(self.port)
        except Exception as exc:
            logger.warning("Could not update MCP configs: %s", exc)

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

