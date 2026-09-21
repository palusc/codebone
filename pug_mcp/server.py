"""Model Context Protocol (MCP) server for PUG.

Exposes `pug_status`, `pug_context`, and `pug_graph` as native tools to any
MCP-compatible client (Claude, Cursor, etc.). Connects directly to the
local PUG service on localhost.
"""
import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

CONFIG_FILE = Path.home() / "Library" / "Application Support" / "PUG" / "config.json"

mcp = FastMCP("pug")


class PugNotRunning(Exception):
    pass


def _connection() -> tuple[str, dict]:
    if not CONFIG_FILE.exists():
        raise PugNotRunning("PUG has never been launched — open the PUG menu bar app first.")
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise PugNotRunning(f"PUG config is unreadable: {exc}") from exc

    port = data.get("server_port", 3000)
    base = f"http://127.0.0.1:{port}"
    return base, {}


def _get(path: str, params: dict | None = None) -> str:
    try:
        base, headers = _connection()
        resp = httpx.get(f"{base}{path}", headers=headers, params=params or {}, timeout=10)
        resp.raise_for_status()
    except PugNotRunning as exc:
        return f"PUG is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "PUG is configured but its server isn't answering on "
            f"{base}{path} — make sure the PUG menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"PUG returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


def _post(path: str, payload: dict) -> str:
    try:
        base, headers = _connection()
        resp = httpx.post(f"{base}{path}", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
    except PugNotRunning as exc:
        return f"PUG is not reachable: {exc}"
    except httpx.ConnectError:
        return (
            "PUG is configured but its server isn't answering on "
            f"{base}{path} — make sure the PUG menu bar app is running."
        )
    except httpx.HTTPStatusError as exc:
        return f"PUG returned an error: {exc.response.status_code} {exc.response.text}"

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        return json.dumps(resp.json(), indent=2)
    return resp.text


@mcp.tool()
def pug_status() -> str:
    """Get PUG's current status: the configured project directory path, sniffing state
    (idle vs actively sniffing), total files indexed, and which brain provider is active.
    Use this to verify PUG's health or check which project is currently active."""
    return _get("/pug/status")


@mcp.tool()
def pug_context(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Retrieve the live codebase architecture, overarching business domains,
    database models/tables, API routes, events, and the Semantic System Graph tracked by PUG.
    ALWAYS call this tool first whenever the user mentions 'PUG', 'pug', asks about
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
    return _get("/pug/context", params)


@mcp.tool()
def pug_graph() -> str:
    """Get the Semantic System Graph derived by PUG from shared business domains,
    database tables, API routes, and events. Reveals how files and components are logically
    intertwined across the overarching system architecture, even when no direct code imports exist."""
    return _get("/pug/graph")


@mcp.tool()
def pug_list_scans() -> str:
    """List all saved or historical codebase scans and snapshots tracked by PUG.
    Returns scan identifiers, project names, file counts, and detected business domains."""
    return _get("/pug/scans")


@mcp.tool()
def pug_adopt_scan(scan_id_or_path: str, project_path: str | None = None) -> str:
    """Adopt and reconcile an existing codebase scan for a project folder (e.g. after
    renaming, moving, or branching the folder). Re-links matching files instantly by SHA-256
    hash with zero LLM overhead, sniffs modified files, and uses the AI to reconcile overarching
    business domains and the Semantic System Graph."""
    payload = {"scan_id": scan_id_or_path}
    if project_path:
        payload["project_path"] = project_path
    return _post("/pug/scans/adopt", payload)


@mcp.prompt("pug")
def pug_prompt() -> str:
    """Prompt for building or understanding code using PUG's live codebase map."""
    return (
        "You have access to PUG (sniffed live codebase knowledge graph). "
        "First, call pug_context() to inspect the architecture, database models, and API routes of the active project. "
        "Then use that context to plan and execute the user's request accurately."
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
