"""Persistent codebone configuration (project path, brain provider, server port)."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / "Library" / "Application Support" / "codebone"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "codebone.sqlite3"
SCANS_DIR = CONFIG_DIR / "scans"
MODELS_DIR = CONFIG_DIR / "models"

BASE_MODEL_NAME = "Built-in (Qwen 0.5B)"
BASE_MODEL_PATH = str(MODELS_DIR / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf")

DEFAULT_WATCHED_EXTENSIONS = [
    # Python & Shell
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    # JavaScript, TypeScript & Web
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".astro",
    # Systems & Backend
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".rb",
    ".php",
    ".swift",
    ".cs",
    ".dart",
    ".lua",
    ".zig",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    # Data, Config & Schemas
    ".sql",
    ".graphql",
    ".gql",
    ".prisma",
    ".proto",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".ini",
    # Documentation & Text
    ".md",
    ".markdown",
    ".txt",
]

EXACT_WATCHED_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Procfile",
    "Jenkinsfile",
    "Containerfile",
    "LICENSE",
}

# Strict hardcoded directories to always ignore
GLOBAL_IGNORED_DIRS = {
    "node_modules",
    ".next",
    "dist",
    "build",
    "venv",
    ".venv",
    ".git",
    ".turbo",
    ".cache",
    ".pytest_cache",
    "target",
    ".idea",
    ".vscode",
    "coverage",
    ".mypy_cache",
    ".codebone",
    ".pug",
    "__pycache__",
    ".parcel-cache",
    ".nuxt",
    ".output",
}

# Strict lockfiles and OS metadata to always ignore
IGNORED_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "poetry.lock",
    "composer.lock",
    "Gemfile.lock",
    "bun.lockb",
    ".DS_Store",
    "Thumbs.db",
}

# Non-code, binary, media, models, compiled bytecodes, and database files
IGNORED_EXTENSIONS = {
    # Images & icons
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".svg", ".webp", ".bmp", ".tiff", ".psd",
    # Audio & video
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".flac", ".ogg", ".aac",
    # Archives & packages
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".iso", ".dmg",
    # Local models & tensors
    ".gguf", ".bin", ".safetensors", ".onnx", ".pt", ".pth", ".pkl", ".h5", ".tflite",
    # Databases & stores
    ".sqlite", ".sqlite3", ".db", ".mdb", ".accdb",
    # Compiled objects & bytecodes
    ".pyc", ".pyo", ".pyd", ".class", ".o", ".obj", ".dylib", ".so", ".dll", ".exe", ".wasm",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Document formats
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

try:
    import pathspec
    _HAS_PATHSPEC = True
except ImportError:
    _HAS_PATHSPEC = False


def load_gitignore_spec(project_path: Optional[Path]) -> Optional[object]:
    """Compiles a pathspec GitIgnoreSpec from project's .gitignore if available."""
    if not project_path or not _HAS_PATHSPEC:
        return None
    gi = Path(project_path) / ".gitignore"
    if not gi.is_file():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except Exception:
        return None


def is_watched_file(
    path: Path,
    extensions: Optional[set[str]] = None,
    ignore_dirs: Optional[set[str]] = None,
    gitignore_spec: Optional[object] = None,
    project_path: Optional[Path] = None,
) -> bool:
    """Returns True if the path is a valid code, script, config, or doc file to scan."""
    if not path.is_file():
        return False

    name = path.name
    # 0. Symlink Jail / Sandboxing: prevent symlinks pointing outside the project folder
    if project_path:
        try:
            resolved_file = path.resolve()
            resolved_proj = project_path.resolve()
            if not resolved_file.is_relative_to(resolved_proj):
                return False
        except (ValueError, OSError):
            return False

    # 1. Environment secret files
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return False

    # 2. Strict lockfiles & OS files
    if name in IGNORED_FILENAMES:
        return False

    # 3. Binary, media, models & compiled files
    suffix = path.suffix.lower()
    if suffix in IGNORED_EXTENSIONS:
        return False

    # 4. Global hardcoded exclusion directories
    parts = set(path.parts)
    if any(d in GLOBAL_IGNORED_DIRS for d in parts):
        return False

    # 5. User / dynamic ignore directories
    if ignore_dirs and any(part in ignore_dirs for part in parts):
        return False

    # 6. Gitignore pathspec matching
    if gitignore_spec and project_path:
        try:
            rel = str(path.relative_to(project_path))
            if gitignore_spec.match_file(rel):
                return False
        except (ValueError, Exception):
            pass

    # 7. Exact watched filenames (Dockerfile, Makefile, etc.)
    if name in EXACT_WATCHED_FILENAMES:
        return True

    exts = extensions if extensions is not None else set(DEFAULT_WATCHED_EXTENSIONS)
    return suffix in exts


def find_free_port(start_port: int = 8053, max_attempts: int = 50) -> int:
    """Finds the first available TCP port starting at start_port by testing socket binding."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


DEFAULTS = {
    "project_path": None,
    "server_port": 8053,
    "known_models": [{"name": BASE_MODEL_NAME, "path": BASE_MODEL_PATH}],
    "model_path": BASE_MODEL_PATH,
    "ignore_dirs": list(GLOBAL_IGNORED_DIRS),
    "watched_extensions": DEFAULT_WATCHED_EXTENSIONS,
    "brain_provider": "builtin",  # "builtin" | "local_url" | "cloud"
    "brain_local_url": "http://localhost:11434/api/generate",
    "brain_cloud_vendor": "openai",  # "openai" | "anthropic"
    "brain_cloud_api_key": "",
    "brain_cloud_model": "gpt-6",
    "deep_scan_model_path": None,
    "recent_projects": [],
    "first_run_at": None,
}


class Config:
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = Path(config_file) if config_file else CONFIG_FILE
        self.config_dir = self.config_file.parent
        self.data = dict(DEFAULTS)
        if self.config_file.exists():
            self.load()
        else:
            self.save()

    def load(self):
        if self.config_file.exists():
            try:
                stored = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.data.update(stored)
                # Ensure all modern default extensions are included
                cur_exts = set(self.data.get("watched_extensions", []))
                for ext in DEFAULT_WATCHED_EXTENSIONS:
                    cur_exts.add(ext)
                self.data["watched_extensions"] = sorted(list(cur_exts))
                # Migrate legacy default ports 3000/3077 to modern 8053
                if self.data.get("server_port") in (3000, 3077):
                    self.data["server_port"] = 8053
                    self.save()
                if self.data.get("brain_cloud_model") in ("gpt-6-luna", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"):
                    self.data["brain_cloud_model"] = "gpt-6"
                    self.save()
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        """Atomic write so a crash mid-save cannot corrupt config.json."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_file.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.config_file)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        self.save()

    def is_first_days(self, days: int = 7) -> bool:
        """Returns True if the app was first run within the specified number of days."""
        first_run = self.data.get("first_run_at")
        now = time.time()
        if first_run is None:
            self.data["first_run_at"] = now
            self.save()
            return True
        try:
            return (now - float(first_run)) < (days * 86400)
        except (ValueError, TypeError):
            return True


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
        self.config_dir.mkdir(parents=True, exist_ok=True)
        primary = self.config_dir / "codebone.sqlite3"
        legacy = self.config_dir / "pug.sqlite3"
        if not primary.exists() and legacy.exists():
            try:
                legacy.replace(primary)
            except Exception:
                return legacy
        return primary

    @property
    def scans_dir(self) -> Path:
        p = self.config_dir / "scans"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def known_models(self) -> list[dict]:
        return self.data.get("known_models", [])

    @property
    def active_model_display_name(self) -> str:
        provider = self.data.get("brain_provider", "builtin")
        if provider == "builtin":
            cur_path = self.data.get("model_path", BASE_MODEL_PATH)
            for m in self.known_models:
                if m.get("path") == cur_path:
                    return m.get("name", "Built-in (Qwen 0.5B)")
            if cur_path:
                return Path(cur_path).stem
            return BASE_MODEL_NAME
        elif provider == "local_url":
            url = self.data.get("brain_local_url", "")
            return f"Local URL ({url.split('://')[-1].split('/')[0]})" if url else "Local URL (Ollama)"
        elif provider == "cloud":
            vendor = self.data.get("brain_cloud_vendor", "openai")
            model = self.data.get("brain_cloud_model", "gpt-6")
            return f"Cloud ({vendor.title()} {model})"
        return "Unknown"

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

    @property
    def recent_projects(self) -> list[str]:
        return self.data.get("recent_projects", [])

    def add_recent_project(self, project_path: str):
        """Adds a project path to the MRU recent projects list (max 10)."""
        try:
            resolved = str(Path(project_path).resolve())
        except Exception:
            resolved = str(project_path)
        recents = [p for p in self.data.get("recent_projects", []) if p != resolved]
        recents.insert(0, resolved)
        self.data["recent_projects"] = recents[:10]
        self.save()

    def remove_recent_project(self, project_path: str):
        """Removes a project path from the recent projects list."""
        try:
            resolved = str(Path(project_path).resolve())
        except Exception:
            resolved = str(project_path)
        recents = [p for p in self.data.get("recent_projects", []) if p != resolved]
        self.data["recent_projects"] = recents
        self.save()

    def clear_recent_projects(self):
        """Clears all recent projects."""
        self.data["recent_projects"] = []
        self.save()

    def get_ignore_dirs(self, project_path: Optional[Path] = None) -> set[str]:
        """Returns comprehensive set of ignored directories, including project .gitignore entries."""
        base_ignores = set(self.data.get("ignore_dirs", []))
        # Ensure standard dependencies, caches, and build targets are always protected
        base_ignores.update({
            ".git", "node_modules", ".venv", "venv", "__pycache__", "build",
            "dist", ".codebone", ".pug", ".next", ".turbo", "target", ".cache", ".idea",
            ".vscode", "coverage", ".pytest_cache", ".mypy_cache"
        })
        proj = project_path or self.project_path
        if proj and proj.exists():
            gitignore = proj / ".gitignore"
            if gitignore.is_file():
                try:
                    for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            clean = line.strip("/").rstrip("/*")
                            if clean and not clean.startswith("*"):
                                base_ignores.add(clean)
                except Exception:
                    pass
        return base_ignores
