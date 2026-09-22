"""Model Context Protocol (MCP) server for CodeBone.

Exposes `codebone_status`, `codebone_context`, and `codebone_graph` as native tools to any
MCP-compatible client (Claude, Cursor, etc.). Connects directly to the
local CodeBone service on localhost.
"""
import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

CONFIG_FILE = Path.home() / "Library" / "Application Support" / "CodeBone" / "config.json"

mcp = FastMCP("codebone")


class CodeBoneNotRunning(Exception):
    pass


def _connection() -> tuple[str, dict]:
    if not CONFIG_FILE.exists():
        raise CodeBoneNotRunning("CodeBone has never been launched — open the CodeBone menu bar app first.")
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise CodeBoneNotRunning(f"CodeBone config is unreadable: {exc}") from exc

    port = data.get("server_port", 3000)
    base = f"http://127.0.0.1:{port}"
    return base, {}


def _get(path: str, params: dict | None = None) -> str:
    try:
        base, headers = _connection()
        resp = httpx.get(f"{base}{path}", headers=headers, params=params or {}, timeout=10)
        if resp.status_code == 404 and path.startswith("/codebone/"):
            legacy_path = path.replace("/codebone/", "/pug/", 1)
            resp = httpx.get(f"{base}{legacy_path}", headers=headers, params=params or {}, timeout=10)
        resp.raise_for_status()
    except CodeBoneNotRunning as exc:
        return f"CodeBone is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "CodeBone is configured but its server isn't answering on "
            f"{base}{path} — make sure the CodeBone menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"CodeBone returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


def _post(path: str, payload: dict) -> str:
    try:
        base, headers = _connection()
        resp = httpx.post(f"{base}{path}", headers=headers, json=payload, timeout=60)
        if resp.status_code == 404 and path.startswith("/codebone/"):
            legacy_path = path.replace("/codebone/", "/pug/", 1)
            resp = httpx.post(f"{base}{legacy_path}", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
    except CodeBoneNotRunning as exc:
        return f"CodeBone is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "CodeBone is configured but its server isn't answering on "
            f"{base}{path} — make sure the CodeBone menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"CodeBone returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


@mcp.tool()
def codebone_status() -> str:
    """Get CodeBone's current status: the configured project directory path, sniffing state
    (idle vs actively sniffing), total files indexed, and which brain provider is active.
    Use this to verify CodeBone's health or check which project is currently active."""
    return _get("/codebone/status")


@mcp.tool()
def codebone_context(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Retrieve the live codebase architecture, overarching business domains,
    database models/tables, API routes, events, and the Semantic System Graph tracked by CodeBone.
    ALWAYS call this tool first whenever the user mentions 'CodeBone', asks about
    project architecture, or asks you to build, implement, understand, or refactor code
    in the project, so you have full architectural context without reading all files manually.
    `format` is 'markdown' (default, human-readable) or 'json' (structured).
    Use `domain`, `file`, or `query` parameters for Level-of-Detail filtering on large codebases:
    e.g. domain='billing' returns only files in the Billing domain, reducing token usage further."""
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
    """Get the Semantic System Graph derived by CodeBone from shared business domains,
    database tables, API routes, and events. Reveals how files and components are logically
    intertwined across the overarching system architecture, even when no direct code imports exist."""
    return _get("/codebone/graph")


@mcp.tool()
def codebone_list_scans() -> str:
    """List all saved or historical codebase scans and snapshots tracked by CodeBone.
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


@mcp.prompt("codebone")
def codebone_prompt() -> str:
    """Prompt for building or understanding code using CodeBone's live codebase map."""
    return (
        "You have access to CodeBone (sniffed live codebase knowledge graph). "
        "First, call codebone_context() to inspect the architecture, database models, and API routes of the active project. "
        "Then use that context to plan and execute the user's request accurately."
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
