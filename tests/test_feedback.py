"""Tests for codebone built-in feedback and bug reporting."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.feedback import (
    _sanitize_log_line,
    build_system_diagnostics,
    generate_github_issue_url,
    get_recent_log_snippet,
    list_recent_feedback,
    record_feedback,
)
from src.server import create_app
from src.service import CodeBoneService
from src.config import Config


def test_sanitize_log_line():
    """Verify sensitive tokens and keys are redacted from logs."""
    raw_log = "Error connecting with openai: sk-proj-1234567890abcdef1234567890 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6"
    sanitized = _sanitize_log_line(raw_log)
    assert "sk-proj-1234567890" not in sanitized
    assert "sk-***REDACTED***" in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6" not in sanitized
    assert "bearer ***redacted***" in sanitized.lower()

    key_log = 'Config: api_key="supersecretkey12345678"'
    sanitized_key = _sanitize_log_line(key_log)
    assert "supersecretkey12345678" not in sanitized_key
    assert "***REDACTED***" in sanitized_key


def test_build_system_diagnostics():
    """Verify system diagnostics are collected accurately."""
    diag = build_system_diagnostics({"extra_k": "extra_v"})
    assert "app_version" in diag
    assert "os" in diag
    assert "architecture" in diag
    assert "python_version" in diag
    assert diag["extra_k"] == "extra_v"


def test_generate_github_issue_url():
    """Verify pre-filled GitHub issue URL contains Markdown-formatted body and title."""
    diag = {"app_version": "1.2.0", "os": "macOS 15.0", "architecture": "arm64", "python_version": "3.14.0"}
    url = generate_github_issue_url(
        feedback_type="bug",
        title="Watcher crashed on deep symlink",
        description="Steps to reproduce:\n1. Create recursive symlink\n2. Watcher loops",
        diagnostics=diag,
        log_snippet="[ERROR] loop detected",
    )
    assert url.startswith("https://github.com/palusc/codebone/issues/new?")
    assert "title=%5BBug%5D+Watcher+crashed+on+deep+symlink" in url
    assert "loop+detected" in url
    assert "System+Diagnostics" in url


def test_record_feedback_local_storage():
    """Verify feedback is recorded to feedback.jsonl and can be listed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_feedback_file = Path(tmp_dir) / "feedback.jsonl"
        with patch("src.feedback.FEEDBACK_FILE", tmp_feedback_file), \
             patch("src.feedback.CONFIG_DIR", Path(tmp_dir)):
            
            res1 = record_feedback(
                feedback_type="bug",
                title="UI canvas glitch",
                description="Nodes flicker when zoomed out past 2x.",
                include_logs=False,
            )
            assert res1["status"] == "success"
            assert "id" in res1
            assert "github_url" in res1

            res2 = record_feedback(
                feedback_type="feature",
                title="Neo4j export",
                description="Please add graph export to Cypher format.",
                include_logs=False,
            )
            assert res2["status"] == "success"

            assert tmp_feedback_file.exists()
            lines = tmp_feedback_file.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 2

            entry1 = json.loads(lines[0])
            assert entry1["type"] == "bug"
            assert entry1["title"] == "UI canvas glitch"

            # Check list_recent_feedback (newest first)
            recent = list_recent_feedback(limit=5)
            assert len(recent) == 2
            assert recent[0]["title"] == "Neo4j export"
            assert recent[1]["title"] == "UI canvas glitch"


def test_feedback_api_endpoints():
    """Verify POST and GET /codebone/feedback endpoints."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg = Config()
        cfg.config_file = Path(tmp_dir) / "config.json"
        service = CodeBoneService(cfg)
        app = create_app(service)
        client = TestClient(app)

        tmp_feedback_file = Path(tmp_dir) / "feedback.jsonl"
        with patch("src.feedback.FEEDBACK_FILE", tmp_feedback_file), \
             patch("src.feedback.CONFIG_DIR", Path(tmp_dir)):

            post_resp = client.post(
                "/codebone/feedback",
                json={
                    "type": "bug",
                    "title": "Port collision warning",
                    "description": "Port 8053 was taken by another app, switched to 8054 nicely.",
                    "include_logs": False,
                },
            )
            assert post_resp.status_code == 200
            data = post_resp.json()
            assert data["status"] == "success"
            assert "github_url" in data
            assert "project" in data["diagnostics"]

            # Check GET endpoint
            get_resp = client.get("/codebone/feedback")
            assert get_resp.status_code == 200
            items = get_resp.json()["feedback"]
            assert len(items) == 1
            assert items[0]["title"] == "Port collision warning"

            # Check legacy endpoint alias
            legacy_resp = client.get("/pug/feedback")
            assert legacy_resp.status_code == 200
            assert len(legacy_resp.json()["feedback"]) == 1
