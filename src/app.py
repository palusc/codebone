"""The 'Bone' UI — PUG's macOS menu bar app."""
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

import rumps
from AppKit import NSOpenPanel

from .config import Config
from .logging_setup import configure_logging
from .server import ServerThread
from .service import PugService

configure_logging()
logger = logging.getLogger("pug.app")

BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = BASE_DIR / "resources"

ICON_ACTIVE = str(RESOURCES_DIR / "bone_idle.png")
ICON_INACTIVE = str(RESOURCES_DIR / "bone_inactive.png")


def _get_icon(path_str: str) -> str:
    p = Path(path_str)
    if p.exists():
        return str(p)
    alt = Path("resources") / p.name
    if alt.exists():
        return str(alt)
    return path_str


def choose_folder(title: str) -> Optional[str]:
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setCanChooseFiles_(False)
    panel.setCanChooseDirectories_(True)
    panel.setAllowsMultipleSelection_(False)
    if panel.runModal():
        urls = panel.URLs()
        if urls:
            return str(urls[0].path())
    return None


def choose_file(title: str, extensions: list[str]) -> Optional[str]:
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(extensions)
    if panel.runModal():
        urls = panel.URLs()
        if urls:
            return str(urls[0].path())
    return None


def copy_to_clipboard(text: str):
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    except Exception as exc:
        logger.error("Failed to copy to clipboard: %s", exc)


class PugApp(rumps.App):
    def __init__(self):
        active_icon = _get_icon(ICON_INACTIVE)
        super().__init__("PUG", icon=active_icon, quit_button=None)

        self.config = Config()
        self.service = PugService(self.config)
        self.server = ServerThread(self.service)

        # Activity callbacks for sniffing status
        self.service.on_activity_start = self._on_sniff_start
        self.service.on_activity_end = self._on_sniff_end

        # Primary menu items
        self.select_project_item = rumps.MenuItem("Select Project Folder...", callback=self.choose_project)
        self.status_item = rumps.MenuItem("Status: Not configured")
        self.server_item = rumps.MenuItem("Server: Running on localhost:3000")
        self.copy_curl_item = rumps.MenuItem("Copy Context-Curl", callback=self.copy_curl)

        # "More..." Submenu
        self.brain_builtin_item = rumps.MenuItem("Built-in (Qwen 0.8B)", callback=self.select_brain_builtin)
        self.brain_local_item = rumps.MenuItem("Local URL (Ollama / LM Studio)...", callback=self.select_brain_local)
        self.brain_cloud_item = rumps.MenuItem("Cloud BYOK (OpenAI / Anthropic)...", callback=self.select_brain_cloud)
        self.add_model_item = rumps.MenuItem("Add Model File (.gguf)...", callback=self.add_model_file)

        self.brain_menu = rumps.MenuItem("Brain Selection")
        self.brain_menu.update([
            self.brain_builtin_item,
            self.brain_local_item,
            self.brain_cloud_item,
            self.add_model_item,
        ])

        self.reset_map_item = rumps.MenuItem("Reset Map", callback=self.reset_map)
        self.quit_item = rumps.MenuItem("Quit PUG", callback=self.quit_app)

        self.more_menu = rumps.MenuItem("More...")
        self.more_menu.update([
            self.brain_menu,
            self.reset_map_item,
            None,
            self.quit_item,
        ])

        self.menu = [
            self.select_project_item,
            self.status_item,
            self.server_item,
            self.copy_curl_item,
            None,
            self.more_menu,
        ]

        self._update_brain_checks()
        self._update_ui_state()

        # Start background server
        self.server.start()

        # Start watcher if configured
        if self.config.is_configured:
            self.service.start(auto_scan=True)

    def _update_ui_state(self):
        """Updates menu bar icon and status labels based on current configuration."""
        if self.config.is_configured:
            project_name = self.config.project_path.name
            sniff_state = "Sniffing" if self.service.sniffing else "Idle"
            self.status_item.title = f"Status: {project_name} | {sniff_state}"
            self.icon = _get_icon(ICON_ACTIVE)
        else:
            self.status_item.title = "Status: Not configured"
            self.icon = _get_icon(ICON_INACTIVE)

        port = self.config.get("server_port", 3000)
        self.server_item.title = f"Server: Running on localhost:{port}"

    def _on_sniff_start(self):
        self._update_ui_state()

    def _on_sniff_end(self):
        self._update_ui_state()

    def _update_brain_checks(self):
        provider = self.config.get("brain_provider", "builtin")
        self.brain_builtin_item.state = (provider == "builtin")
        self.brain_local_item.state = (provider == "local_url")
        self.brain_cloud_item.state = (provider == "cloud")

    def choose_project(self, _):
        path = choose_folder("Select Project Folder to Sniff")
        if path:
            self.config.set("project_path", path)
            self.service.stop()
            self._update_ui_state()
            self.service.start(auto_scan=True)
            rumps.notification("PUG", f"Watching {Path(path).name}", "Project indexed successfully.")

    def copy_curl(self, _):
        cmd = self.server.curl_command()
        copy_to_clipboard(cmd)
        rumps.notification("PUG", "Copied to clipboard", cmd)

    def select_brain_builtin(self, _):
        self.config.set("brain_provider", "builtin")
        self._update_brain_checks()
        self.service.reload_provider()
        rumps.notification("PUG", "Brain switched", "Built-in Qwen 0.8B (Metal) active.")

    def select_brain_local(self, _):
        current = self.config.get("brain_local_url", "http://localhost:11434/api/generate")
        window = rumps.Window(
            message="Enter the URL of your local LLM server (Ollama / LM Studio):",
            title="Local URL Provider",
            default_text=current,
            ok="Save",
            cancel="Cancel",
        )
        resp = window.run()
        if resp.clicked and resp.text:
            self.config.set("brain_local_url", resp.text.strip())
            self.config.set("brain_provider", "local_url")
            self._update_brain_checks()
            self.service.reload_provider()
            rumps.notification("PUG", "Brain switched", f"Local URL active: {resp.text.strip()}")

    def select_brain_cloud(self, _):
        current_vendor = self.config.get("brain_cloud_vendor", "openai")
        current_key = self.config.get("brain_cloud_api_key", "")
        window = rumps.Window(
            message="Enter your API key:\nFormat: 'openai:sk-...' or 'anthropic:sk-ant-...'",
            title="Cloud BYOK",
            default_text=f"{current_vendor}:{current_key}" if current_key else "openai:",
            ok="Save",
            cancel="Cancel",
        )
        resp = window.run()
        if resp.clicked and resp.text:
            parts = resp.text.strip().split(":", 1)
            vendor = parts[0].lower() if len(parts) == 2 else "openai"
            api_key = parts[1].strip() if len(parts) == 2 else parts[0].strip()
            self.config.set("brain_cloud_vendor", vendor)
            self.config.set("brain_cloud_api_key", api_key)
            self.config.set("brain_provider", "cloud")
            self._update_brain_checks()
            self.service.reload_provider()
            rumps.notification("PUG", "Brain switched", f"Cloud BYOK ({vendor.upper()}) active.")

    def add_model_file(self, _):
        path = choose_file("Select .gguf Model File", ["gguf"])
        if path:
            entry = self.config.add_model(path)
            self.config.select_model(path)
            self.config.set("brain_provider", "builtin")
            self._update_brain_checks()
            self.service.reload_provider()
            rumps.notification("PUG", "Model added", f"Loaded model: {entry['name']}")

    def reset_map(self, _):
        self.service.reset_map()
        self._update_ui_state()
        rumps.notification("PUG", "Map reset", "Semantic knowledge graph cleared.")
        if self.config.is_configured:
            threading.Thread(target=self.service.rescan_all, daemon=True).start()

    def quit_app(self, _):
        self.service.stop()
        self.server.stop()
        rumps.quit_application()


def main():
    app = PugApp()
    app.run()


if __name__ == "__main__":
    main()
