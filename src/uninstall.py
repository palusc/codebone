"""Complete removal of codebone from this Mac.

One implementation behind the in-app "Uninstall codebone..." menu item and the terminal fallback
(uninstall.sh, or `python -m src.uninstall`). It removes everything codebone put on the machine: processes,
app bundles, application data, caches, preferences, login items, MCP registrations and package-manager
installs. It never touches your project files. The one exception is the codebone entry that older versions wrote
into a project's .cursor / .gemini / .agents MCP files: only that entry goes, and the report says so. Inside other
programs' configs it only ever deletes codebone's own entries.

Standard library only and Python 3.9 compatible, so the stock macOS python3 can run it as well.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

APP_IDS = ("com.codebone.app", "com.pug.app")  # current bundle id, then the legacy one
APP_NAMES = ("codebone", "CodeBone", "PUG")  # current name first, then legacy names
MCP_NAMES = ("codebone", "pug")  # server names codebone registered itself under
NPM_PACKAGE = "codebone-mcp"
BREW_FORMULA = "codebone"
BREW_TAP = "palusc/codebone"
SYSTEM_APPS = Path("/Applications")
BREW_PREFIXES = (Path("/opt/homebrew"), Path("/usr/local"))
LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
)

# A codebone process either executes out of an app bundle (the app, its bundled Python) or is an interpreter running
# the MCP server, a launcher script or the npm bridge. The executable is checked, not just the command line, so an
# editor that merely has one of these files open (vim codebone_mcp/server.py) is never a target.
_BUNDLE_EXE_RE = re.compile(r"/(?:codebone|CodeBone|PUG)\.app/Contents/")
_INTERPRETER_RE = re.compile(r"^(?:[Pp]ython[\d.]*|node)$")
_SCRIPT_RE = re.compile(
    r"(?:codebone|pug)_mcp[./]server|codebone_main\.py|pug_main\.py|(?:^|[/\s])codebone-mcp(?:\.js)?(?:\s|$)"
)
# Login items are matched by bundle id, so another vendor's com.pug.* agent is never touched.
_AGENT_RE = re.compile(r"^(?:%s)(?:[._-].*)?\.plist$" % "|".join(re.escape(i) for i in APP_IDS))

_LABELS = {
    "data": "Application data",
    "logs": "Logs",
    "cache": "Caches",
    "prefs": "Preferences",
    "state": "Saved state",
    "service": "Login item",
    "app": "Application",
    "mcp": "MCP registration",
    "process": "Running process",
    "package": "Package",
}


@dataclass
class Target:
    """One thing the uninstall removes. `path` is a filesystem path, or a short description for processes."""

    kind: str
    label: str
    path: str
    exists: bool = True
    size_bytes: int = 0


@dataclass
class Report:
    removed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False
    project_files_edited: bool = False  # a legacy codebone entry was taken out of an MCP file in a project folder

    @property
    def nothing_to_remove(self) -> bool:
        return not (self.removed or self.errors)

    def format(self) -> str:
        lines: List[str] = []
        if self.removed:
            lines.append(f"{'Would remove' if self.dry_run else 'Removed'} ({len(self.removed)}):")
            lines += [f"  - {item}" for item in self.removed]
        if self.skipped:
            lines.append("Left in place:")
            lines += [f"  - {item}" for item in self.skipped]
        if self.errors:
            lines.append("Problems:")
            lines += [f"  - {item}" for item in self.errors]
        if self.nothing_to_remove:
            lines.append("Nothing to remove. codebone is not installed on this Mac (or was already removed).")
        elif self.dry_run:
            lines.append("Dry run: nothing was changed.")
        elif self.errors:
            lines.append("codebone was removed except for the problems listed above.")
        elif self.project_files_edited:
            lines.append("codebone has been removed from this Mac. In your project folders only codebone's own "
                         "MCP entries (listed above) were taken out; nothing else there was changed.")
        else:
            lines.append("codebone has been removed from this Mac. Your project folders were not touched.")
        return "\n".join(lines)


@dataclass
class _Cfg:
    """A JSON file that may hold an `mcpServers` object with a codebone entry."""

    label: str
    path: Path
    prune: Tuple[Path, ...] = ()  # directories to remove (in order) if deleting the file leaves them empty
    deletable: bool = True  # delete the file once nothing but our entry was in it
    nested: bool = False  # also look in projects.*.mcpServers (~/.claude.json)
    cli: bool = False  # try `claude mcp remove` before editing the file
    project: bool = False  # lives in an indexed project folder (older versions wrote there)


# ── environment ─────────────────────────────────────────────────────────────


def _home(home) -> Path:
    """The home directory to work in. An empty $HOME is refused (Path.home() would turn it into "/" or the current
    directory, and every path below into a system-wide or project path), and so is any relative or root path."""
    raw = str(home) if home else os.environ.get("HOME", str(_account_home()))
    if not os.path.isabs(raw) or not os.path.normpath(raw).strip("/"):  # "//" is a root too
        raise ValueError(f"refusing to use {raw!r} as the home directory: it must be an absolute path other than "
                         "the filesystem root (is $HOME empty?)")
    return Path(os.path.normpath(raw))


def _account_home() -> Path:
    """The real account home, independent of $HOME (which tests and sandboxes override)."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except KeyError:
        return Path.home()


def _is_system(home: Path, system: Optional[bool]) -> bool:
    """Machine-wide steps (/Applications, running processes, claude/brew/npm, TCC, LaunchServices) only run for the
    real account home. With any other home the uninstall stays inside that directory tree."""
    if system is not None:
        return system
    try:
        return home.resolve() == _account_home().resolve()
    except OSError:
        return False


def _run(cmd: List[str], timeout: float = 30, env: Optional[dict] = None) -> Tuple[int, str]:
    """Run a helper command. Never raises: a missing or hanging tool is just a non-zero result."""
    try:  # stdin is closed so no helper can wait for input (a sudo or keychain prompt) on our terminal
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def _glob(directory: Path, pattern: str) -> List[Path]:
    try:
        return sorted(directory.glob(pattern))
    except OSError:
        return []


def _find_tool(name: str, home: Path) -> Optional[str]:
    """PATH lookup plus the usual install dirs (an app started from Finder has a minimal PATH)."""
    found = shutil.which(name)
    if found:
        return found
    dirs = [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), home / ".local" / "bin", home / ".claude" / "local",
            home / ".npm-global" / "bin", home / ".volta" / "bin"]
    dirs += [p / "bin" for p in _glob(home / ".nvm" / "versions" / "node", "*")]
    for d in dirs:
        cand = d / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def _tilde(path, home: Path) -> str:
    s, h = str(path), str(home)
    return "~" + s[len(h):] if s == h or s.startswith(h + os.sep) else s


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1000:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} GB"


def _size(path: Path) -> int:
    """Bytes below path without following symlinks (venv/src/model links point into the app bundle)."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size
    total, stack = 0, [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _delete(path: Path) -> None:
    """Remove a file, symlink (never its target) or directory tree. A missing path is fine."""
    try:
        if path.is_symlink() or not path.is_dir():
            path.unlink()
            return
        try:
            shutil.rmtree(path)
        except PermissionError:
            os.chmod(path, 0o700)
            for root, dirs, _files in os.walk(path):
                for d in dirs:
                    full = os.path.join(root, d)
                    if not os.path.islink(full):
                        os.chmod(full, 0o700)
            shutil.rmtree(path)
    except FileNotFoundError:
        pass


def _why(exc: BaseException, path: Path) -> str:
    if isinstance(exc, PermissionError):
        return f"permission denied (owned by another user? try: sudo rm -rf {shlex.quote(str(path))})"
    return str(exc)


# ── processes ───────────────────────────────────────────────────────────────


def _ps() -> List[Tuple[int, int, str, str]]:
    """(pid, ppid, executable, command line) of every process of the current user."""
    base = ["ps", "-x", "-ww", "-U", str(os.getuid()), "-o"]
    exes = {}
    for line in _run(base + ["pid=,comm="], timeout=10)[1].splitlines():  # comm may contain spaces: its own call
        pid, _, exe = line.strip().partition(" ")
        if pid.isdigit():
            exes[int(pid)] = exe.strip()
    rows = []
    for line in _run(base + ["pid=,ppid=,command="], timeout=10)[1].splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and int(parts[0]) in exes:
            rows.append((int(parts[0]), int(parts[1]), exes[int(parts[0])], parts[2]))
    return rows


def _is_codebone_process(exe: str, cmd: str) -> bool:
    if _BUNDLE_EXE_RE.search(exe):
        return True
    return bool(_INTERPRETER_RE.match(os.path.basename(exe)) and _SCRIPT_RE.search(cmd))


def _codebone_processes(system: bool) -> List[Tuple[int, str]]:
    """Running codebone processes, never this process or its ancestors (the shell that started us)."""
    if not system:
        return []
    rows = _ps()
    parent = {pid: ppid for pid, ppid, _, _ in rows}
    mine, pid = set(), os.getpid()
    while pid and pid not in mine:
        mine.add(pid)
        pid = parent.get(pid, 0)
    return [(pid, cmd) for pid, _, exe, cmd in rows if pid not in mine and _is_codebone_process(exe, cmd)]


def _kill(pid: int, sig: int) -> None:
    os.kill(pid, sig)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stop(pids: List[int], grace: float = 3.0) -> List[int]:
    """SIGTERM, then SIGKILL for whatever survives the grace period. Returns the pids still running."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        for pid in pids:
            try:
                _kill(pid, sig)
            except OSError:
                pass
        end = time.monotonic() + wait
        while time.monotonic() < end and any(_alive(p) for p in pids):
            time.sleep(0.1)
        pids = [p for p in pids if _alive(p)]
        if not pids:
            break
    return pids


# ── locations ───────────────────────────────────────────────────────────────


def _app_ancestor(path) -> Optional[Path]:
    """Outermost *.app directory containing path."""
    found = None
    for parent in Path(path).parents:
        if parent.suffix == ".app":
            found = parent
    return found


def _looks_like_codebone(app: Path) -> bool:
    if app.name in {f"{n}.app" for n in APP_NAMES}:
        return True
    try:
        with open(app / "Contents" / "Info.plist", "rb") as fh:
            return plistlib.load(fh).get("CFBundleIdentifier") in APP_IDS
    except Exception:  # missing, unreadable or malformed plist
        return False


def _running_bundle() -> Optional[Path]:
    """The .app this code runs from (<app>/Contents/Resources/src/src/uninstall.py), if any."""
    try:
        app = _app_ancestor(Path(__file__).resolve())
    except OSError:
        return None
    return app if app and _looks_like_codebone(app) else None


def _read_only(path: Path) -> bool:
    """True if the volume holding path is mounted read-only (a mounted disk image)."""
    try:
        return bool(os.statvfs(path.parent).f_flag & os.ST_RDONLY)
    except OSError:
        return False


def _hosts_this_process(app: Path) -> bool:
    """True if this very process runs out of the bundle, so deleting it now would pull the code from under us."""
    try:
        base = app.resolve()
        mine = [Path(__file__).resolve()] + ([Path(sys.executable).resolve()] if sys.executable else [])
    except OSError:
        return False
    return any(p == base or base in p.parents for p in mine)


def _linked_bundles(home: Path) -> List[Path]:
    """Bundles the Application Support symlinks (venv, src, models) point into: covers apps kept anywhere."""
    found = []
    for name in APP_NAMES:
        base = home / "Library" / "Application Support" / name
        for link in [base / "venv", base / "src"] + _glob(base / "models", "*.gguf"):
            if link.is_symlink():
                app = _app_ancestor(os.path.realpath(link))
                if app and _looks_like_codebone(app):
                    found.append(app)
    return found


def _dedupe(paths: Iterable[Path]) -> List[Path]:
    """Existing paths only, one per inode (APFS is case-insensitive: CodeBone and codebone are one directory)."""
    seen, out = set(), []
    for p in paths:
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if (st.st_dev, st.st_ino) not in seen:
            seen.add((st.st_dev, st.st_ino))
            out.append(p)
    return out


def _inside(path: Path, folders: List[Path]) -> bool:
    real = Path(os.path.realpath(path))
    for folder in folders:
        base = Path(os.path.realpath(folder))
        if real == base or base in real.parents:
            return True
    return False


def _app_bundles(home: Path, bundle, system: bool,
                 projects: Optional[List[Path]] = None) -> Tuple[List[Path], List[Path]]:
    """(to remove, protected). A bundle that sits inside a project folder (say a dist/ build) is a project file:
    it is only ever removed when the caller names it explicitly."""
    roots = [home / "Applications"] + ([SYSTEM_APPS] if system else [])
    names = ([f"{n}.app" for n in APP_NAMES] + [f"Uninstall {n}.app" for n in APP_NAMES]
             + [f"{APP_NAMES[0]}.app.new", f"{APP_NAMES[0]}.app.old"])  # leftovers of an interrupted update
    fixed = [root / name for root in roots for name in names]
    running = [_running_bundle()] if system and not bundle else []
    found = [p for p in running + _linked_bundles(home) if p]
    if bundle:
        if Path(bundle).suffix != ".app":
            raise ValueError(f"bundle must be a .app directory: {bundle}")
        if not _looks_like_codebone(Path(bundle)):  # a wrong path must never delete somebody else's app
            raise ValueError(f"not a codebone app bundle: {bundle}")
        fixed.append(Path(bundle))
    protected = [p for p in found if _inside(p, projects or []) and p not in fixed]  # standard locations are always ours
    keep = [p for p in found if p not in protected]
    return _dedupe(fixed + keep), _dedupe(protected)


def _launch_agents(home: Path) -> List[Path]:
    return [p for p in _glob(home / "Library" / "LaunchAgents", "*.plist") if _AGENT_RE.match(p.name)]


def _npx_caches(home: Path) -> List[Path]:
    """npx cache entries that exist only to hold codebone-mcp (never one that holds other packages too)."""
    out = []
    for entry in _glob(home / ".npm" / "_npx", "*"):
        try:
            deps = json.loads((entry / "package.json").read_text(encoding="utf-8")).get("dependencies") or {}
        except Exception:  # unreadable, not JSON, too deeply nested, not an object
            continue
        if isinstance(deps, dict) and set(deps) == {NPM_PACKAGE} and (entry / "node_modules" / NPM_PACKAGE).is_dir():
            out.append(entry)
    return out


def _fs_targets(home: Path) -> List[Tuple[str, Path]]:
    """(kind, path) of every existing file or directory that belongs to codebone, except app bundles."""
    lib = home / "Library"
    cands: List[Tuple[str, Path]] = []
    for name in APP_NAMES:
        cands += [("data", lib / "Application Support" / name), ("logs", lib / "Logs" / name)]
    cands.append(("cache", lib / "Caches" / "codebone-build"))
    for app_id in APP_IDS:
        cands += [
            ("cache", lib / "Caches" / app_id),
            ("prefs", lib / "Preferences" / f"{app_id}.plist"),
            ("state", lib / "Saved Application State" / f"{app_id}.savedState"),
            ("state", lib / "HTTPStorages" / app_id),
            ("state", lib / "HTTPStorages" / f"{app_id}.binarycookies"),
            ("state", lib / "WebKit" / app_id),
            ("state", lib / "Containers" / app_id),
        ]
        cands += [("state", p) for p in _glob(lib / "Group Containers", f"*{app_id}")]
    cands += [("cache", p) for p in _npx_caches(home)]
    kept = _dedupe(p for _, p in cands)
    return [(kind, p) for kind, p in cands if p in kept]


def _packages(home: Path, system: bool) -> List[Tuple[str, Path]]:
    """Cheap detection (no subprocess) of Homebrew and global npm installs, for the confirmation list."""
    if not system:
        return []
    found = [("Homebrew formula codebone", p / "Cellar" / BREW_FORMULA) for p in BREW_PREFIXES]
    found += [("Homebrew tap " + BREW_TAP, p / "Library" / "Taps" / "palusc" / "homebrew-codebone")
              for p in BREW_PREFIXES]
    libs = [p / "lib" / "node_modules" for p in BREW_PREFIXES] + [home / ".npm-global" / "lib" / "node_modules"]
    libs += [p / "lib" / "node_modules" for p in _glob(home / ".nvm" / "versions" / "node", "*")]
    found += [("npm package " + NPM_PACKAGE, lib / NPM_PACKAGE) for lib in libs]
    return [(label, p) for label, p in found if os.path.lexists(p)]


def _projects(home: Path) -> List[Path]:
    """Project folders codebone was pointed at (config.json). Only used to clean legacy per-project MCP entries."""
    seen, out = set(), []
    for name in APP_NAMES:
        try:
            data = json.loads((home / "Library" / "Application Support" / name / "config.json").read_text("utf-8"))
        except Exception:  # unreadable, not JSON, or nested deeper than the parser allows
            continue
        if not isinstance(data, dict):
            continue
        recent = data.get("recent_projects")
        raw = (recent if isinstance(recent, list) else []) + [data.get("project_path")]
        for p in raw:
            if isinstance(p, str) and os.path.isabs(p) and p not in seen and os.path.isdir(p):
                seen.add(p)
                out.append(Path(p))
    return out


def _mcp_files(home: Path, projects: List[Path]) -> List[_Cfg]:
    gemini = home / ".gemini"
    cfgs = [
        _Cfg("Claude Code", home / ".claude.json", deletable=False, nested=True, cli=True),
        _Cfg("Claude Desktop", home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"),
        _Cfg("Cursor", home / ".cursor" / "mcp.json", (home / ".cursor",)),
        _Cfg("Gemini", gemini / "config" / "mcp_config.json", (gemini / "config", gemini)),
        _Cfg("Antigravity", gemini / "antigravity-ide" / "mcp_config.json", (gemini / "antigravity-ide", gemini)),
    ]
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if claude_dir and home == _account_home():
        cfgs.append(_Cfg("Claude Code", Path(claude_dir) / ".claude.json", deletable=False, nested=True, cli=True))
    for proj in projects:  # older versions wrote these into the project folder
        for folder, name in ((".cursor", "mcp.json"), (".gemini", "mcp_config.json"), (".agents", "mcp_config.json")):
            cfgs.append(_Cfg(f"project {proj.name}", proj / folder / name, (proj / folder,), project=True))
    seen, out = set(), []
    for cfg in cfgs:  # one entry per real file: a project can be the home directory itself
        key = os.path.realpath(cfg.path)
        if key not in seen:
            seen.add(key)
            out.append(cfg)
    return out


# ── MCP config editing ──────────────────────────────────────────────────────


def _parse(path: Path) -> Tuple[Optional[str], Optional[dict]]:
    """(text, data). text is None when the file cannot be read; data is None unless it is a JSON object."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:  # never rewritten, but still checked for a codebone entry
        return raw.decode("utf-8", "replace"), None
    try:
        data = json.loads(text)
    except Exception:  # invalid JSON, or nested deeper than the parser allows
        return text, None
    return text, data if isinstance(data, dict) else None


def _server_maps(data: dict, nested: bool) -> List[dict]:
    holders = [data]
    if nested and isinstance(data.get("projects"), dict):
        holders += [v for v in data["projects"].values() if isinstance(v, dict)]
    return [h["mcpServers"] for h in holders if isinstance(h.get("mcpServers"), dict)]


def _is_ours(name: str, entry) -> bool:
    """`pug` is also a common name for other tools (the template engine): take it only if it points at this app."""
    return name != "pug" or bool(re.search(r"pug_(?:mcp|main|port)|pug\.app|codebone", json.dumps(entry), re.I))


def _ours(data: dict, nested: bool, pop: bool = False) -> List[str]:
    """Names of codebone's own server entries in data; with pop they are removed from it as well."""
    found = []
    for servers in _server_maps(data, nested):
        for name in MCP_NAMES:
            if name in servers and _is_ours(name, servers[name]):
                found.append(name)
                if pop:
                    del servers[name]
    return found


def _save(path: Path, text: str, data: dict) -> None:
    """Atomic rewrite that keeps the file's indentation, trailing newline, permissions and symlink."""
    m = re.search(r"^([ \t]+)\S", text, re.M)
    out = json.dumps(data, indent=m.group(1) if m else None, ensure_ascii=False)
    if text.endswith("\n"):
        out += "\n"
    target = Path(os.path.realpath(path))
    tmp = target.with_name(target.name + ".codebone-tmp")
    try:
        tmp.write_text(out, encoding="utf-8")
        shutil.copymode(target, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


def _prune(dirs: Tuple[Path, ...], gone: str, dry: bool) -> List[Path]:
    """Remove the directories that became empty (a stray .DS_Store does not count), innermost first."""
    removed, gone_names = [], {gone}
    for d in dirs:
        if os.path.islink(d):  # a dotfiles-managed directory is not ours to remove
            break
        try:
            names = set(os.listdir(d))
        except OSError:
            break
        if names - gone_names - {".DS_Store"}:
            break
        if not dry:
            for name in names - gone_names:
                os.unlink(d / name)
            os.rmdir(d)
        removed.append(d)
        gone_names = {d.name}
    return removed


# ── the run ─────────────────────────────────────────────────────────────────


class _Runner:
    def __init__(self, home: Path, bundle, remove_app: bool, dry_run: bool, system: bool):
        self.home, self.bundle, self.remove_app = home, bundle, remove_app
        self.dry, self.system = dry_run, system
        self.report = Report(dry_run=dry_run)
        # Both are found through files the run itself deletes (config.json, the venv/src symlinks): look first.
        self.projects = _projects(home)
        self.app_paths: List[Path] = []
        self.protected_apps: List[Path] = []

    def t(self, path) -> str:
        return _tilde(path, self.home)

    def run(self) -> Report:
        try:
            self.app_paths, self.protected_apps = _app_bundles(self.home, self.bundle, self.system, self.projects)
        except Exception as exc:  # noqa: BLE001
            self.report.errors.append(f"apps: {exc}")
        steps = (self.services, self.processes, self.mcp, self.packages, self.data, self.apps, self.permissions)
        for step in steps:  # every step stands alone: one failure never stops the rest
            try:
                step()
            except Exception as exc:  # noqa: BLE001
                self.report.errors.append(f"{step.__name__}: {exc}")
        return self.report

    def remove(self, what: str, path: Path) -> bool:
        size = _size(path)
        try:
            if not self.dry:
                _delete(path)
        except Exception as exc:  # noqa: BLE001
            self.report.errors.append(f"{what} {self.t(path)}: {_why(exc, path)}")
            return False
        self.report.removed.append(f"{what}: {self.t(path)}" + (f" ({_fmt_size(size)})" if size else ""))
        return True

    def services(self) -> None:
        uid = str(os.getuid())
        for plist in _launch_agents(self.home):
            if self.system and not self.dry:
                if _run(["launchctl", "bootout", f"gui/{uid}", str(plist)])[0] != 0:
                    _run(["launchctl", "unload", str(plist)])
            self.remove("login item", plist)

    def processes(self) -> None:
        procs = _codebone_processes(self.system)
        for pid, cmd in procs:
            self.report.removed.append(f"process {pid}: {cmd[:100]}")
        if procs and not self.dry:
            for pid in _stop([p for p, _ in procs]):
                self.report.errors.append(f"process {pid} could not be stopped")

    def mcp(self) -> None:
        for cfg in _mcp_files(self.home, self.projects):
            try:
                self.edit_config(cfg)
            except Exception as exc:  # noqa: BLE001
                self.report.errors.append(f"MCP config {self.t(cfg.path)}: {exc}")

    def edit_config(self, cfg: _Cfg) -> None:
        path = cfg.path
        if not os.path.lexists(path):
            return
        text, data = _parse(path)
        if data is None:
            if text is None:
                if path.is_file():  # exists but cannot be opened: we cannot tell whether it holds an entry of ours
                    self.report.skipped.append(f"{self.t(path)} could not be read; check it for a codebone entry")
            elif re.search(r"codebone|\"pug\"", text, re.I):
                self.report.skipped.append(
                    f"{self.t(path)} is not a valid JSON object; remove its codebone entry by hand")
            return
        if cfg.cli and self.system and not self.dry:
            cli = _find_tool("claude", self.home)
            top = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
            for name in [n for n in MCP_NAMES if n in top and _is_ours(n, top[n])] if cli else []:
                if _run([cli, "mcp", "remove", "-s", "user", name], timeout=30)[0] == 0:
                    self.report.removed.append(f"MCP entry '{name}': claude mcp remove -s user")
            text, data = _parse(path)  # the CLI rewrote the file
            if data is None:
                return
        names = _ours(data, cfg.nested, pop=True)
        if not names:
            return
        where = f"{cfg.label} ({self.t(path)})"
        self.report.project_files_edited |= cfg.project
        empty = data in ({}, {"mcpServers": {}})
        if empty and cfg.deletable and not path.is_symlink():
            if not self.dry:
                path.unlink()
            self.report.removed.append(f"MCP config {self.t(path)}: deleted, only codebone was in it")
            for d in _prune(cfg.prune, path.name, self.dry):
                self.report.removed.append(f"empty directory: {self.t(d)}")
            return
        if not self.dry:
            _save(path, text, data)
        self.report.removed.append(f"MCP entry {', '.join(repr(n) for n in dict.fromkeys(names))} in {where}")

    def packages(self) -> None:
        if not self.system:
            return
        brew = _find_tool("brew", self.home)
        if brew:
            env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ENV_HINTS="1")
            if _run([brew, "list", BREW_FORMULA], env=env)[0] == 0:
                self.command([brew, "uninstall", BREW_FORMULA], f"Homebrew formula {BREW_FORMULA}", env, 180)
            if BREW_TAP in _run([brew, "tap"], env=env)[1].split():
                self.command([brew, "untap", BREW_TAP], f"Homebrew tap {BREW_TAP}", env)
        npm = _find_tool("npm", self.home)
        if npm and f"{NPM_PACKAGE}@" in _run([npm, "ls", "-g", "--depth=0", NPM_PACKAGE], timeout=60)[1]:
            self.command([npm, "uninstall", "-g", NPM_PACKAGE], f"npm package {NPM_PACKAGE} (global)", None, 120)

    def command(self, cmd: List[str], what: str, env: Optional[dict], timeout: float = 60) -> None:
        rc, out = (0, "") if self.dry else _run(cmd, timeout=timeout, env=env)
        if rc == 0:
            self.report.removed.append(f"package: {what}")
        else:
            self.report.errors.append(f"{' '.join(cmd)}: {out.strip()[-200:]}")

    def data(self) -> None:
        for kind, path in _fs_targets(self.home):
            if kind == "prefs" and self.system and not self.dry:
                _run(["defaults", "delete", path.name[: -len(".plist")]])  # also drops cfprefsd's cached copy
            self.remove(_LABELS[kind].lower(), path)

    def apps(self) -> None:
        for app in self.protected_apps:
            self.report.skipped.append(f"app: {self.t(app)} (inside one of your project folders)")
        for app in self.app_paths:
            if not self.remove_app:
                self.report.skipped.append(f"app: {self.t(app)} (kept)")
                continue
            try:  # one bundle failing must not keep the others from being removed
                self.remove_bundle(app)
            except Exception as exc:  # noqa: BLE001
                self.report.errors.append(f"app {self.t(app)}: {exc}")

    def remove_bundle(self, app: Path) -> None:
        if _read_only(app):  # run straight from the DMG (or a translocated copy): nothing can be deleted there
            self.report.skipped.append(f"app: {self.t(app)} (read-only location, e.g. a mounted disk image: "
                                       "eject it or move it to the Trash yourself)")
            return
        if self.system and not self.dry and not app.is_symlink() and os.path.exists(LSREGISTER):
            _run([LSREGISTER, "-u", str(app)])
        if not app.is_symlink() and _hosts_this_process(app):
            if not self.dry:
                schedule_bundle_removal(app, os.getpid())
            size = _fmt_size(_size(app))
            self.report.removed.append(f"app: {self.t(app)} ({size}, deleted when this process exits)")
        else:
            self.remove("app", app)

    def permissions(self) -> None:
        """Forget the app's privacy grants (Full Disk Access, Documents, ...). Quiet: it cannot tell if any exist."""
        if self.system and self.remove_app and not self.dry:
            for app_id in APP_IDS:
                _run(["tccutil", "reset", "All", app_id])
            if self.report.removed:
                self.report.removed.append("privacy permissions for " + APP_IDS[0])


# ── public API ──────────────────────────────────────────────────────────────

# Wait for the pid to be gone (a zombie counts as gone), give up after ~10 minutes, then delete.
_REMOVER = (
    'n=0; while s=$(ps -o stat= -p "$1" 2>/dev/null); [ -n "$s" ] && [ "${s#Z}" = "$s" ]; do '
    '[ $n -ge 2000 ] && exit 0; sleep 0.3; n=$((n+1)); done; '
    'sleep 0.5; case "$2" in *.app) rm -rf -- "$2";; esac'
)


def schedule_bundle_removal(bundle_path, pid: int):
    """Delete a .app bundle after process `pid` has exited, from a detached shell that outlives the caller.
    The bundle path is a positional argument, so spaces and quotes in it are safe."""
    return subprocess.Popen(
        ["/bin/sh", "-c", _REMOVER, "codebone-remover", str(pid), os.path.abspath(bundle_path)],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def collect_targets(home=None, bundle=None, *, system: Optional[bool] = None) -> List[Target]:
    """Everything that exists on this machine and would be removed, for the confirmation dialog."""
    home = _home(home)
    system = _is_system(home, system)
    out: List[Target] = []
    for pid, cmd in _codebone_processes(system):
        out.append(Target("process", f"{_LABELS['process']}: {cmd[:60]}", f"pid {pid}"))
    for label, path in _packages(home, system):
        out.append(Target("package", label, str(path), True, _size(path)))
    projects = _projects(home)
    for cfg in _mcp_files(home, projects):
        _text, data = _parse(cfg.path)
        names = _ours(data, cfg.nested) if data is not None else []
        if names:
            out.append(Target("mcp", f"MCP entry ({cfg.label}): {', '.join(dict.fromkeys(names))}", str(cfg.path)))
    for plist in _launch_agents(home):
        out.append(Target("service", f"{_LABELS['service']}: {plist.name}", str(plist), True, _size(plist)))
    for kind, path in _fs_targets(home):
        legacy = path.name in ("CodeBone", "PUG") or "pug" in path.name.lower()
        label = _LABELS[kind] + (" (legacy)" if legacy else "")
        out.append(Target(kind, label, str(path), True, _size(path)))
    for app in _app_bundles(home, bundle, system, projects)[0]:
        out.append(Target("app", f"{_LABELS['app']}: {app.name}", str(app), True, _size(app)))
    return out


def run_uninstall(home=None, bundle=None, remove_app: bool = True, dry_run: bool = False, *,
                  system: Optional[bool] = None) -> Report:
    """Remove codebone. `home` defaults to the current user's home.

    `bundle` names the app bundle to remove; by default the .app this code runs from is used (real account home
    only), plus the standard locations and any bundle the Application Support symlinks point into.
    With dry_run nothing is changed and the report lists what would happen. The bundle this very process runs from
    is not deleted inline: its removal is scheduled for after the process exits (schedule_bundle_removal), so a
    caller that started the uninstall from inside the app should quit right after it returns.
    `system=None` enables machine-wide steps (processes, /Applications, claude/brew/npm, TCC, LaunchServices)
    only for the real account home; with any other home the run stays inside that directory tree.
    """
    home = _home(home)
    return _Runner(home, bundle, remove_app, dry_run, _is_system(home, system)).run()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m src.uninstall",
        description="Remove codebone from this Mac. Your project files are never touched; at most a legacy codebone "
        "entry is taken out of an MCP config file in a project folder.",
    )
    ap.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("-n", "--dry-run", action="store_true", help="show what would be removed, change nothing")
    ap.add_argument("--keep-app", action="store_true", help="remove everything except the app bundle")
    args = ap.parse_args(argv)

    try:
        plan = run_uninstall(remove_app=not args.keep_app, dry_run=True)
    except ValueError as exc:  # no usable home directory
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(plan.format())
    if args.dry_run or plan.nothing_to_remove:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("Not removing anything: no terminal to confirm on. Re-run with --yes.", file=sys.stderr)
            return 2
        try:
            answer = input("\nRemove everything listed above? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1
    print()
    report = run_uninstall(remove_app=not args.keep_app)
    print(report.format())
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
