"""Model modules: a named API (endpoints, model id, key) that coding apps can be routed through.

A module is for coding, not for codebone's own indexing. Each supported app is a target with its own on/off switch:
switching it on writes that app's own configuration to use the module, switching it off puts back exactly what was
there before. Keys live in the macOS Keychain; Claude Code fetches its key through `apiKeyHelper`. opencode can only
read a key from an environment variable or a file, so for it a private (0600) key file inside codebone's own data
directory is used. Standard library only (the uninstaller ships its own copy of the restore logic).
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bridge_common import bridge_path

KEYCHAIN_SERVICE = "codebone-module"
# Settings this module owns while a module is on. apiKeyHelper is also what marks the change as ours.
ENV_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL")
OWNED_KEYS = ENV_KEYS + ("apiKeyHelper",)

PRESETS = [
    {"name": "MiMo V2.6 Pro (Xiaomi)", "model": "mimo-v2.6-pro",
     "anthropic_url": "https://api.xiaomimimo.com/anthropic", "openai_url": "https://api.xiaomimimo.com/v1"},
    {"name": "OpenRouter", "model": "openai/gpt-4o-mini",
     "openai_url": "https://openrouter.ai/api/v1"},
    {"name": "Claude (Anthropic)", "model": "claude-sonnet-5",
     "anthropic_url": "https://api.anthropic.com/v1"},
    {"name": "OpenAI", "model": "gpt-4o",
     "openai_url": "https://api.openai.com/v1"},
    {"name": "Local Server (Ollama)", "model": "qwen2.5-coder:7b",
     "openai_url": "http://localhost:11434/v1"},
]

# app id -> (menu name, API format the app needs)
APPS = {
    "claude-code": ("Claude Code", "anthropic"),
    "codex": ("Codex", "openai"),
    "cursor": ("Cursor", "openai"),
    "antigravity": ("Antigravity (Gemini)", "openai"),
    "opencode": ("opencode", "openai"),
}
OPENCODE_PROVIDER = "codebone"
FORMAT_NAMES = {"anthropic": "Anthropic", "openai": "OpenAI"}


class SettingsUnreadable(Exception):
    """~/.claude/settings.json exists but is not a JSON object: never overwritten."""


# ── Keychain ─────────────────────────────────────────────────────────────────
class Keychain:
    """API keys in the macOS login keychain (service "codebone-module", account = module id)."""

    def set(self, module_id: str, key: str) -> None:
        # `security` takes the secret as an argument, visible to this user's own processes for
        # the few milliseconds it runs; acceptable for a local single-user machine.
        r = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", module_id, "-w", key],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            raise RuntimeError("Could not store the key in the Keychain: " + (r.stderr.strip() or "unknown error"))

    def get(self, module_id: str) -> Optional[str]:
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", module_id, "-w"],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None

    def delete(self, module_id: str) -> None:
        subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", module_id],
                       capture_output=True, timeout=15)


def key_helper_command(module_id: str) -> str:
    return f"security find-generic-password -s {KEYCHAIN_SERVICE} -a {module_id} -w"


# ── Claude settings ──────────────────────────────────────────────────────────
def settings_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / ".claude" / "settings.json"


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, RecursionError) as exc:
        raise SettingsUnreadable(f"{path} is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise SettingsUnreadable(f"{path} is not a JSON object")
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".codebone.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _is_ours(data: dict) -> bool:
    return KEYCHAIN_SERVICE in str(data.get("apiKeyHelper", ""))


def _url(module: dict, fmt: str, port: Optional[int] = None) -> Optional[str]:
    direct = module.get(f"{fmt}_url") or (module.get("base_url") if fmt == "anthropic" else None)
    if direct:
        return direct
    # No Anthropic-format URL of its own (e.g. OpenRouter): route Claude Code through the local
    # translation bridge instead, which speaks Anthropic on one side and this module's OpenAI-format
    # URL on the other. Needs a live codebone server, so it's unavailable until one is known.
    if fmt == "anthropic" and module.get("openai_url") and port:
        return f"http://127.0.0.1:{port}{bridge_path(module['openai_url'], module['model'])}"
    return None


def supports(module: dict, app_id: str, port: Optional[int] = None) -> bool:
    if app_id not in APPS:
        return False
    fmt = APPS[app_id][1]
    if _url(module, fmt, port):
        return True
    if app_id in ("codex", "antigravity"):
        return bool(_url(module, "anthropic", port))
    return False


# ── Claude Code ──────────────────────────────────────────────────────────────
def apply_claude(module: dict, previous: Optional[dict] = None, home: Optional[Path] = None,
                 port: Optional[int] = None) -> dict:
    """Route Claude Code through `module`. Returns the backup (previous values of every key touched)."""
    path = settings_path(home)
    data = _read(path)
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    if previous is None or not _is_ours(data):
        previous = {k: env.get(k) for k in ENV_KEYS}
        previous["apiKeyHelper"] = data.get("apiKeyHelper")
    env = dict(env)
    env["ANTHROPIC_BASE_URL"] = _url(module, "anthropic", port)
    env["ANTHROPIC_MODEL"] = module["model"]
    env["ANTHROPIC_SMALL_FAST_MODEL"] = module["model"]
    data["env"] = env
    data["apiKeyHelper"] = key_helper_command(module["id"])
    _write(path, data)
    return previous


def restore_settings(previous: Optional[dict], home: Optional[Path] = None) -> bool:
    """Undo apply_claude: put back the previous values. Does nothing if the settings are not ours any more."""
    path = settings_path(home)
    if not path.exists():
        return False
    data = _read(path)
    if not _is_ours(data):
        return False
    previous = previous or {}
    env = dict(data.get("env")) if isinstance(data.get("env"), dict) else {}
    for k in ENV_KEYS:
        if previous.get(k) is None:
            env.pop(k, None)
        else:
            env[k] = previous[k]
    if env:
        data["env"] = env
    else:
        data.pop("env", None)
    if previous.get("apiKeyHelper") is None:
        data.pop("apiKeyHelper", None)
    else:
        data["apiKeyHelper"] = previous["apiKeyHelper"]
    if data:
        _write(path, data)
    else:
        path.unlink()
    return True


# ── opencode ─────────────────────────────────────────────────────────────────
def opencode_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / ".config" / "opencode" / "opencode.json"


def key_file(module_id: str, home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / "Library" / "Application Support" / "codebone" / "keys" / f"opencode-{module_id}"


def _opencode_ours(data: dict) -> bool:
    prov = data.get("provider") if isinstance(data.get("provider"), dict) else {}
    entry = prov.get(OPENCODE_PROVIDER)
    return isinstance(entry, dict) and "codebone/keys" in json.dumps(entry)


def apply_opencode(module: dict, key: str, previous: Optional[dict] = None, home: Optional[Path] = None) -> dict:
    path = opencode_path(home)
    data = _read(path)  # opencode.json may contain comments: then it is refused, never rewritten
    prov = dict(data.get("provider")) if isinstance(data.get("provider"), dict) else {}
    if previous is None or not _opencode_ours(data):
        previous = {"model": data.get("model"), "provider": prov.get(OPENCODE_PROVIDER)}
    kf = key_file(module["id"], home)
    kf.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(kf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    prov[OPENCODE_PROVIDER] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": module["name"],
        "options": {"baseURL": _url(module, "openai"), "apiKey": "{file:%s}" % kf},
        "models": {module["model"]: {"name": module["model"]}},
    }
    data["provider"] = prov
    data["model"] = f"{OPENCODE_PROVIDER}/{module['model']}"
    _write(path, data)
    return previous


def restore_opencode(previous: Optional[dict], home: Optional[Path] = None) -> bool:
    path = opencode_path(home)
    if not path.exists():
        return False
    data = _read(path)
    if not _opencode_ours(data):
        return False
    previous = previous or {}
    prov = dict(data["provider"])
    for kf in (data["provider"][OPENCODE_PROVIDER].get("options", {}).get("apiKey", ""),):
        target = kf[len("{file:"):-1] if kf.startswith("{file:") and kf.endswith("}") else ""
        if target and "codebone/keys" in target:
            Path(target).unlink(missing_ok=True)
    if previous.get("provider") is None:
        prov.pop(OPENCODE_PROVIDER, None)
    else:
        prov[OPENCODE_PROVIDER] = previous["provider"]
    if prov:
        data["provider"] = prov
    else:
        data.pop("provider", None)
    if previous.get("model") is None:
        data.pop("model", None)
    else:
        data["model"] = previous["model"]
    if data:
        _write(path, data)
    else:
        path.unlink()
    return True


# ── Codex ────────────────────────────────────────────────────────────────────
def codex_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / ".codex" / "config.toml"


def _codex_ours(text: str) -> bool:
    return "CODEBONE_MANAGED" in text or "codebone" in text


def apply_codex(module: dict, key: str, previous: Optional[dict] = None, home: Optional[Path] = None,
                port: Optional[int] = None) -> dict:
    path = codex_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()

    if previous is None or not _codex_ours(text):
        prev_model = None
        for line in lines:
            if line.strip().startswith("["):
                break
            if line.strip().startswith("model ="):
                _, v = line.split("=", 1)
                prev_model = v.strip().strip('"').strip("'")
                break
        prev_shell_env = {}
        in_shell_env = False
        for line in lines:
            stripped = line.strip()
            if stripped == "[shell_environment_policy.set]":
                in_shell_env = True
                continue
            elif in_shell_env and stripped.startswith("["):
                break
            elif in_shell_env and "=" in stripped:
                k, v = stripped.split("=", 1)
                prev_shell_env[k.strip()] = v.strip().strip('"').strip("'")
        previous = {"model": prev_model, "shell_env": prev_shell_env}

    openai_url = _url(module, "openai", port)
    anthropic_url = _url(module, "anthropic", port)

    # 1. Update top-level model
    model_updated = False
    new_lines = []
    first_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            first_section = True
        if not first_section and stripped.startswith("model ="):
            new_lines.append(f'model = "{module["model"]}"')
            model_updated = True
        else:
            new_lines.append(line)
    if not model_updated:
        new_lines.insert(0, f'model = "{module["model"]}"')

    # 2. Update [shell_environment_policy.set]
    shell_keys = {
        "CODEBONE_MANAGED": "1",
    }
    if openai_url:
        shell_keys["OPENAI_BASE_URL"] = openai_url
        shell_keys["OPENAI_API_BASE"] = openai_url
        if key:
            shell_keys["OPENAI_API_KEY"] = key
        shell_keys["OPENAI_MODEL"] = module["model"]
    if anthropic_url:
        shell_keys["ANTHROPIC_BASE_URL"] = anthropic_url
        shell_keys["ANTHROPIC_MODEL"] = module["model"]
        shell_keys["ANTHROPIC_SMALL_FAST_MODEL"] = module["model"]

    found_section = False
    result_lines = []
    in_section = False
    existing_keys_handled = set()

    for line in new_lines:
        stripped = line.strip()
        if stripped == "[shell_environment_policy.set]":
            found_section = True
            in_section = True
            result_lines.append(line)
            continue
        elif in_section and stripped.startswith("["):
            for sk, sv in shell_keys.items():
                if sk not in existing_keys_handled:
                    result_lines.append(f'{sk} = "{sv}"')
                    existing_keys_handled.add(sk)
            in_section = False
            result_lines.append(line)
            continue
        elif in_section:
            if "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in shell_keys:
                    result_lines.append(f'{k} = "{shell_keys[k]}"')
                    existing_keys_handled.add(k)
                    continue
            result_lines.append(line)
        else:
            result_lines.append(line)

    if in_section:
        for sk, sv in shell_keys.items():
            if sk not in existing_keys_handled:
                result_lines.append(f'{sk} = "{sv}"')
                existing_keys_handled.add(sk)
    elif not found_section:
        result_lines.append("\n[shell_environment_policy]")
        result_lines.append('inherit = "core"')
        result_lines.append("\n[shell_environment_policy.set]")
        for sk, sv in shell_keys.items():
            result_lines.append(f'{sk} = "{sv}"')

    tmp = path.with_name(path.name + ".codebone.tmp")
    tmp.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return previous


def restore_codex(previous: Optional[dict], home: Optional[Path] = None) -> bool:
    path = codex_path(home)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if not _codex_ours(text):
        return False

    previous = previous or {}
    prev_model = previous.get("model")
    prev_shell_env = previous.get("shell_env") or {}

    lines = text.splitlines()
    first_section = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            first_section = True
        if not first_section and stripped.startswith("model ="):
            if prev_model is not None:
                new_lines.append(f'model = "{prev_model}"')
            continue
        new_lines.append(line)

    result_lines = []
    in_section = False
    codebone_keys = {"CODEBONE_MANAGED", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_KEY", "OPENAI_MODEL",
                     "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"}

    for line in new_lines:
        stripped = line.strip()
        if stripped == "[shell_environment_policy.set]":
            in_section = True
            result_lines.append(line)
            continue
        elif in_section and stripped.startswith("["):
            in_section = False
            result_lines.append(line)
            continue
        elif in_section:
            if "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in codebone_keys:
                    if k in prev_shell_env:
                        result_lines.append(f'{k} = "{prev_shell_env[k]}"')
                    continue
            result_lines.append(line)
        else:
            result_lines.append(line)

    clean_text = "\n".join(result_lines).strip()
    if clean_text and clean_text != '[shell_environment_policy]\ninherit = "core"\n\n[shell_environment_policy.set]':
        tmp = path.with_name(path.name + ".codebone.tmp")
        tmp.write_text(clean_text + "\n", encoding="utf-8")
        os.replace(tmp, path)
    else:
        path.unlink(missing_ok=True)
    return True


# ── Cursor ───────────────────────────────────────────────────────────────────
def cursor_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / "Library" / "Application Support" / "Cursor" / "User" / "settings.json"


def cursor_fallback_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / ".cursor" / "settings.json"


def _cursor_ours(data: dict) -> bool:
    return bool(data.get("codebone.cursor.managed")) or "codebone" in str(data.get("cursor.openai.apiBaseUrl", ""))


def apply_cursor(module: dict, key: str, previous: Optional[dict] = None, home: Optional[Path] = None,
                 port: Optional[int] = None) -> dict:
    p1 = cursor_path(home)
    p2 = cursor_fallback_path(home)
    target = p1 if p1.parent.exists() or not p2.parent.exists() else p2
    data = _read(target)
    if previous is None or not _cursor_ours(data):
        previous = {k: data.get(k) for k in ("cursor.openai.apiBaseUrl", "cursor.openai.apiKey", "cursor.general.model", "cursor.openai.model")}
    url = _url(module, "openai", port) or _url(module, "anthropic", port)
    data["cursor.openai.apiBaseUrl"] = url
    data["cursor.openai.apiKey"] = key
    data["cursor.general.model"] = module["model"]
    data["cursor.openai.model"] = module["model"]
    data["codebone.cursor.managed"] = True
    _write(target, data)
    return previous


def restore_cursor(previous: Optional[dict], home: Optional[Path] = None) -> bool:
    restored = False
    previous = previous or {}
    for path in (cursor_path(home), cursor_fallback_path(home)):
        if not path.exists():
            continue
        data = _read(path)
        if not _cursor_ours(data):
            continue
        for k in ("cursor.openai.apiBaseUrl", "cursor.openai.apiKey", "cursor.general.model", "cursor.openai.model"):
            if previous.get(k) is None:
                data.pop(k, None)
            else:
                data[k] = previous[k]
        data.pop("codebone.cursor.managed", None)
        if data:
            _write(path, data)
        else:
            path.unlink()
        restored = True
    return restored


# ── Antigravity (Gemini) ─────────────────────────────────────────────────────
def antigravity_ide_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / "Library" / "Application Support" / "Antigravity IDE" / "User" / "settings.json"


def gemini_config_path(home: Optional[Path] = None) -> Path:
    return Path(home or Path.home()) / ".gemini" / "config" / "config.json"


def _antigravity_ours(data: dict) -> bool:
    return bool(data.get("codebone.antigravity.managed")) or "CODEBONE_MANAGED" in json.dumps(data.get("terminal.integrated.env.osx", {}))


def apply_antigravity(module: dict, key: str, previous: Optional[dict] = None, home: Optional[Path] = None,
                      port: Optional[int] = None) -> dict:
    path = antigravity_ide_path(home)
    data = _read(path)
    tenv = dict(data.get("terminal.integrated.env.osx") or {})
    if previous is None or not _antigravity_ours(data):
        previous = {
            "terminal_env": {k: tenv.get(k) for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                                                      "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "CODEBONE_MANAGED")},
            "codebone_model": data.get("codebone.model"),
            "codebone_baseUrl": data.get("codebone.baseUrl"),
        }
    openai_url = _url(module, "openai", port)
    anthropic_url = _url(module, "anthropic", port)
    tenv["CODEBONE_MANAGED"] = "1"
    if openai_url:
        tenv["OPENAI_BASE_URL"] = openai_url
        if key:
            tenv["OPENAI_API_KEY"] = key
        tenv["OPENAI_MODEL"] = module["model"]
    if anthropic_url:
        tenv["ANTHROPIC_BASE_URL"] = anthropic_url
        tenv["ANTHROPIC_MODEL"] = module["model"]
        tenv["ANTHROPIC_SMALL_FAST_MODEL"] = module["model"]
    data["terminal.integrated.env.osx"] = tenv
    data["codebone.model"] = module["model"]
    data["codebone.baseUrl"] = openai_url or anthropic_url
    data["codebone.antigravity.managed"] = True
    _write(path, data)

    g_cfg = gemini_config_path(home)
    if g_cfg.exists():
        try:
            gdata = _read(g_cfg)
            us = dict(gdata.get("userSettings") or {})
            us["codeboneModule"] = {"model": module["model"], "base_url": openai_url or anthropic_url}
            gdata["userSettings"] = us
            _write(g_cfg, gdata)
        except Exception:
            pass
    return previous


def restore_antigravity(previous: Optional[dict], home: Optional[Path] = None) -> bool:
    path = antigravity_ide_path(home)
    restored = False
    if path.exists():
        data = _read(path)
        if _antigravity_ours(data):
            tenv = dict(data.get("terminal.integrated.env.osx") or {})
            prev_env = (previous or {}).get("terminal_env") or {}
            for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                      "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "CODEBONE_MANAGED"):
                if prev_env.get(k) is None:
                    tenv.pop(k, None)
                else:
                    tenv[k] = prev_env[k]
            if tenv:
                data["terminal.integrated.env.osx"] = tenv
            else:
                data.pop("terminal.integrated.env.osx", None)
            if (previous or {}).get("codebone_model") is None:
                data.pop("codebone.model", None)
            else:
                data["codebone.model"] = previous["codebone_model"]
            if (previous or {}).get("codebone_baseUrl") is None:
                data.pop("codebone.baseUrl", None)
            else:
                data["codebone.baseUrl"] = previous["codebone_baseUrl"]
            data.pop("codebone.antigravity.managed", None)
            if data:
                _write(path, data)
            else:
                path.unlink()
            restored = True
    g_cfg = gemini_config_path(home)
    if g_cfg.exists():
        try:
            gdata = _read(g_cfg)
            if isinstance(gdata.get("userSettings"), dict):
                gdata["userSettings"].pop("codeboneModule", None)
                _write(g_cfg, gdata)
        except Exception:
            pass
    return restored


# ── library (stored in codebone's config; keys never are) ─────────────────────
def list_modules(config) -> List[dict]:
    return [m for m in config.get("modules", []) if isinstance(m, dict) and m.get("id")]


def get_module(config, module_id: Optional[str]) -> Optional[dict]:
    return next((m for m in list_modules(config) if m["id"] == module_id), None)


def enabled_apps(config) -> List[str]:
    return [a for a, on in (config.get("module_apps") or {}).items() if on and a in APPS]


def validate(name: str, model: str, key: str, anthropic_url: str = "", openai_url: str = "") -> Optional[str]:
    """Returns a problem description, or None if the entry is usable."""
    if not (name.strip() and model.strip() and key.strip()):
        return "Name, model and API key are required."
    urls = [u.strip() for u in (anthropic_url, openai_url) if u and u.strip()]
    if not urls:
        return "Give at least one base URL (Anthropic format for Claude Code, OpenAI format for opencode)."
    for u in urls:
        low = u.lower()
        if not (low.startswith("https://") or low.startswith(("http://127.0.0.1", "http://localhost"))):
            return "Base URLs must start with https:// (http:// is only allowed for localhost)."
    return None


def add_module(config, name: str, model: str, key: str, anthropic_url: str = "", openai_url: str = "",
               keychain: Optional[Keychain] = None) -> dict:
    problem = validate(name, model, key, anthropic_url, openai_url)
    if problem:
        raise ValueError(problem)
    module = {"id": uuid.uuid4().hex[:12], "name": name.strip(), "model": model.strip()}
    if anthropic_url.strip():
        module["anthropic_url"] = anthropic_url.strip().rstrip("/")
    if openai_url.strip():
        module["openai_url"] = openai_url.strip().rstrip("/")
    (keychain or Keychain()).set(module["id"], key.strip())
    config.set("modules", list_modules(config) + [module])
    return module


def rename_module(config, module_id: str, new_name: str) -> Optional[dict]:
    mods = list_modules(config)
    found = None
    for m in mods:
        if m["id"] == module_id:
            m["name"] = new_name.strip()
            found = m
            break
    if found:
        config.set("modules", mods)
    return found


def update_module_key(config, module_id: str, new_key: str, keychain: Optional[Keychain] = None) -> None:
    (keychain or Keychain()).set(module_id, new_key.strip())


def get_module_key(config, module_id: str, keychain: Optional[Keychain] = None) -> str:
    return (keychain or Keychain()).get(module_id) or ""


def detect_provider(mod: dict) -> str:
    openai_url = (mod.get("openai_url") or "").lower()
    anthropic_url = (mod.get("anthropic_url") or "").lower()
    name = (mod.get("name") or "").lower()
    if "openrouter" in openai_url or "openrouter" in anthropic_url or "openrouter" in name:
        return "OpenRouter"
    if "api.openai.com" in openai_url:
        return "OpenAI"
    if "api.anthropic.com" in anthropic_url:
        return "Anthropic"
    if "11434" in openai_url or "ollama" in name or "ollama" in openai_url:
        return "Ollama"
    if "1234" in openai_url or "lmstudio" in name or "lmstudio" in openai_url:
        return "LM Studio"
    if openai_url:
        return "OpenAI"
    if anthropic_url:
        return "Anthropic"
    return "API"


def format_model_name(mod: dict) -> str:
    raw_name = (mod.get("name") or "Custom Model").strip()
    provider = detect_provider(mod)
    if f"({provider})" in raw_name:
        return raw_name
    if raw_name.lower().startswith(provider.lower()) and "(" in raw_name and raw_name.endswith(")"):
        inner = raw_name[len(provider):].strip(" ()")
        return f"{inner} ({provider})"
    return f"{raw_name} ({provider})"


def _port(config) -> Optional[int]:
    return config.get("active_port") or config.get("server_port", 8053)


def _apply(config, app_id: str, module: dict, home, keychain) -> None:
    backups = dict(config.get("module_backups") or {})
    previous = backups.get(app_id) if app_id in enabled_apps(config) else None
    if app_id == "claude-code":
        backups[app_id] = apply_claude(module, previous, home, _port(config))
    elif app_id == "codex":
        key = (keychain or Keychain()).get(module["id"]) or ""
        backups[app_id] = apply_codex(module, key, previous, home, _port(config))
    elif app_id == "cursor":
        key = (keychain or Keychain()).get(module["id"]) or ""
        backups[app_id] = apply_cursor(module, key, previous, home, _port(config))
    elif app_id == "antigravity":
        key = (keychain or Keychain()).get(module["id"]) or ""
        backups[app_id] = apply_antigravity(module, key, previous, home, _port(config))
    else:
        key = (keychain or Keychain()).get(module["id"])
        if not key:
            raise ValueError("The API key is missing from the Keychain; remove the module and add it again.")
        backups[app_id] = apply_opencode(module, key, previous, home)
    config.set("module_backups", backups)


def set_app_enabled(config, app_id: str, on: bool, home: Optional[Path] = None,
                    keychain: Optional[Keychain] = None) -> Optional[dict]:
    """One app's switch: on = it goes through the selected module, off = its normal setup."""
    if app_id not in APPS:
        raise ValueError("Unknown app")
    apps = dict(config.get("module_apps") or {})
    backups = dict(config.get("module_backups") or {})
    if not on:
        # Always attempt the restore, even if our own bookkeeping says this app is already off:
        # a crash, a config desync, or a manual edit can leave settings.json pointing at a module
        # while codebone believes it already put things back. Restoring is a no-op when the
        # settings file is not ours (restore_settings/restore_opencode check that themselves).
        if app_id == "claude-code":
            restore_settings(backups.get(app_id), home)
        elif app_id == "codex":
            restore_codex(backups.get(app_id), home)
        elif app_id == "cursor":
            restore_cursor(backups.get(app_id), home)
        elif app_id == "antigravity":
            restore_antigravity(backups.get(app_id), home)
        else:
            restore_opencode(backups.get(app_id), home)
        apps[app_id] = False
        backups.pop(app_id, None)
        config.set("module_backups", backups)
        config.set("module_apps", apps)
        return None
    module = get_module(config, config.get("module_selected"))
    if not module:
        raise ValueError("Add and select a module first.")
    if not supports(module, app_id, _port(config)):
        raise ValueError(f"{module['name']} has no {FORMAT_NAMES[APPS[app_id][1]]}-format URL, which {APPS[app_id][0]} needs.")
    _apply(config, app_id, module, home, keychain)
    apps[app_id] = True
    config.set("module_apps", apps)
    return module


def select_module(config, module_id: str, home: Optional[Path] = None, keychain: Optional[Keychain] = None) -> None:
    """Choose which module is used. Apps that are switched on move to it right away (or off, if it cannot serve them)."""
    module = get_module(config, module_id)
    if not module:
        raise ValueError("Unknown module")
    config.set("module_selected", module_id)
    for app_id in enabled_apps(config):
        set_app_enabled(config, app_id, supports(module, app_id, _port(config)), home=home, keychain=keychain)


def remove_module(config, module_id: str, home: Optional[Path] = None, keychain: Optional[Keychain] = None) -> None:
    if config.get("module_selected") == module_id:
        for app_id in enabled_apps(config):
            set_app_enabled(config, app_id, False, home=home)
        config.set("module_selected", None)
    (keychain or Keychain()).delete(module_id)
    config.set("modules", [m for m in list_modules(config) if m["id"] != module_id])


# ── master switch & recovery ───────────────────────────────────────────────────
def force_restore_all(config, home: Optional[Path] = None) -> None:
    """Unconditional recovery: strip every setting codebone's modules could have written, for every app,
    whether or not our own bookkeeping (module_apps / module_backups) still agrees that anything is on.
    This is the fix for a coding app stuck on a module's API (e.g. showing API errors) after codebone's
    normal off-switch failed to catch it — it never trusts local state, only what's actually on disk."""
    path = settings_path(home)
    if path.exists():
        try:
            data = _read(path)
            if _is_ours(data):
                env = dict(data.get("env")) if isinstance(data.get("env"), dict) else {}
                for k in ENV_KEYS:
                    env.pop(k, None)
                if env:
                    data["env"] = env
                else:
                    data.pop("env", None)
                data.pop("apiKeyHelper", None)
                if data:
                    _write(path, data)
                else:
                    path.unlink()
        except SettingsUnreadable:
            pass

    op_path = opencode_path(home)
    if op_path.exists():
        try:
            data = _read(op_path)
            if _opencode_ours(data):
                prov = dict(data.get("provider") or {})
                entry = prov.pop(OPENCODE_PROVIDER, None)
                if isinstance(entry, dict):
                    kf = entry.get("options", {}).get("apiKey", "")
                    target = kf[len("{file:"):-1] if kf.startswith("{file:") and kf.endswith("}") else ""
                    if target and "codebone/keys" in target:
                        Path(target).unlink(missing_ok=True)
                if prov:
                    data["provider"] = prov
                else:
                    data.pop("provider", None)
                if str(data.get("model", "")).startswith(f"{OPENCODE_PROVIDER}/"):
                    data.pop("model", None)
                if data:
                    _write(op_path, data)
                else:
                    op_path.unlink()
        except SettingsUnreadable:
            pass

    try:
        restore_codex(None, home)
    except Exception:
        pass

    try:
        restore_cursor(None, home)
    except Exception:
        pass

    try:
        restore_antigravity(None, home)
    except Exception:
        pass

    config.set("module_apps", {})
    config.set("module_backups", {})
    config.set("modules_enabled", False)
    config.set("modules_paused_apps", [])


def set_modules_master(config, on: bool, home: Optional[Path] = None, keychain: Optional[Keychain] = None) -> None:
    """The single on/off switch for Modules. Off = every app goes back to its normal setup and stays there;
    codebone remembers which apps were routed so turning it back on restores exactly that."""
    if not on:
        active = enabled_apps(config)
        for app_id in active:
            set_app_enabled(config, app_id, False, home=home, keychain=keychain)
        config.set("modules_paused_apps", active)
        config.set("modules_enabled", False)
        return
    config.set("modules_enabled", True)
    paused = config.get("modules_paused_apps") or []
    if paused:
        for app_id in paused:
            try:
                set_app_enabled(config, app_id, True, home=home, keychain=keychain)
            except (ValueError, SettingsUnreadable):
                pass
    elif not (config.get("module_apps") or {}):
        # First switch-on with nothing routed yet: every app the selected module can serve starts
        # enabled instead of an empty checklist — "Use for Claude Code / opencode" default to on.
        # A later off/on cycle restores whatever the user last chose (set_app_enabled above).
        module = get_module(config, config.get("module_selected"))
        if module:
            for app_id in APPS:
                if supports(module, app_id, _port(config)):
                    try:
                        set_app_enabled(config, app_id, True, home=home, keychain=keychain)
                    except (ValueError, SettingsUnreadable):
                        pass
    config.set("modules_paused_apps", [])


# ── connection test ──────────────────────────────────────────────────────────
def test_connection(base_url: str, model: str, key: str, timeout: float = 20.0, fmt: str = "anthropic") -> Tuple[bool, str]:
    """One-token request: Anthropic /v1/messages or OpenAI /chat/completions, depending on the format."""
    if fmt == "openai":
        url, body = "/chat/completions", {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
    else:
        url, body = "/v1/messages", {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
    req = urllib.request.Request(
        base_url.rstrip("/") + url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key, "authorization": f"Bearer {key}",
                 "anthropic-version": "2023-06-01"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (200 <= resp.status < 300), f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read()[:160].decode("utf-8", "replace")
        except Exception:  # reset (OSError) or truncated chunked body (IncompleteRead): message only
            text = ""
        if exc.code in (401, 403):
            return False, "The endpoint rejected the API key."
        return False, f"HTTP {exc.code}: {text}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"Could not reach the endpoint: {getattr(exc, 'reason', exc)}"
