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


def _build_live_graph_html(port: int) -> str:
    """Returns a self-contained interactive dark-mode HTML5 canvas graph."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PUG — Live Code Graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0b0c10; color: #c5c6c7; font-family: 'Segoe UI', system-ui, sans-serif; overflow: hidden; }}
  #canvas {{ display: block; cursor: grab; }}
  #canvas:active {{ cursor: grabbing; }}
  #sidebar {{
    position: fixed; right: 0; top: 0; width: 300px; height: 100vh;
    background: rgba(15,17,23,0.97); border-left: 1px solid #1f2a3a;
    padding: 20px; overflow-y: auto; transform: translateX(100%);
    transition: transform 0.25s ease; backdrop-filter: blur(10px); z-index: 10;
  }}
  #sidebar.open {{ transform: translateX(0); }}
  #sidebar h2 {{ color: #66fcf1; font-size: 14px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  #sidebar h3 {{ color: #45a29e; font-size: 12px; margin: 12px 0 6px; }}
  #sidebar ul {{ list-style: none; }}
  #sidebar li {{ font-size: 11px; color: #c5c6c7; padding: 2px 0; border-bottom: 1px solid #1a2030; }}
  #sidebar p {{ font-size: 12px; color: #888; line-height: 1.5; }}
  #close-btn {{
    position: absolute; top: 12px; right: 12px; background: none; border: none;
    color: #66fcf1; font-size: 18px; cursor: pointer; opacity: 0.7;
  }}
  #close-btn:hover {{ opacity: 1; }}
  #hud {{
    position: fixed; top: 16px; left: 16px; z-index: 5;
    display: flex; flex-direction: column; gap: 6px;
  }}
  #title {{ font-size: 16px; font-weight: 700; color: #66fcf1; letter-spacing: 0.5px; }}
  #subtitle {{ font-size: 11px; color: #45a29e; }}
  #stats {{ font-size: 11px; color: #888; margin-top: 4px; }}
  #legend {{
    position: fixed; bottom: 16px; left: 16px; z-index: 5;
    display: flex; gap: 14px; align-items: center;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 11px; color: #888; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .domain {{ background: #7c3aed; }}
  .file {{ background: #10b981; }}
  .route {{ background: #06b6d4; }}
  .table {{ background: #f59e0b; }}
  .event {{ background: #f43f5e; }}
  #loading {{
    position: fixed; inset: 0; background: #0b0c10; display: flex;
    align-items: center; justify-content: center; z-index: 100; flex-direction: column; gap: 14px;
  }}
  .spinner {{
    width: 40px; height: 40px; border: 3px solid #1f2a3a;
    border-top-color: #66fcf1; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<div id="loading">
  <div class="spinner"></div>
  <div style="color:#66fcf1;font-size:13px;">Building graph…</div>
</div>
<canvas id="canvas"></canvas>
<div id="hud">
  <div id="title">🦴 PUG Live Graph</div>
  <div id="subtitle">Semantic System Graph</div>
  <div id="stats">Loading…</div>
</div>
<div id="legend">
  <div class="legend-item"><div class="dot domain"></div>Domain</div>
  <div class="legend-item"><div class="dot file"></div>File</div>
  <div class="legend-item"><div class="dot route"></div>Route</div>
  <div class="legend-item"><div class="dot table"></div>Table</div>
  <div class="legend-item"><div class="dot event"></div>Event</div>
</div>
<div id="sidebar">
  <button id="close-btn" onclick="closeSidebar()">✕</button>
  <h2 id="sb-title">Node</h2>
  <p id="sb-path"></p>
  <div id="sb-content"></div>
</div>
<script>
const PORT = {port};
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
let nodes = [], edges = [], dragging = null, dragOffX = 0, dragOffY = 0;
let pan = {{x: 0, y: 0}}, zoom = 1, isPanning = false, lastMouse = null;
let frameReq = null, graphData = null;

const TYPE_COLORS = {{
  domain: '#7c3aed', file: '#10b981', route: '#06b6d4', table: '#f59e0b', event: '#f43f5e'
}};
const GLOW = {{ domain: '#9f67ff', file: '#34d399', route: '#22d3ee', table: '#fbbf24', event: '#fb7185' }};

function resize() {{
  canvas.width = window.innerWidth; canvas.height = window.innerHeight;
  if (frameReq) cancelAnimationFrame(frameReq); frameReq = requestAnimationFrame(draw);
}}
window.addEventListener('resize', resize);

async function fetchData() {{
  const [graphRes, contextRes] = await Promise.all([
    fetch(`http://127.0.0.1:${{PORT}}/pug/graph`),
    fetch(`http://127.0.0.1:${{PORT}}/pug/context?format=json`)
  ]);
  graphData = await graphRes.json();
  const ctx2 = await contextRes.json();
  buildGraph(graphData, ctx2);
  document.getElementById('loading').style.display = 'none';
  document.getElementById('stats').textContent = `${{nodes.length}} nodes · ${{edges.length}} edges · auto-refreshes every 5s`;
  resize();
}}

function buildGraph(data, ctx2) {{
  const nodeMap = {{}};
  const cx = window.innerWidth / 2, cy = window.innerHeight / 2;
  const entityIndex = ctx2.entities || {{}};

  // Collect domain nodes
  const domains = Object.keys(entityIndex.domains || {{}});
  domains.forEach((d, i) => {{
    const angle = (2 * Math.PI * i) / (domains.length || 1);
    const r = Math.min(cx, cy) * 0.4;
    const id = 'domain:' + d;
    nodeMap[id] = {{id, label: d, type: 'domain', x: cx + Math.cos(angle)*r, y: cy + Math.sin(angle)*r,
      vx:0, vy:0, radius: 18, data: {{files: (entityIndex.domains[d]||[])}} }};
  }});

  // File nodes
  (data.nodes || []).forEach((path, i) => {{
    if (!nodeMap['file:'+path]) {{
      const angle = (2 * Math.PI * i) / ((data.nodes.length) || 1);
      const r = Math.min(cx, cy) * 0.7;
      nodeMap['file:'+path] = {{id:'file:'+path, label: path.split('/').pop(), path, type: 'file',
        x: cx + Math.cos(angle)*r + (Math.random()-0.5)*80,
        y: cy + Math.sin(angle)*r + (Math.random()-0.5)*80,
        vx:0, vy:0, radius: 10, data: {{}} }};
    }}
  }});

  nodes = Object.values(nodeMap);

  // Edges from semantic graph
  edges = (data.edges || []).map(e => ({{
    from: 'file:'+e.from, to: 'file:'+e.to, type: e.type, entity: e.entity
  }}));

  // Domain -> file edges
  Object.entries(entityIndex.domains || {{}}).forEach(([d, files]) => {{
    files.forEach(f => {{
      edges.push({{from: 'domain:'+d, to: 'file:'+f, type: 'domain', entity: d}});
    }});
  }});

  runForceLayout(80);
}}

function runForceLayout(ticks) {{
  for (let t = 0; t < ticks; t++) {{
    nodes.forEach(a => {{
      nodes.forEach(b => {{
        if (a === b) return;
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const f = 1800 / (dist * dist);
        a.vx += dx/dist * f; a.vy += dy/dist * f;
      }});
      a.vx *= 0.85; a.vy *= 0.85;
    }});
    edges.forEach(e => {{
      const a = nodes.find(n => n.id === e.from), b = nodes.find(n => n.id === e.to);
      if (!a || !b) return;
      const dx = b.x-a.x, dy = b.y-a.y;
      const dist = Math.sqrt(dx*dx+dy*dy)||1;
      const ideal = e.type === 'domain' ? 140 : 90;
      const f = (dist - ideal) * 0.05;
      a.vx += dx/dist*f; a.vy += dy/dist*f;
      b.vx -= dx/dist*f; b.vy -= dy/dist*f;
    }});
    nodes.forEach(n => {{ n.x += n.vx; n.y += n.vy; }});
  }}
}}

function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Draw edges
  edges.forEach(e => {{
    const a = nodes.find(n => n.id === e.from), b = nodes.find(n => n.id === e.to);
    if (!a || !b) return;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = (TYPE_COLORS[e.type] || '#334155') + '55';
    ctx.lineWidth = 1;
    ctx.stroke();
  }});

  // Draw nodes
  nodes.forEach(n => {{
    const col = TYPE_COLORS[n.type] || '#334155';
    const glow = GLOW[n.type] || col;

    ctx.save();
    ctx.shadowColor = glow;
    ctx.shadowBlur = n.type === 'domain' ? 20 : 10;
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI*2);
    ctx.fillStyle = col;
    ctx.fill();
    ctx.restore();

    if (zoom > 0.5) {{
      ctx.font = `${{Math.min(11, 9/zoom)}}px system-ui`;
      ctx.fillStyle = '#c5c6c7';
      ctx.textAlign = 'center';
      ctx.fillText(n.label.length > 18 ? n.label.slice(0,16)+'…' : n.label,
        n.x, n.y + n.radius + 12);
    }}
  }});

  ctx.restore();
  frameReq = requestAnimationFrame(draw);
}}

function screenToWorld(sx, sy) {{
  return {{ x: (sx - pan.x) / zoom, y: (sy - pan.y) / zoom }};
}}

canvas.addEventListener('mousedown', e => {{
  const w = screenToWorld(e.clientX, e.clientY);
  const hit = nodes.find(n => Math.hypot(n.x - w.x, n.y - w.y) < n.radius + 4);
  if (hit) {{
    dragging = hit; dragOffX = hit.x - w.x; dragOffY = hit.y - w.y;
    openSidebar(hit);
  }} else {{
    isPanning = true; lastMouse = {{x: e.clientX, y: e.clientY}};
  }}
}});
canvas.addEventListener('mousemove', e => {{
  if (dragging) {{
    const w = screenToWorld(e.clientX, e.clientY);
    dragging.x = w.x + dragOffX; dragging.y = w.y + dragOffY;
  }} else if (isPanning && lastMouse) {{
    pan.x += e.clientX - lastMouse.x; pan.y += e.clientY - lastMouse.y;
    lastMouse = {{x: e.clientX, y: e.clientY}};
  }}
}});
canvas.addEventListener('mouseup', () => {{ dragging = null; isPanning = false; }});
canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.91;
  const cx = e.clientX, cy = e.clientY;
  pan.x = cx + (pan.x - cx) * factor; pan.y = cy + (pan.y - cy) * factor;
  zoom = Math.max(0.15, Math.min(5, zoom * factor));
}}, {{passive: false}});

function openSidebar(n) {{
  document.getElementById('sb-title').textContent = n.label;
  document.getElementById('sb-path').textContent = n.path || n.id;
  const content = document.getElementById('sb-content');
  const conn = edges.filter(e => e.from === n.id || e.to === n.id);
  content.innerHTML = conn.length
    ? `<h3>Connections (${{conn.length}})</h3><ul>${{conn.map(e =>
        `<li>${{e.entity}} <span style="color:#45a29e">(${{e.type}})</span></li>`).join('')}}</ul>`
    : '<p>No connections detected.</p>';
  document.getElementById('sidebar').classList.add('open');
}}
function closeSidebar() {{ document.getElementById('sidebar').classList.remove('open'); }}

// Auto-refresh every 5 seconds
setInterval(async () => {{
  try {{
    const r = await fetch(`http://127.0.0.1:${{PORT}}/pug/graph`);
    const d = await r.json();
    if (d.nodes.length !== nodes.filter(n=>n.type==='file').length) {{
      const r2 = await fetch(`http://127.0.0.1:${{PORT}}/pug/context?format=json`);
      buildGraph(d, await r2.json());
    }}
  }} catch(_) {{}}
}}, 5000);

fetchData();
resize();
</script>
</body>
</html>"""


def create_app(service: PugService) -> FastAPI:
    app = FastAPI(title="PUG", description="Local semantic knowledge graph server")

    @app.get("/pug/status")
    def status():
        return {
            "configured": service.config.is_configured,
            "project": str(service.config.project_path) if service.config.project_path else None,
            "sniffing": service.sniffing,
            "last_synced": service.last_synced,
            "last_error": getattr(service, "last_error", None),
            "last_reconciliation": service.last_reconciliation,
            "file_count": service.storage.file_count(),
            "brain_provider": service.config.get("brain_provider"),
            "brain_available": service.provider.available,
        }

    @app.get("/pug/context")
    def context(format: str = "markdown", domain: str = "", file: str = "", query: str = ""):
        if not service.config.is_configured:
            msg = "PUG is not configured yet. Please select a project folder in the menu bar."
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
            # Filter by query: match tables/routes/events/domains with keyword
            if query:
                query_lower = query.lower()
                q_files: set[str] = set()
                for cat in ("tables", "routes", "events", "domains"):
                    for entity, paths in index.get(cat, {}).items():
                        if query_lower in entity.lower():
                            q_files.update(paths)
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
            all_f = service.storage.all_files()
            filtered = [f for f in all_f if f["path"] in (filtered_files or set())]
            lines = [
                "# PUG — Filtered Codebase Context",
                f"*Filter: domain=`{domain or '*'}` file=`{file or '*'}` query=`{query or '*'}` | {len(filtered)} files*",
                "",
            ]
            for entry in filtered[:40]:
                lines.append(f"### `{entry['path']}`")
                if entry.get("summary"):
                    lines.append(f"*{entry['summary']}*")
                if entry.get("tables"):
                    lines.append("**Tables:** " + ", ".join(f"`{t}`" for t in entry["tables"]))
                if entry.get("routes"):
                    lines.append("**Routes:** " + ", ".join(f"`{r}`" for r in entry["routes"]))
                if entry.get("events"):
                    lines.append("**Events:** " + ", ".join(f"`{e}`" for e in entry["events"]))
                if entry.get("domains"):
                    lines.append("**Domains:** " + ", ".join(entry["domains"]))
                lines.append("")
            return Response(content="\n".join(lines), media_type="text/markdown; charset=utf-8")

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

    @app.get("/pug/graph/ui", response_class=Response)
    def graph_ui():
        port = service.config.get("server_port", 3000)
        html = _build_live_graph_html(port)
        return Response(content=html, media_type="text/html; charset=utf-8")

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
