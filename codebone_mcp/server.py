"""Model Context Protocol (MCP) server for codebone.

Exposes the live codebase map (cb / codebone_context), file links (codebone_graph) and status to any
MCP-compatible client. Connects to the local codebone service on localhost. Tool descriptions are kept short
on purpose: they are sent to the model in every session.
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
    """When the configured port is dead (the app restarted on another one), look for a live codebone on 8053-8061."""
    for p in range(8053, 8062):
        candidate_base = f"http://127.0.0.1:{p}"
        if candidate_base == initial_base:
            continue
        try:
            if httpx.get(f"{candidate_base}/codebone/status", timeout=0.25).status_code == 200:
                return candidate_base
        except Exception:
            continue
    return None


def _request(method: str, path: str, params: dict | None = None, payload: dict | None = None) -> str:
    base = ""
    try:
        base, headers = _connection()
        call = httpx.get if method == "GET" else httpx.post
        kwargs = {"headers": headers, "timeout": 10 if method == "GET" else 60}
        kwargs.update({"params": params or {}} if method == "GET" else {"json": payload or {}})
        try:
            resp = call(f"{base}{path}", **kwargs)
        except httpx.ConnectError:
            # An explicit CODEBONE_PORT is a deliberate choice: never silently talk to a different instance
            alt_base = None if os.environ.get("CODEBONE_PORT") else _probe_live_base(base)
            if not alt_base:
                raise
            base = alt_base
            resp = call(f"{base}{path}", **kwargs)
        if resp.status_code == 404 and path.startswith("/codebone/"):
            resp = call(f"{base}{path.replace('/codebone/', '/pug/', 1)}", **kwargs)  # older app versions
        resp.raise_for_status()
    except CodeBoneNotRunning as exc:
        return f"codebone is not reachable: {exc}"
    except httpx.ConnectError:
        return f"codebone is configured but not answering on {base}: make sure the codebone menu bar app is running."
    except httpx.TimeoutException:
        return "codebone did not answer in time (it may be busy scanning); try again in a moment."
    except httpx.HTTPStatusError as exc:
        return f"codebone returned an error: {exc.response.status_code} {exc.response.text[:300]}"
    except httpx.HTTPError as exc:
        return f"codebone request failed: {exc}"

    if "json" in resp.headers.get("content-type", ""):
        return json.dumps(resp.json(), separators=(",", ":"))  # compact: every space costs tokens
    return resp.text


def _get(path: str, params: dict | None = None) -> str:
    return _request("GET", path, params=params)


def _post(path: str, payload: dict) -> str:
    return _request("POST", path, payload=payload)


@mcp.tool()
def cb(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Codebase map from codebone; use it before reading files. No arguments: layout, domains, entities and a
    one-line summary per file. Drill down with query="billing invoice" (several words), file="auth" or
    domain="Payment"; format="json" for structured output."""
    params: dict = {"format": format}
    params.update({k: v for k, v in (("domain", domain), ("file", file), ("query", query)) if v})
    return _get("/codebone/context", params)


@mcp.tool()
def codebone_context(format: str = "markdown", domain: str = "", file: str = "", query: str = "") -> str:
    """Same as cb."""
    return cb(format=format, domain=domain, file=file, query=query)


@mcp.tool()
def codebone_graph(file: str = "") -> str:
    """Files linked through shared tables, routes or events, plus file imports and fetch->API calls.
    With file="x": the links of that file; without: the most connected files."""
    return _get("/codebone/links", {"file": file} if file else None)


@mcp.tool()
def codebone_status() -> str:
    """codebone health: active project, files indexed, scan state, active brain."""
    return _get("/codebone/status")


@mcp.tool()
def codebone_list_scans() -> str:
    """Saved scan snapshots (id, project, file count, domains)."""
    return _get("/codebone/scans")


@mcp.tool()
def codebone_adopt_scan(scan_id_or_path: str, project_path: str | None = None) -> str:
    """Reuse an existing scan for a renamed, moved or branched project folder (matched by SHA-256, only changed
    files are re-analysed)."""
    payload = {"scan_id": scan_id_or_path}
    if project_path:
        payload["project_path"] = project_path
    return _post("/codebone/scans/adopt", payload)


@mcp.prompt("cb")
@mcp.prompt("codebone")
def codebone_prompt() -> str:
    """Use codebone's live codebase map."""
    return (
        "codebone is available. Call cb() first for the project map, then drill down with "
        'cb(query="...") / cb(file="...") / cb(domain="...") and codebone_graph(file="...") '
        "instead of reading many files."
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
