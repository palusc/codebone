"""MCP client payload contracts: the adopt server route rejects '/' inside scan_id, so a path
must travel under scan_path or adoption 400s end-to-end."""
from codebone_mcp import server as mcp_server


def test_adopt_scan_routes_paths_under_scan_path(monkeypatch):
    seen = {}
    monkeypatch.setattr(mcp_server, "_post",
                        lambda path, payload: seen.update(path=path, payload=payload) or "ok")
    assert mcp_server.codebone_adopt_scan("askment_8aff831e") == "ok"
    assert seen == {"path": "/codebone/scans/adopt", "payload": {"scan_id": "askment_8aff831e"}}
    mcp_server.codebone_adopt_scan("/tmp/snap.sqlite3", project_path="/tmp/proj")
    assert seen["payload"] == {"scan_path": "/tmp/snap.sqlite3", "project_path": "/tmp/proj"}
    mcp_server.codebone_adopt_scan("~/scans/x.sqlite3")
    assert seen["payload"] == {"scan_path": "~/scans/x.sqlite3"}


def _fake_resp(status, payload):
    class R:
        headers = {"content-type": "application/json"}
        status_code = status

        def json(self):
            return payload

        def raise_for_status(self):
            pass

        @property
        def text(self):
            return str(payload)

    return R()


def test_404_fallback_retries_only_missing_routes(monkeypatch):
    """Handler 404s (adopt: scan not found) are answers — re-POSTing them would run side effects twice."""
    monkeypatch.setattr(mcp_server, "_connection", lambda: ("http://127.0.0.1:8053", {}))

    def handler_404(url, **kw):
        return _fake_resp(404, {"detail": "Source scan 'x' not found"})

    monkeypatch.setattr(mcp_server.httpx, "post", handler_404)
    monkeypatch.setattr(mcp_server.httpx, "get", handler_404)
    out = mcp_server._post("/codebone/scans/adopt", {"scan_path": "/nope.sqlite3"})
    assert "not found" in out  # exactly one POST: no blind retry on a real answer

    hits = []

    def route_missing(url, **kw):
        hits.append(url)
        return _fake_resp(404, {"detail": "Not Found"}) if len(hits) == 1 else _fake_resp(200, {"ok": 1})

    monkeypatch.setattr(mcp_server.httpx, "post", route_missing)
    out = mcp_server._post("/codebone/scans/adopt", {"scan_id": "x"})
    assert len(hits) == 2 and hits[0].endswith("/codebone/scans/adopt") and hits[1].endswith("/pug/scans/adopt")
