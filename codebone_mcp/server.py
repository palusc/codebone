"""Model Context Protocol (MCP) server for codebone.

Exposes `codebone_status`, `codebone_context`, and `codebone_graph` as native tools to any
MCP-compatible client (Claude, Cursor, etc.). Connects directly to the
local codebone service on localhost.
"""
import json
import os
from pathlib import Path
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

CONFIG_FILE = Path.home() / "Library" / "Application Support" / "codebone" / "config.json"
LEGACY_CONFIG_FILE = Path.home() / "Library" / "Application Support" / "CodeBone" / "config.json"

mcp = FastMCP("codebone")


class CodeBoneNotRunning(Exception):
    pass


def _connection() -> tuple[str, dict]:
    # 1. Environment variable override
    env_port = os.environ.get("CODEBONE_PORT")
    if env_port:
        try:
            return f"http://127.0.0.1:{int(env_port)}", {}
        except ValueError:
            pass

    # 2. Config file
    cfg = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_CONFIG_FILE
    if not cfg.exists():
        raise CodeBoneNotRunning("codebone has never been launched — open the codebone menu bar app first.")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodeBoneNotRunning(f"codebone config is unreadable: {exc}") from exc

    port = data.get("active_port") or data.get("server_port", 8053)
    base = f"http://127.0.0.1:{port}"
    return base, {}


def _probe_live_base(initial_base: str) -> Optional[str]:
    """Fallback probe across dynamic ports (8053-8061) if initial connection fails."""
    candidates = [8053, 8054, 8055, 8056, 8057, 8058, 8059, 8060, 8061]
    for p in candidates:
        candidate_base = f"http://127.0.0.1:{p}"
        if candidate_base == initial_base:
            continue
        try:
            r = httpx.get(f"{candidate_base}/codebone/status", timeout=0.25)
            if r.status_code == 200:
                return candidate_base
        except Exception:
            continue
    return None


def _get(path: str, params: dict | None = None) -> str:
    try:
        base, headers = _connection()
        try:
            resp = httpx.get(f"{base}{path}", headers=headers, params=params or {}, timeout=10)
        except httpx.ConnectError:
            alt_base = _probe_live_base(base)
            if alt_base:
                base = alt_base
                resp = httpx.get(f"{base}{path}", headers=headers, params=params or {}, timeout=10)
            else:
                raise
        if resp.status_code == 404 and path.startswith("/codebone/"):
            legacy_path = path.replace("/codebone/", "/pug/", 1)
            resp = httpx.get(f"{base}{legacy_path}", headers=headers, params=params or {}, timeout=10)
        resp.raise_for_status()
    except CodeBoneNotRunning as exc:
        return f"codebone is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "codebone is configured but its server isn't answering on "
            f"{base}{path} — make sure the codebone menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"codebone returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


def _post(path: str, payload: dict) -> str:
    try:
        base, headers = _connection()
        try:
            resp = httpx.post(f"{base}{path}", headers=headers, json=payload, timeout=60)
        except httpx.ConnectError:
            alt_base = _probe_live_base(base)
            if alt_base:
                base = alt_base
                resp = httpx.post(f"{base}{path}", headers=headers, json=payload, timeout=60)
            else:
                raise
        if resp.status_code == 404 and path.startswith("/codebone/"):
            legacy_path = path.replace("/codebone/", "/pug/", 1)
            resp = httpx.post(f"{base}{legacy_path}", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
    except CodeBoneNotRunning as exc:
        return f"codebone is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "codebone is configured but its server isn't answering on "
            f"{base}{path} — make sure the codebone menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"codebone returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


@mcp.tool()
def codebone_status() -> str:
    """Get codebone's current status: the configured project directory path, sniffing state
    (idle vs actively sniffing), total files indexed, and which brain provider is active.
    Use this to verify codebone's health or check which project is currently active."""
    return _get("/codebone/status")


@mcp.tool()
def cb(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Universal shortcut 'cb' for codebone_context.
    
    Trigger this tool whenever the user types 'cb', 'cb: <task>', 'cb overview', or asks for
    codebase architecture and semantic context.
    
    LEVEL-OF-DETAIL (LOD) PARAMETERS:
    - Calling without parameters (`cb()`) returns the High-Level Architectural Overview and Business Domains.
    - Drill down to conserve tokens:
      - `domain`: e.g. `domain="billing"` to receive models, routes, events, and file summaries for that domain.
      - `file`: e.g. `file="auth.py"` to inspect a specific file or module.
      - `query`: e.g. `query="stripe"` to search matching tables, endpoints, and connections.
    """
    return codebone_context(format=format, domain=domain, file=file, query=query)


@mcp.tool()
def codebone_context(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Retrieve live codebase architecture, overarching business domains, and semantic context.
    
    SHORTCUT: Can also be triggered directly as `cb` or whenever the user writes 'cb' in their prompt.
    
    LEVEL-OF-DETAIL (LOD) USAGE:
    - Calling without parameters (`codebone_context()`) returns a token-efficient High-Level Architectural Overview and Business Domains list.
    - When working on specific components or answering detailed questions, ALWAYS drill down using targeted parameters to conserve tokens:
      - `domain`: e.g. `domain="billing"` to receive database models, routes, events, and file summaries for that business domain.
      - `file`: e.g. `file="auth.py"` to inspect a specific file or module.
      - `query`: e.g. `query="stripe"` to search for matching tables, endpoints, and semantic connections.
    
    `format` defaults to 'markdown' (human-readable) or 'json' (structured)."""
    params: dict = {"format": format}
    if domain:
        params["domain"] = domain
    if file:
        params["file"] = file
    if query:
        params["query"] = query
    return _get("/codebone/context", params)


@mcp.tool()
def codebone_graph() -> str:
    """Get the Semantic System Graph derived by codebone from shared business domains,
    database tables, API routes, and events. Reveals how files and components are logically
    intertwined across the overarching system architecture, even when no direct code imports exist."""
    return _get("/codebone/graph")


@mcp.tool()
def codebone_list_scans() -> str:
    """List all saved or historical codebase scans and snapshots tracked by codebone.
    Returns scan identifiers, project names, file counts, and detected business domains."""
    return _get("/codebone/scans")


@mcp.tool()
def codebone_adopt_scan(scan_id_or_path: str, project_path: str | None = None) -> str:
    """Adopt and reconcile an existing codebase scan for a project folder (e.g. after
    renaming, moving, or branching the folder). Re-links matching files instantly by SHA-256
    hash with zero LLM overhead, sniffs modified files, and uses the AI to reconcile overarching
    business domains and the Semantic System Graph."""
    payload = {"scan_id": scan_id_or_path}
    if project_path:
        payload["project_path"] = project_path
    return _post("/codebone/scans/adopt", payload)


@mcp.prompt("cb")
@mcp.prompt("codebone")
def codebone_prompt() -> str:
    """Universal shortcut prompt 'cb' for understanding code using codebone's live codebase map."""
    return (
        "You have access to codebone (live codebase semantic knowledge graph). "
        "Official shortcut: 'cb'. "
        "1. First, call `cb()` or `codebone_context()` with no parameters to inspect the high-level architecture and overarching business domains. "
        "2. When implementing a feature or exploring a specific domain, execute a targeted sub-query such as "
        "`cb(domain=\"billing\")` or `cb(query=\"stripe\")` to retrieve granular database models, "
        "routes, and file summaries without exceeding context token limits."
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
