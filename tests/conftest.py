"""Every test runs against a throw-away home: no test may read or write the developer's real codebone data,
MCP client configs or Claude Code registration."""
import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEBONE_NO_MCP_PATCH", "1")

    from src import config, feedback, logging_setup

    cfg_dir = home / "Library" / "Application Support" / "codebone"
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "config.json")
    monkeypatch.setattr(config, "DB_FILE", cfg_dir / "codebone.sqlite3")
    monkeypatch.setattr(config, "SCANS_DIR", cfg_dir / "scans")
    monkeypatch.setattr(config, "MODELS_DIR", cfg_dir / "models")
    monkeypatch.setattr(feedback, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(feedback, "FEEDBACK_FILE", cfg_dir / "feedback.jsonl")
    monkeypatch.setattr(logging_setup, "LOG_DIR", home / "Library" / "Logs" / "codebone")
    monkeypatch.setattr(logging_setup, "LOG_FILE", home / "Library" / "Logs" / "codebone" / "codebone.log")
    yield home
