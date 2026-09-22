"""The 'Bone' UI — CodeBone macOS menu bar app."""
import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

import rumps
from AppKit import (
    NSOpenPanel,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSFont,
    NSFontAttributeName,
    NSAttributedString,
)

from .config import Config
from .logging_setup import configure_logging
from .server import ServerThread
from .service import CodeBoneService, PugService

configure_logging()
logger = logging.getLogger("codebone.app")

BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = BASE_DIR / "resources"

ICON_ACTIVE = str(RESOURCES_DIR / "bone_active.png")
ICON_INACTIVE = str(RESOURCES_DIR / "bone_inactive.png")


def _get_icon(path_str: str) -> str:
    p = Path(path_str)
    if p.exists():
        return str(p)
    alt = Path("resources") / p.name
    if alt.exists():
        return str(alt)
    alt2 = Path(__file__).resolve().parent.parent / "resources" / p.name
    if alt2.exists():
        return str(alt2)
    try:
        import AppKit
        res_dir = AppKit.NSBundle.mainBundle().resourcePath()
        if res_dir:
            bundle_icon = Path(res_dir) / p.name
            if bundle_icon.exists():
                return str(bundle_icon)
    except Exception:
        pass
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


class CodeBoneApp(rumps.App):
    def __init__(self):
        try:
            NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass

        self.config = Config()
        self.service = CodeBoneService(self.config)
        self.server = ServerThread(self.service)

        active_icon = _get_icon(ICON_ACTIVE if self.config.is_configured else ICON_INACTIVE)
        super().__init__("CodeBone", icon=active_icon, template=True, quit_button=None)
        self.template = True
        if not self.icon:
            self.title = "CodeBone"

        # Activity callbacks for sniffing status
        self.service.on_activity_start = self._on_sniff_start
        self.service.on_activity_end = self._on_sniff_end

        # Header / Status Section (100% Native macOS NSMenuItems)
        self.header_item = rumps.MenuItem("CodeBone", callback=self.show_about)
        try:
            bold_font = NSFont.boldSystemFontOfSize_(13)
            attr = NSAttributedString.alloc().initWithString_attributes_(
                "CodeBone", {NSFontAttributeName: bold_font}
            )
            self.header_item._menuitem.setAttributedTitle_(attr)
        except Exception:
            pass

        self.status_item = rumps.MenuItem("● Watching for changes", callback=self.on_click_status)
        self.repo_item = rumps.MenuItem("Repository: None", callback=self.open_repo)
        self.model_item = rumps.MenuItem("Model: Built-in (Qwen 0.5B)", callback=self.on_click_model)
        self.stats_item = rumps.MenuItem("Files: 0  ·  Connections: 0", callback=self.view_live_graph)

        # Primary Actions
        self.select_project_item = rumps.MenuItem("Select Project Folder...", callback=self.choose_project)
        self.adopt_scan_item = rumps.MenuItem("Adopt / Link Existing Scan...", callback=self.choose_adopt_scan)
        self.copy_curl_item = rumps.MenuItem("Copy Context-Curl", callback=self.copy_curl)
        self.view_graph_item = rumps.MenuItem("View Live Graph...", callback=self.view_live_graph)

        # Brain / Model Selection Submenu
        self.brain_builtin_item = rumps.MenuItem("Built-in (Qwen 0.5B)", callback=self.select_brain_builtin)
        self.brain_local_item = rumps.MenuItem("Local URL (Ollama / LM Studio)...", callback=self.select_brain_local)
        self.brain_cloud_item = rumps.MenuItem("Cloud BYOK (OpenAI / Anthropic)...", callback=self.select_brain_cloud)
        self.add_model_item = rumps.MenuItem("Add Model File (.gguf)...", callback=self.add_model_file)
        self.deep_scan_item = rumps.MenuItem("Deep Scan Mode (7B)...", callback=self.run_deep_scan)

        self.brain_menu = rumps.MenuItem("Brain Selection")
        self.brain_menu.update([
            self.brain_builtin_item,
            self.brain_local_item,
            self.brain_cloud_item,
            self.add_model_item,
            None,
            self.deep_scan_item,
        ])

        # Settings Submenu
        self.rescan_item = rumps.MenuItem("Rescan Workspace Now", callback=self.rescan_workspace)
        self.view_logs_item = rumps.MenuItem("View Logs...", callback=self.view_logs)
        self.export_scan_item = rumps.MenuItem("Export Scan Snapshot...", callback=self.export_scan_snapshot)
        self.import_scan_item = rumps.MenuItem("Import Scan File (.sqlite3)...", callback=self.import_scan_file)
        self.reset_map_item = rumps.MenuItem("Reset Knowledge Map", callback=self.reset_map)

        self.settings_menu = rumps.MenuItem("Settings")
        self.settings_menu.update([
            self.brain_menu,
            None,
            self.rescan_item,
            self.view_logs_item,
            None,
            self.export_scan_item,
            self.import_scan_item,
            self.reset_map_item,
        ])

        self.quit_item = rumps.MenuItem("Quit CodeBone", callback=self.quit_app)

        self.menu = [
            self.header_item,
            self.status_item,
            self.repo_item,
            self.model_item,
            self.stats_item,
            None,
            self.select_project_item,
            self.adopt_scan_item,
            self.copy_curl_item,
            self.view_graph_item,
            None,
            self.settings_menu,
            None,
            self.quit_item,
        ]

        self._update_brain_checks()
        self._update_ui_state()

        # Push live stats periodically
        self._stats_timer = rumps.Timer(self._push_stats, 2)
        self._stats_timer.start()

        # Start background server
        self.server.start()

        # Start watcher if configured
        if self.config.is_configured:
            self.service.start(auto_scan=True)

    def show_about(self, _):
        rumps.alert(
            title="CodeBone",
            message="Real-time Codebase Intelligence for LLMs\nVersion 1.0.0\n\nRuns local-first semantic analysis and provides knowledge graphs to AI coding agents.",
            ok="OK",
        )

    def on_click_status(self, _):
        if not self.config.is_configured:
            self.choose_project(_)
        else:
            self.rescan_workspace(_)

    def open_repo(self, _):
        if self.config.project_path and self.config.project_path.exists():
            subprocess.Popen(["open", str(self.config.project_path)])
        else:
            self.choose_project(_)

    def on_click_model(self, _):
        self.add_model_file(_)

    def rescan_workspace(self, _):
        if not self.config.is_configured:
            rumps.alert("CodeBone", "No project configured. Please select a project folder first.")
            return
        p_name = self.config.project_path.name if self.config.project_path else "project"
        rumps.notification("CodeBone", "Rescan Started", f"Scanning {p_name}...")

        def _run():
            try:
                total, sniffed, skipped = self.service.rescan_all(force=True)
                rumps.notification(
                    "CodeBone",
                    "Rescan Complete",
                    f"{sniffed} updated, {skipped} unchanged out of {total} files.",
                )
            except Exception as exc:
                logger.exception("Rescan failed")
                rumps.notification("CodeBone", "Rescan Failed", str(exc))
            finally:
                self._update_ui_state()

        threading.Thread(target=_run, daemon=True, name="codebone-rescan").start()

    def _push_stats(self, _timer=None):
        data = self.service.stats_snapshot()
        configured = data.get("configured", False)
        sniffing = data.get("sniffing", False)
        repo_name = data.get("repo_name", "None")
        model_name = data.get("model_name", "Built-in (Qwen 0.5B)")
        file_count = data.get("file_count", 0)
        connection_count = data.get("connection_count", 0)

        # Status item
        if sniffing:
            status_text = "● Sniffing & Reconciling..."
        elif configured:
            status_text = "● Watching for changes"
        else:
            status_text = "○ Not configured"
        if self.status_item.title != status_text:
            self.status_item.title = status_text

        # Repo item (parent folder name)
        repo_text = f"Repository: {repo_name}"
        if self.repo_item.title != repo_text:
            self.repo_item.title = repo_text
        if configured and self.config.project_path:
            try:
                self.repo_item._menuitem.setToolTip_(f"Folder: {self.config.project_path}\nClick to open in Finder")
            except Exception:
                pass

        # Model item
        model_text = f"Model: {model_name}"
        if self.model_item.title != model_text:
            self.model_item.title = model_text

        # Stats item (Files & Connections only)
        stats_text = f"Files: {file_count}  ·  Connections: {connection_count}"
        if self.stats_item.title != stats_text:
            self.stats_item.title = stats_text
        try:
            self.stats_item._menuitem.setToolTip_("Click to view interactive knowledge graph")
        except Exception:
            pass

    def _update_ui_state(self):
        """Updates the menu bar icon and refreshes menu status."""
        self.icon = _get_icon(ICON_ACTIVE if self.config.is_configured else ICON_INACTIVE)
        if not self.icon:
            self.title = "CodeBone"
        self._update_brain_checks()
        self._push_stats()

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
        if not path:
            return
        p = Path(path)
        self.config.set("project_path", str(p))
        self.service.stop()
        self._update_ui_state()

        # Check if an existing scan matches this folder
        matching = self.service.scans.find_matching_scan(p)
        if matching:
            rumps.notification(
                "CodeBone",
                f"Found Previous Scan: {matching.get('project_name')}",
                "Reconciling folder structure via AI...",
            )

            def _run_matched():
                try:
                    rep = self.service.adopt_scan(matching["id"])
                    reused = rep.get("reused_count", 0)
                    renamed = rep.get("renamed_count", 0)
                    modified = rep.get("modified_count", 0)
                    added = rep.get("added_count", 0)
                    rumps.notification(
                        "CodeBone",
                        f"Adopted {matching.get('project_name')}",
                        f"{reused} files reused, {renamed} renamed, {modified} modified, {added} added.",
                    )
                except Exception as exc:
                    logger.warning("Matching scan adoption failed, falling back to rescan: %s", exc)
                    self.service.rescan_all()
                finally:
                    self._update_ui_state()
                    self.service.start(auto_scan=False)

            threading.Thread(target=_run_matched, daemon=True, name="codebone-matched-adopt").start()
        else:
            self.service.start(auto_scan=True)
            rumps.notification("CodeBone", f"Watching {p.name}", "Project indexed successfully.")

    def choose_adopt_scan(self, _):
        if not self.config.is_configured:
            path = choose_folder("Select Target Project Folder to Reconcile")
            if not path:
                return
            self.config.set("project_path", path)
            self.service.stop()
            self._update_ui_state()

        scans = self.service.scans.list_scans()
        source_target = None

        if scans:
            msg_lines = ["Select an existing codebase scan to adopt:\n"]
            for i, s in enumerate(scans[:8], 1):
                name = s.get("project_name", "Unknown")
                f_count = s.get("file_count", 0)
                domains = ", ".join(s.get("domains", [])[:2]) or "no domains"
                msg_lines.append(f"{i}. {name} ({f_count} files, {domains})")
            msg_lines.append("\nEnter number (or leave empty to browse for a .sqlite3 file):")

            window = rumps.Window(
                message="\n".join(msg_lines),
                title="Adopt / Link Existing Scan",
                default_text="1",
                ok="Adopt",
                cancel="Cancel",
            )
            resp = window.run()
            if not resp.clicked:
                return

            entered = resp.text.strip()
            if entered.isdigit() and 1 <= int(entered) <= len(scans):
                source_target = scans[int(entered) - 1]["id"]
            elif entered:
                for s in scans:
                    if s.get("project_name", "").lower() == entered.lower() or s["id"] == entered:
                        source_target = s["id"]
                        break

        if not source_target:
            f_path = choose_file("Select Existing Scan Database (.sqlite3)", ["sqlite3", "db", "sqlite"])
            if not f_path:
                return
            source_target = f_path

        def _run_adopt():
            rumps.notification(
                "CodeBone",
                "Reconciling Codebase Scan",
                "Comparing file hash signatures & running AI reconciliation...",
            )
            try:
                rep = self.service.adopt_scan(source_target)
                reused = rep.get("reused_count", 0)
                renamed = rep.get("renamed_count", 0)
                modified = rep.get("modified_count", 0)
                added = rep.get("added_count", 0)
                rumps.notification(
                    "CodeBone",
                    "Scan Adoption Complete!",
                    f"{reused} files reused, {renamed} renamed, {modified} modified, {added} added. Semantic Graph synchronized!",
                )
                self._update_ui_state()
                self.service.start(auto_scan=False)
            except Exception as exc:
                logger.exception("Error during scan adoption: %s", exc)
                rumps.notification("CodeBone", "Adoption Failed", str(exc))

        threading.Thread(target=_run_adopt, daemon=True, name="codebone-user-adopt").start()

    def export_scan_snapshot(self, _):
        if not self.config.is_configured:
            rumps.notification("CodeBone", "Not Configured", "Configure a project first to export its scan.")
            return
        dest_folder = choose_folder("Select Destination Folder for Scan Snapshot")
        if not dest_folder:
            return
        p_name = self.config.project_path.name
        dest_file = Path(dest_folder) / f"{p_name}_scan.sqlite3"
        try:
            self.service.storage.snapshot_to(dest_file)
            rumps.notification("CodeBone", "Scan Exported", f"Saved to {dest_file.name}")
        except Exception as exc:
            rumps.notification("CodeBone", "Export Failed", str(exc))

    def import_scan_file(self, _):
        f_path = choose_file("Select Scan Snapshot File (.sqlite3)", ["sqlite3", "db", "sqlite"])
        if not f_path:
            return
        try:
            meta = self.service.scans.import_scan(Path(f_path))
            rumps.notification("CodeBone", "Scan Imported", f"Imported '{meta['project_name']}' ({meta['file_count']} files).")
        except Exception as exc:
            rumps.notification("CodeBone", "Import Failed", str(exc))

    def view_live_graph(self, _):
        port = self.config.get("server_port", 3000)
        url = f"http://127.0.0.1:{port}/codebone/graph/ui"
        try:
            subprocess.Popen(["open", url])
        except Exception as exc:
            logger.error("Failed to open graph UI: %s", exc)

    def view_logs(self, _):
        from .logging_setup import LOG_FILE
        try:
            subprocess.Popen(["open", "-a", "Console", str(LOG_FILE)])
        except Exception:
            try:
                subprocess.Popen(["open", str(LOG_FILE)])
            except Exception as exc:
                logger.error("Failed to open log file: %s", exc)

    def copy_curl(self, _):
        cmd = self.server.curl_command()
        copy_to_clipboard(cmd)
        rumps.notification("CodeBone", "Copied to clipboard", cmd)

    def select_brain_builtin(self, _):
        self.config.set("brain_provider", "builtin")
        self._update_brain_checks()
        self.service.reload_provider()
        rumps.notification("CodeBone", "Brain switched", "Built-in Qwen 0.5B (Metal) active.")

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
            rumps.notification("CodeBone", "Brain switched", f"Local URL active: {resp.text.strip()}")

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
            rumps.notification("CodeBone", "Brain switched", f"Cloud BYOK ({vendor.upper()}) active.")

    def add_model_file(self, _):
        path = choose_file("Select .gguf Model File", ["gguf"])
        if path:
            entry = self.config.add_model(path)
            self.config.select_model(path)
            self.config.set("brain_provider", "builtin")
            self._update_brain_checks()
            self.service.reload_provider()
            rumps.notification("CodeBone", "Model added", f"Loaded model: {entry['name']}")

    def run_deep_scan(self, _):
        if not self.config.is_configured:
            rumps.alert("Deep Scan Mode", "Please select a project folder first.")
            return

        model_path = self.config.get("deep_scan_model_path")
        if not model_path or not Path(model_path).exists():
            proceed = rumps.alert(
                title="Deep Scan Mode",
                message=(
                    "Deep Scan re-analyzes your whole project with a larger, slower local model "
                    "(e.g. Qwen 7B) for more thorough architecture extraction.\n\n"
                    "This uses far more RAM, disk, and time than the default 0.5B brain. "
                    "Only turn this on if you know what you're doing.\n\n"
                    "Choose a .gguf model file to continue."
                ),
                ok="Choose Model...",
                cancel="Cancel",
            )
            if proceed != 1:
                return
            path = choose_file("Select Deep Scan Model (.gguf, e.g. Qwen 7B)", ["gguf"])
            if not path:
                return
            self.config.set("deep_scan_model_path", path)
            model_path = path

        def _run():
            rumps.notification("CodeBone", "Deep Scan Started", f"Re-analyzing project with {Path(model_path).name}...")
            try:
                total, sniffed, _ = self.service.run_deep_scan()
                rumps.notification("CodeBone", "Deep Scan Complete", f"{sniffed}/{total} files re-analyzed.")
            except Exception as exc:
                logger.exception("Deep scan failed")
                rumps.notification("CodeBone", "Deep Scan Failed", str(exc))
            finally:
                self._update_ui_state()

        threading.Thread(target=_run, daemon=True, name="codebone-deep-scan").start()

    def reset_map(self, _):
        self.service.reset_map()
        self._update_ui_state()
        rumps.notification("CodeBone", "Map reset", "Semantic knowledge graph cleared.")
        if self.config.is_configured:
            threading.Thread(target=self.service.rescan_all, daemon=True).start()

    def quit_app(self, _):
        self._stats_timer.stop()
        self.service.stop()
        self.server.stop()
        rumps.quit_application()


def main():
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    app = CodeBoneApp()
    app.run()


# Backwards compatibility alias
PugApp = CodeBoneApp


if __name__ == "__main__":
    main()
