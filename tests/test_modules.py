"""Model modules: library, routing switch, settings safety, connection test, uninstall."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src import modules
from src import uninstall as un
from src.config import Config


class FakeKeychain:
    def __init__(self):
        self.items = {}

    def set(self, module_id, key):
        self.items[module_id] = key

    def get(self, module_id):
        return self.items.get(module_id)

    def delete(self, module_id):
        self.items.pop(module_id, None)


@pytest.fixture()
def env(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    return Config(tmp_path / "cfg" / "config.json"), home, FakeKeychain()


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text())


def add(cfg, kc, name="MiMo V2.6 Pro (Xiaomi)"):
    p = modules.PRESETS[0]
    return modules.add_module(cfg, name, p["model"], "sk-secret-123", p["anthropic_url"], p["openai_url"], keychain=kc)


def test_preset_matches_the_documented_anthropic_endpoint():
    p = modules.PRESETS[0]
    assert p["anthropic_url"] == "https://api.xiaomimimo.com/anthropic" and p["model"] == "mimo-v2.6-pro"
    assert p["openai_url"] == "https://api.xiaomimimo.com/v1"


def test_add_stores_the_key_in_the_keychain_not_in_the_config(env):
    cfg, home, kc = env
    m = add(cfg, kc)
    assert kc.get(m["id"]) == "sk-secret-123"
    assert "sk-secret-123" not in (cfg.config_file.read_text())


def test_validation_rejects_empty_fields_and_plain_http(env):
    cfg, home, kc = env
    for args in (("", "m", "k", "https://x"), ("n", "m", "k", "http://evil.example"), ("n", "m", "", "https://x"),
                 ("n", "m", "k", "")):
        with pytest.raises(ValueError):
            modules.add_module(cfg, *args, keychain=kc)
    modules.add_module(cfg, "local", "m", "k", "http://localhost:4000", keychain=kc)  # local proxies are fine


def test_switch_on_routes_claude_and_off_restores_the_previous_settings_exactly(env):
    cfg, home, kc = env
    original = {"model": "opus", "env": {"FOO": "1", "ANTHROPIC_MODEL": "claude-sonnet-x"}, "apiKeyHelper": "echo mine",
                "permissions": {"allow": ["Bash(ls)"]}}
    (home / ".claude" / "settings.json").write_text(json.dumps(original))
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])

    modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    s = settings(home)
    assert s["env"]["ANTHROPIC_BASE_URL"] == m["anthropic_url"] and s["env"]["ANTHROPIC_MODEL"] == "mimo-v2.6-pro"
    assert "sk-secret-123" not in json.dumps(s) and "codebone-module" in s["apiKeyHelper"]
    assert s["permissions"] == original["permissions"] and s["env"]["FOO"] == "1"

    modules.set_app_enabled(cfg, 'claude-code', False, home=home)
    assert settings(home) == original
    assert modules.enabled_apps(cfg) == []


def test_switching_modules_while_on_keeps_the_original_backup(env):
    cfg, home, kc = env
    a, b = add(cfg, kc, "A"), add(cfg, kc, "B")
    cfg.set("module_selected", a["id"])
    modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    modules.select_module(cfg, b["id"], home=home)
    assert settings(home)["apiKeyHelper"].endswith(f"-a {b['id']} -w")
    modules.set_app_enabled(cfg, 'claude-code', False, home=home)
    assert not (home / ".claude" / "settings.json").exists()  # the file did not exist before: nothing is left behind


def test_unreadable_settings_are_never_overwritten(env):
    cfg, home, kc = env
    (home / ".claude" / "settings.json").write_text('{ "env": // comment\n}')
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    with pytest.raises(modules.SettingsUnreadable):
        modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    assert (home / ".claude" / "settings.json").read_text() == '{ "env": // comment\n}'
    assert modules.enabled_apps(cfg) == []


def test_settings_changed_by_the_user_meanwhile_are_left_alone(env):
    cfg, home, kc = env
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    data = settings(home)
    data["apiKeyHelper"] = "echo something-else"  # no longer ours
    (home / ".claude" / "settings.json").write_text(json.dumps(data))
    modules.set_app_enabled(cfg, 'claude-code', False, home=home)
    assert settings(home)["apiKeyHelper"] == "echo something-else"


def test_remove_module_switches_off_and_deletes_the_key(env):
    cfg, home, kc = env
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    modules.remove_module(cfg, m["id"], home=home, keychain=kc)
    assert modules.list_modules(cfg) == [] and kc.items == {} and modules.enabled_apps(cfg) == []


def test_connection_test_reports_success_and_rejected_keys():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            ok = self.headers.get("x-api-key") == "good" and self.path == "/anthropic/v1/messages"
            self.send_response(200 if ok else 401)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}/anthropic"
    try:
        assert modules.test_connection(base, "m", "good")[0] is True
        ok, msg = modules.test_connection(base, "m", "bad")
        assert ok is False and "rejected" in msg
        assert modules.test_connection("http://127.0.0.1:9", "m", "k")[0] is False
    finally:
        srv.shutdown()


def test_uninstall_restores_claude_settings_and_constants_match(env, tmp_path):
    cfg, home, kc = env
    assert (un._MODULE_MARK, un._MODULE_ENV_KEYS) == (modules.KEYCHAIN_SERVICE, modules.ENV_KEYS)
    original = {"env": {"FOO": "1"}, "model": "opus"}
    (home / ".claude" / "settings.json").write_text(json.dumps(original, indent=2) + "\n")
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    modules.set_app_enabled(cfg, 'claude-code', True, home=home)
    # the uninstaller finds the backup in codebone's config inside the (fake) home
    support = home / "Library" / "Application Support" / "codebone"
    support.mkdir(parents=True)
    (support / "config.json").write_text(cfg.config_file.read_text())

    dry = un.run_uninstall(home=home, dry_run=True)
    assert any("model routing" in r for r in dry.removed) and "codebone-module" in (home / ".claude" / "settings.json").read_text()
    report = un.run_uninstall(home=home, remove_app=False)
    assert not report.errors
    assert settings(home) == original


def test_opencode_target_writes_a_provider_and_restores_it(env):
    cfg, home, kc = env
    oc = home / ".config" / "opencode" / "opencode.json"
    oc.parent.mkdir(parents=True)
    original = {"$schema": "https://opencode.ai/config.json", "model": "anthropic/sonnet", "theme": "dark"}
    oc.write_text(json.dumps(original))
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    modules.set_app_enabled(cfg, "opencode", True, home=home, keychain=kc)

    data = json.loads(oc.read_text())
    prov = data["provider"]["codebone"]
    assert prov["options"]["baseURL"] == m["openai_url"] and data["model"] == "codebone/mimo-v2.6-pro"
    kf = modules.key_file(m["id"], home)
    assert kf.read_text() == "sk-secret-123" and oct(kf.stat().st_mode & 0o777) == "0o600"
    assert "sk-secret-123" not in oc.read_text() and data["theme"] == "dark"

    modules.set_app_enabled(cfg, "opencode", False, home=home)
    assert json.loads(oc.read_text()) == original and not kf.exists()


def test_apps_switch_independently_and_need_a_matching_url(env):
    cfg, home, kc = env
    only_anthropic = modules.add_module(cfg, "A", "m", "k", "https://a.example", keychain=kc)
    cfg.set("module_selected", only_anthropic["id"])
    with pytest.raises(ValueError, match="OpenAI-format URL"):
        modules.set_app_enabled(cfg, "opencode", True, home=home, keychain=kc)
    both = add(cfg, kc)
    modules.select_module(cfg, both["id"], home=home)
    modules.set_app_enabled(cfg, "claude-code", True, home=home, keychain=kc)
    modules.set_app_enabled(cfg, "opencode", True, home=home, keychain=kc)
    assert sorted(modules.enabled_apps(cfg)) == ["claude-code", "opencode"]
    modules.set_app_enabled(cfg, "opencode", False, home=home)
    assert modules.enabled_apps(cfg) == ["claude-code"]
    modules.select_module(cfg, only_anthropic["id"], home=home)  # Claude stays on and moves to the new module
    assert settings(home)["env"]["ANTHROPIC_BASE_URL"] == "https://a.example"


def test_uninstall_restores_opencode_too(env):
    cfg, home, kc = env
    oc = home / ".config" / "opencode" / "opencode.json"
    oc.parent.mkdir(parents=True)
    oc.write_text(json.dumps({"theme": "dark"}, indent=2) + "\n")
    m = add(cfg, kc)
    cfg.set("module_selected", m["id"])
    modules.set_app_enabled(cfg, "opencode", True, home=home, keychain=kc)
    support = home / "Library" / "Application Support" / "codebone"
    (support / "config.json").write_text(cfg.config_file.read_text())
    assert not un.run_uninstall(home=home, remove_app=False).errors
    assert json.loads(oc.read_text()) == {"theme": "dark"} and not support.exists()
