"""Persistent codebone configuration (project path, brain provider, server port)."""
from __future__ import annotations
import json
import copy
import logging
import os
import stat
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("codebone.config")

CONFIG_DIR = Path.home() / "Library" / "Application Support" / "codebone"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "codebone.sqlite3"
SCANS_DIR = CONFIG_DIR / "scans"
MODELS_DIR = CONFIG_DIR / "models"

BASE_MODEL_NAME = "Built-in (Qwen 0.5B)"
BASE_MODEL_FILE = "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
BASE_MODEL_PATH = str(MODELS_DIR / BASE_MODEL_FILE)
# Pinned to an exact HF revision + checksum so every install path (DMG, install.sh, brew, in-app fetch) gets the same bytes.
BASE_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/resolve/"
    "ebb2015119c907b064c512bf053e945850b5875f/" + BASE_MODEL_FILE
)
BASE_MODEL_SHA256 = "1d9614638d18024d0fbb36575a15f1302a3adf044df10345688ec4f6e1c4ff32"

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
    ".gitignore",
    ".npmignore",
    ".dockerignore",
}

# Strict hardcoded directories to always ignore
OWN_DIRS = {".pug", ".codebone"}
# Dependency, VCS and build-output trees: vendored or regenerated, never project content. Pruned from the walk
# itself — an 800-file repo with node_modules and .git otherwise scans as 150k+ files (read, hashed, some even
# sent to the brain), which is what made a scan slow and the Mac hot.
PRUNED_DIRS = OWN_DIRS | {
    "node_modules", ".git", ".svn", ".hg", "vendor",
    "__pycache__", ".venv", "venv", ".tox", ".nox",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".dmypy_cache",
    "dist", "build", "out", "target", "coverage", "htmlcov",
    ".next", ".nuxt", ".output", ".svelte-kit", ".turbo", ".cache", ".parcel-cache",
    "Pods", "DerivedData", ".gradle", ".dart_tool",
    ".eggs",
}
# Credential stores: mapped like everything else, but nothing below these is ever read (service._sniff_file)
GLOBAL_IGNORED_DIRS = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".secrets",
    "secrets",
}

# Pure OS-generated metadata, never project content (auto-regenerated, carries no code/architecture signal)
IGNORED_FILENAMES = {
    ".DS_Store",
    "Thumbs.db",
}

# Legacy: no longer used to exclude files (every extension is mapped now), kept for callers that still
# import it. See _asset_category in service.py for how these are classified instead of skipped.
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

# Files above this size are generated/minified/data dumps, not architecture; reading them costs RAM and time.
MAX_READ_BYTES = 32_000_000

# Credentials never leave the disk: a cloud brain would otherwise receive them as "source code".
_SECRET_NAMES = {".npmrc", ".netrc", ".pypirc", ".htpasswd", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx"}
_SECRET_STEMS = ("credential", "secret")  # secrets.py, credentials.json, secret_key.txt ...
_SECRET_WORDS = ("secret", "credential", "token", "password", "passwd", "apikey", "api_key", "api-key",
                 "private_key", "private-key", "privatekey", "service-account", "service_account", "serviceaccount",
                 "firebase-adminsdk", "client_secret", "deploy_key", "deploy-key")
_DATA_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".txt", ".xml", ".cfg", ".conf", ".properties", ".plist"}


def _is_secret_or_junk(name: str) -> bool:
    low = name.lower()
    if low == ".env" or low.startswith(".env.") or low.endswith(".env"):
        return True
    if name in _SECRET_NAMES or name.startswith("id_rsa") or name.startswith("id_ed25519"):
        return True
    if low.startswith("._") or low.endswith((".min.js", ".min.css", ".map")):
        return True
    dot = low.rfind(".")
    stem, suffix = (low[:dot], low[dot:]) if dot > 0 else (low, "")
    if suffix in _SECRET_SUFFIXES:
        return True
    if suffix in _DATA_SUFFIXES:  # data files: any secret-looking word anywhere in the name (auth.json, token.json ...)
        return any(w in stem for w in _SECRET_WORDS) or stem == "auth"
    return stem.startswith(_SECRET_STEMS)  # code files: secrets.py, credentials.js


def load_gitignore_spec(project_path: Optional[Path]) -> Optional[object]:
    """.gitignore is deliberately NOT applied: the map must cover the whole project, gitignored files included
    (build output, .env-style names are still dropped by the secret and vendor rules). Kept so callers stay unchanged."""
    return None
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


def _relative_parts(path: Path, project_path: Optional[Path]) -> Optional[tuple]:
    """Path parts relative to the project root (None if outside it). Ignore rules must only look at these:
    matching absolute parts made a project living under e.g. ~/build/ index nothing."""
    if not project_path:
        return path.parts
    try:
        return path.relative_to(project_path).parts
    except ValueError:
        return None


def is_watched_file(
    path: Path,
    extensions: Optional[set[str]] = None,
    ignore_dirs: Optional[set[str]] = None,
    gitignore_spec: Optional[object] = None,
    project_path: Optional[Path] = None,
    check_exists: bool = True,
) -> bool:
    """True if the path belongs in the project map. Every real project file counts — source, config,
    docs, images, lockfiles, compiled output — so codebone builds a complete picture of what
    is actually on disk, secrets and all: a credential-shaped file is a node too, its content just never
    gets read (Service._path_only). A file too large or binary to analyse as code still gets a node in the
    map, catalogued instead of sniffed (see _asset_category / Service._catalog_asset). Dependency, VCS and
    build trees (node_modules, .git, dist, ...) are the one exception: pruned, see PRUNED_DIRS.

    Cheap name/extension/ignore checks run first; the filesystem is only touched at the end. With
    check_exists=False (used for deletion events) the file does not have to exist any more."""
    # Everything is mapped: no extension list, no .gitignore. The only exclusions are the app's own data folder
    # (indexing the index would loop) and dependency/VCS/build trees (PRUNED_DIRS — vendored, not project content).
    # Secret, binary and huge files become path-only nodes, see service.
    rel = _relative_parts(path, project_path)
    if rel is None or any(d in PRUNED_DIRS for d in rel[:-1]):
        return False

    if not check_exists:
        return True
    try:
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            # Symlink jail: a link may not lead outside the project folder. A link to a secret file
            # is still a node — its content is never read, see service._sniff_file.
            target = path.resolve()
            if project_path and not target.is_relative_to(project_path.resolve()):
                return False
            return target.is_file()
        return stat.S_ISREG(st.st_mode)
    except (OSError, ValueError):
        return False


def list_watched_files(
    project_path: Path,
    extensions: Optional[set[str]] = None,
    ignore_dirs: Optional[set[str]] = None,
    gitignore_spec: Optional[object] = None,
    unreadable_dirs: Optional[list] = None,
) -> list[Path]:
    """All indexable files below project_path. Ignored directories are pruned instead of walked (a node_modules
    tree used to be traversed and stat'ed file by file). Raises OSError if the root itself cannot be listed, so
    callers can tell "empty project" from "folder unreadable" and never wipe an index because of the latter.

    A subdirectory that can't be listed (permissions, a broken mount) is skipped by os.walk without raising —
    by default that failure is completely silent, and files under it just vanish from the count with no sign
    anything went wrong. Pass unreadable_dirs to collect those paths instead of losing them quietly."""
    root = Path(project_path)
    os.listdir(root)
    found: list[Path] = []

    def _onerror(exc: OSError):
        path = getattr(exc, "filename", None) or str(exc)
        logger.warning("Skipping unreadable directory while scanning %s: %s (%s)", root, path, exc)
        if unreadable_dirs is not None:
            unreadable_dirs.append(path)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_onerror):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIRS]
        for f in filenames:
            p = Path(dirpath, f)
            if is_watched_file(p, extensions, ignore_dirs, gitignore_spec, root):
                found.append(p)
    return found


def is_pruned_rel(rel: str) -> bool:
    """True when a project-relative path sits in a pruned tree (node_modules, .git, ...). Rows under one are
    stale index entries to drop, not files that went missing."""
    return any(part in PRUNED_DIRS for part in Path(rel).parts)


def find_free_port(start_port: int = 8053, max_attempts: int = 50) -> int:
    """First TCP port from start_port that nothing listens on and we can bind on 127.0.0.1."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                continue  # somebody (possibly bound to a wildcard address) already listens
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
    "ignore_dirs": [],
    "watched_extensions": DEFAULT_WATCHED_EXTENSIONS,
    "brain_provider": "builtin",  # "builtin" | "local_url" | "cloud"
    "brain_local_url": "http://localhost:11434/api/generate",
    "brain_cloud_vendor": "openai",  # "openai" | "anthropic" | "openrouter"
    "brain_cloud_api_key": "",
    "brain_cloud_model": "gpt-6",
    "deep_scan_model_path": None,
    "recent_projects": [],
    "first_run_at": None,
    "modules": [],
    "module_selected": None,
    "module_apps": {},
    "module_backups": {},
    "modules_enabled": False,
    "modules_paused_apps": [],
}


class Config:
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = Path(config_file) if config_file else CONFIG_FILE
        self.config_dir = self.config_file.parent
        self.data = copy.deepcopy(DEFAULTS)
        self._lock = threading.RLock()
        if self.config_file.exists():
            self.load()
        else:
            self.save()

    def load(self):
        with self._lock:
            if not self.config_file.exists():
                return
            try:
                stored = json.loads(self.config_file.read_text(encoding="utf-8"))
                if not isinstance(stored, dict):
                    raise ValueError("config root is not an object")
            except (ValueError, OSError) as exc:
                # Keep the unreadable file (it may hold an API key or the project path) instead of overwriting it
                backup = self.config_file.with_name(f"{self.config_file.name}.corrupt-{int(time.time())}")
                try:
                    os.replace(self.config_file, backup)
                    logger.warning("Unreadable config moved to %s (%s); starting from defaults", backup, exc)
                except OSError:
                    pass
                return
            self.data.update(stored)
            # Ensure all modern default extensions are included
            cur_exts = set(self.data.get("watched_extensions", []))
            cur_exts.update(DEFAULT_WATCHED_EXTENSIONS)
            self.data["watched_extensions"] = sorted(cur_exts)
            migrated = False
            # Migrate legacy default ports 3000/3077 to modern 8053
            if self.data.get("server_port") in (3000, 3077):
                self.data["server_port"] = 8053
                migrated = True
            if self.data.get("brain_cloud_model") in ("gpt-6-luna", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"):
                self.data["brain_cloud_model"] = "gpt-6"
                migrated = True
            if migrated:
                self.save()

    def save(self):
        """Atomic, durable write (fsync + rename) readable only by the owner: the file can hold a cloud API key."""
        with self._lock:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self.config_file.with_suffix(".json.tmp")
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.config_file)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
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
        if not p:
            return None
        try:
            # Resolved once: FSEvents reports real paths, so a project opened through a symlink or alias must be
            # compared in its real location or it would get no live updates.
            return Path(p).expanduser().resolve()
        except OSError:
            return Path(p)

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
        """Directory names that are never indexed. .gitignore rules are applied separately through
        load_gitignore_spec. Nothing is excluded any more — saved ignore lists from older versions are
        ignored too — except codebone's own data folder, which would otherwise index its own index."""
        return {".codebone", ".pug"}
