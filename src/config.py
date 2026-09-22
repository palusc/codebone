"""Persistent PUG configuration (project path, brain provider, server port)."""
import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / "Library" / "Application Support" / "PUG"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "pug.sqlite3"
MODELS_DIR = CONFIG_DIR / "models"

BASE_MODEL_NAME = "Built-in (Qwen 0.8B)"
BASE_MODEL_PATH = str(MODELS_DIR / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf")

DEFAULTS = {
    "project_path": None,
    "server_port": 3000,
    "known_models": [{"name": BASE_MODEL_NAME, "path": BASE_MODEL_PATH}],
    "model_path": BASE_MODEL_PATH,
    "ignore_dirs": [
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pug",
        ".next",
        ".turbo",
    ],
    "watched_extensions": [
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".c",
        ".cpp",
        ".h",
        ".sql",
        ".graphql",
    ],
    "brain_provider": "builtin",  # "builtin" | "local_url" | "cloud"
    "brain_local_url": "http://localhost:11434/api/generate",
    "brain_cloud_vendor": "openai",  # "openai" | "anthropic"
    "brain_cloud_api_key": "",
    "brain_cloud_model": "gpt-4o-mini",
}


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        if CONFIG_FILE.exists():
            self.load()
        else:
            self.save()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        """Atomic write so a crash mid-save cannot corrupt config.json."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = CONFIG_FILE.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp_path, CONFIG_FILE)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        self.save()

    @property
    def project_path(self) -> Optional[Path]:
        p = self.data.get("project_path")
        return Path(p) if p else None

    @property
    def is_configured(self) -> bool:
        p = self.project_path
        return bool(p and p.exists())

    @property
    def db_path(self) -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return DB_FILE

    @property
    def known_models(self) -> list[dict]:
        return self.data.get("known_models", [])

    def add_model(self, path: str, name: Optional[str] = None) -> dict:
        """Register an additional GGUF selected by the user."""
        name = name or Path(path).stem
        for m in self.known_models:
            if m["path"] == path:
                return m
        entry = {"name": name, "path": path}
        self.data.setdefault("known_models", [])
        self.data["known_models"].append(entry)
        self.save()
        return entry

    def select_model(self, path: str):
        self.data["model_path"] = path
        self.save()
