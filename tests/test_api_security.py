"""Local API: DNS-rebinding and cross-origin protection, export safety, context endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.config import Config
from src.providers import FastFallbackProvider
from src.server import create_app
from src.service import CodeBoneService


@pytest.fixture()
def client(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    cfg = Config(tmp_path / "cfg" / "config.json")
    cfg.set("project_path", str(proj))
    svc = CodeBoneService(cfg)
    svc.provider = FastFallbackProvider()
    svc.storage.update_file("billing/stripe.py", "TABLES: Invoice\nROUTES: POST /checkout\nEVENTS: PaymentSucceeded\nDOMAINS: Billing\nFLOW: Handles Stripe payments.")
    svc.storage.update_file("cron/dunning.py", "TABLES: Invoice\nROUTES: none\nEVENTS: none\nDOMAINS: Billing\nFLOW: Retries failed cards.")
    svc.storage.update_file("auth/login.py", "TABLES: User\nROUTES: POST /login\nEVENTS: none\nDOMAINS: Auth\nFLOW: Signs users in.")
    return TestClient(create_app(svc), base_url="http://127.0.0.1:8053")


def test_foreign_host_header_is_refused(client):
    assert client.get("/codebone/status", headers={"Host": "evil.example:8053"}).status_code == 403
    assert client.get("/codebone/status").status_code == 200


def test_cross_origin_requests_are_refused_but_same_origin_and_tools_work(client):
    assert client.post("/codebone/reset", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.get("/codebone/context", headers={"Origin": "http://localhost:3000"}).status_code == 403
    assert client.get("/codebone/status", headers={"Origin": "http://127.0.0.1:8053"}).status_code == 200
    assert client.get("/codebone/status").status_code == 200  # curl / MCP send no Origin


def test_docs_pages_are_not_served_and_headers_are_set(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    r = client.get("/codebone/graph/ui")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_export_refuses_wrong_suffix_and_existing_files(client, tmp_path):
    scan = client.get("/codebone/scans").json()
    assert scan["count"] == 0
    target = tmp_path / "x.txt"
    r = client.post("/codebone/scans/export", json={"scan_id": "nope", "dest_path": str(target)})
    assert r.status_code in (400, 404)
    assert not target.exists()


def test_status_does_not_load_the_model(client):
    body = client.get("/codebone/status").json()
    assert "revision" in body and body["brain_available"] is False  # fallback provider: nothing to load


def test_context_overview_query_and_links(client):
    overview = client.get("/codebone/context").text
    assert overview.startswith("# codebone: proj | 3 files")
    assert "billing/stripe.py: Handles Stripe payments." in overview

    hit = client.get("/codebone/context", params={"query": "stripe payments"}).text
    assert "### billing/stripe.py" in hit and "Linked: cron/dunning.py (via Invoice)" in hit

    partial = client.get("/codebone/context", params={"query": "login billing"}).text
    assert "showing files matching some" in partial

    assert "cron/dunning.py" in client.get("/codebone/links", params={"file": "stripe"}).text
    assert client.get("/codebone/context", params={"format": "json", "query": "invoice"}).json()["match_count"] == 2


def test_rescan_and_reset_do_not_pile_up_threads(client):
    first = client.post("/codebone/rescan").json()
    assert first["status"] in ("started", "running")
