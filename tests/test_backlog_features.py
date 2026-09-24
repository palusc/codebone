"""Unit test suite for codebone Product Backlog Issues #1 - #5."""
import json
import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.battery import on_battery_power
from src.config import (
    GLOBAL_IGNORED_DIRS,
    IGNORED_FILENAMES,
    IGNORED_EXTENSIONS,
    find_free_port,
    is_watched_file,
    load_gitignore_spec,
    Config,
)
from src.server import create_app, patch_mcp_configs
from src.service import CodeBoneService
from src.storage import Storage
from src.watcher import DEBOUNCE_SECONDS, DEBOUNCE_SECONDS_ON_BATTERY


def test_issue_1_dynamic_port_probe_and_mcp_patch(monkeypatch):
    """Issue #1: Verify port finding increments on busy port and auto-patches MCP configs."""
    # Find free port starting at 8053
    free_p = find_free_port(8053)
    assert free_p >= 8053

    # Simulate port collision by binding a test socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", free_p))

    try:
        next_port = find_free_port(free_p)
        assert next_port > free_p, "Port finder must increment when start_port is blocked"
    finally:
        sock.close()

    # Global client configs are patched in place; nothing is ever written into project folders
    from src import server
    monkeypatch.delenv("CODEBONE_NO_MCP_PATCH")
    monkeypatch.setattr(server, "register_claude_cli", lambda python_cmd: None)
    home = Path(os.environ["HOME"])
    (home / ".cursor").mkdir()
    (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {
        "other": {"command": "x"},
        "codebone": {"command": "old", "env": {"CODEBONE_PORT": "9999", "KEEP": "1"}},
    }}))
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        patch_mcp_configs(port=next_port, project_path=tmp_path)

        data = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["other"] == {"command": "x"}
        entry = data["mcpServers"]["codebone"]
        assert entry["args"] == ["-m", "codebone_mcp.server"]
        assert entry["env"] == {"KEEP": "1"}, "stale pinned port must go, unrelated env must stay"
        assert not (home / ".gemini").exists(), "clients that are not installed are not touched"
        for d in (".cursor", ".gemini", ".agents"):
            assert not (tmp_path / d).exists(), "no config files inside project folders"


def test_issue_2_smart_ignoring():
    """Issue #2: Verify strict exclusions for node_modules, build artifacts, lockfiles, .env, and gitignore."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj = Path(tmp_dir)

        # Create sample files
        normal_py = proj / "main.py"
        normal_py.write_text("print('hello')")

        env_file = proj / ".env"
        env_file.write_text("SECRET=123")
        env_prod = proj / ".env.production"
        env_prod.write_text("SECRET=456")

        lockfile = proj / "package-lock.json"
        lockfile.write_text("{}")
        pnpm_lock = proj / "pnpm-lock.yaml"
        pnpm_lock.write_text("")

        media_png = proj / "logo.png"
        media_png.write_bytes(b"\x89PNG\r\n\x1a\n")

        node_mod = proj / "node_modules" / "express" / "index.js"
        node_mod.parent.mkdir(parents=True)
        node_mod.write_text("module.exports = {}")

        next_cache = proj / ".next" / "server" / "page.js"
        next_cache.parent.mkdir(parents=True)
        next_cache.write_text("export default function() {}")

        git_file = proj / ".git" / "HEAD"
        git_file.parent.mkdir(parents=True)
        git_file.write_text("ref: refs/heads/main")

        # Create .gitignore ignoring secret_folder
        gi = proj / ".gitignore"
        gi.write_text("secret_folder/\n*.tmp.py\n")
        gi_spec = load_gitignore_spec(proj)

        secret_file = proj / "secret_folder" / "keys.py"
        secret_file.parent.mkdir(parents=True)
        secret_file.write_text("API_KEY = 'secret'")

        tmp_py = proj / "scratch.tmp.py"
        tmp_py.write_text("# scratch")

        # Tests: codebone maps every real project file now (lockfiles, images, node_modules, ...);
        # only secrets (.env, credential-shaped names), .git internals and .gitignore rules stay excluded.
        assert is_watched_file(normal_py, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(env_file, project_path=proj, gitignore_spec=gi_spec) is False
        assert is_watched_file(env_prod, project_path=proj, gitignore_spec=gi_spec) is False
        assert is_watched_file(lockfile, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(pnpm_lock, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(media_png, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(node_mod, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(next_cache, project_path=proj, gitignore_spec=gi_spec) is True
        assert is_watched_file(git_file, project_path=proj, gitignore_spec=gi_spec) is False
        assert is_watched_file(secret_file, project_path=proj, gitignore_spec=gi_spec) is False
        assert is_watched_file(tmp_py, project_path=proj, gitignore_spec=gi_spec) is False


def test_issue_3_lod_slicing_and_parameterless_overview():
    """Issue #3: Parameterless call returns high-level architecture only; targeted parameters drill down."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_file = Path(tmp_dir) / "config.json"
        db_file = Path(tmp_dir) / "test.sqlite3"
        cfg = Config(cfg_file)
        cfg.data["project_path"] = tmp_dir
        cfg.data["db_path"] = str(db_file)
        cfg.save()

        service = CodeBoneService(cfg)
        service.storage = Storage(db_file)

        # Seed storage with billing domain and auth domain
        service.storage.update_file(
            "billing/stripe.py",
            "TABLES: Invoice, Subscription\nROUTES: POST /checkout\nEVENTS: PaymentSucceeded\nDOMAINS: Billing & Payments\nFLOW: Handles Stripe payments.",
        )
        service.storage.update_file(
            "auth/login.py",
            "TABLES: User, Session\nROUTES: POST /login\nEVENTS: UserLoggedIn\nDOMAINS: Authentication\nFLOW: User authentication.",
        )

        app = create_app(service)
        client = TestClient(app, base_url="http://127.0.0.1")

        # 1. Parameterless call: High-level overview only
        resp_overview = client.get("/codebone/context")
        assert resp_overview.status_code == 200
        text = resp_overview.text
        assert text.startswith("# codebone:")
        assert "2 files" in text
        assert "Billing & Payments" in text
        assert "Authentication" in text
        assert "Invoice" in text and "POST /checkout" in text
        # The overview is a map: every file with its one-line summary
        assert "billing/stripe.py: Handles Stripe payments." in text
        assert "Drill down:" in text

        # 2. Targeted drill-down by domain="billing"
        resp_drill = client.get("/codebone/context?domain=billing")
        assert resp_drill.status_code == 200
        drill_text = resp_drill.text
        assert drill_text.startswith("# codebone:") and 'domain="billing"' in drill_text
        assert "Billing & Payments" in drill_text
        assert "Invoice" in drill_text
        assert "POST /checkout" in drill_text
        assert "Handles Stripe payments." in drill_text
        # Does not include unrelated auth domain
        assert "POST /login" not in drill_text


def test_issue_4_battery_aware_throttling_intervals():
    """Issue #4: Verify debounce interval constants (0.5s AC, 15.0s battery)."""
    assert DEBOUNCE_SECONDS == 0.5
    assert DEBOUNCE_SECONDS_ON_BATTERY == 15.0

    # Test on_battery_power returns a boolean without throwing
    val = on_battery_power()
    assert isinstance(val, bool)


def test_issue_5_syntax_error_resilience():
    """Issue #5: Transient syntax errors in broken files do not crash or corrupt previous SQLite record."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cfg_file = tmp_path / "config.json"
        db_file = tmp_path / "test.sqlite3"
        cfg = Config(cfg_file)
        cfg.data["project_path"] = str(tmp_path)
        cfg.data["db_path"] = str(db_file)
        cfg.save()

        service = CodeBoneService(cfg)
        service.storage = Storage(db_file)

        # Step 1: Valid initial Python file
        py_file = tmp_path / "worker.py"
        py_file.write_text("class JobWorker:\n    def process(self):\n        pass\n")

        service._sniff_file(py_file, force=True, live=True)
        hashes_before = service.storage.get_file_hashes()
        assert "worker.py" in hashes_before

        # Step 2: Broken code with unclosed bracket (syntax error during typing)
        py_file.write_text("class JobWorker:\n    def process(self: unclosed_bracket(")

        # Step 3: Sniff broken file — must NOT throw, must quietly preserve previous state
        service._sniff_file(py_file, force=True, live=True)

        files = service.storage.all_files()
        assert len(files) == 1
        assert files[0]["path"] == "worker.py"
        # Database preserved previous valid hash and record
        assert files[0]["content_hash"] == hashes_before["worker.py"]
 
 
def test_issue_6_initial_days_and_status_mcp_metadata():
    """Verify is_first_days initializes first_run_at, expires after 7 days, and status includes MCP metadata."""
    import time
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cfg_file = tmp_path / "config.json"
        cfg = Config(cfg_file)
        
        # Initially None
        assert cfg.data.get("first_run_at") is None
        # is_first_days sets it to now and returns True
        assert cfg.is_first_days(days=7) is True
        assert cfg.data.get("first_run_at") is not None

        # Simulate 8 days in the future
        cfg.data["first_run_at"] = time.time() - (8 * 86400)
        assert cfg.is_first_days(days=7) is False

        # Create service & test status endpoint response
        db_file = tmp_path / "test.sqlite3"
        cfg.data["project_path"] = str(tmp_path)
        cfg.data["first_run_at"] = time.time()  # reset to today
        cfg.save()
        service = CodeBoneService(cfg)
        service.storage = Storage(db_file)
        app = create_app(service)
        client = TestClient(app, base_url="http://127.0.0.1")

        resp = client.get("/codebone/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_first_days" in data
        assert data["is_first_days"] is True
        assert "mcp_guide_url" in data
        assert "mcp-setup" in data["mcp_guide_url"]

