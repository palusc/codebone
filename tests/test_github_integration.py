"""Tests for GitHub Repository Connection and Cloning in CodeBone."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases import AddGitHubRepositoryUseCase
from src.config import Config
from src.github import parse_github_identifier
from src.server import create_app
from src.service import CodeBoneService


def test_parse_github_identifier():
    # Various valid URL styles
    assert parse_github_identifier("palusc/codebone") == (
        "palusc",
        "codebone",
        "https://github.com/palusc/codebone.git",
    )
    assert parse_github_identifier("https://github.com/palusc/codebone") == (
        "palusc",
        "codebone",
        "https://github.com/palusc/codebone.git",
    )
    assert parse_github_identifier("https://github.com/palusc/codebone.git") == (
        "palusc",
        "codebone",
        "https://github.com/palusc/codebone.git",
    )
    assert parse_github_identifier("git@github.com:palusc/codebone.git") == (
        "palusc",
        "codebone",
        "https://github.com/palusc/codebone.git",
    )
    assert parse_github_identifier("github.com/palusc/codebone") == (
        "palusc",
        "codebone",
        "https://github.com/palusc/codebone.git",
    )

    # Invalid input
    with pytest.raises(ValueError):
        parse_github_identifier("just_a_random_string_without_slash")


def test_add_github_repo_use_case(tmp_path):
    cfg = Config()
    service = CodeBoneService(cfg)
    fake_cloned_dir = tmp_path / "cloned_repo"
    fake_cloned_dir.mkdir()

    use_case = AddGitHubRepositoryUseCase(service)
    with patch("src.github.clone_github_repo", return_value=fake_cloned_dir) as mock_clone, \
         patch.object(service, "activate_project") as mock_activate:
        res = use_case.execute("palusc/codebone")
        assert res == fake_cloned_dir
        mock_clone.assert_called_once_with("palusc/codebone", target_dir=None, branch=None)
        mock_activate.assert_called_once_with(fake_cloned_dir)
        assert fake_cloned_dir in cfg.project_paths


def test_server_add_github_endpoint(tmp_path):
    cfg = Config()
    service = CodeBoneService(cfg)
    app = create_app(service)
    client = TestClient(app, base_url="http://127.0.0.1:8053")

    # 1. Missing repo param
    resp = client.post("/codebone/projects/add_github", json={})
    assert resp.status_code == 400

    # 2. Valid repo param with mock clone
    fake_cloned_dir = tmp_path / "cloned_test_repo"
    fake_cloned_dir.mkdir()

    with patch("src.github.clone_github_repo", return_value=fake_cloned_dir), \
         patch.object(service, "activate_project"):
        resp = client.post(
            "/codebone/projects/add_github",
            json={"repo": "https://github.com/palusc/codebone"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["project_name"] == fake_cloned_dir.name
        assert data["project_path"] == str(fake_cloned_dir)
