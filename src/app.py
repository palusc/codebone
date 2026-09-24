"""The 'Bone' UI — codebone macOS menu bar app."""
import fcntl
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import objc
import rumps
from PyObjCTools import AppHelper
from Foundation import NSRunLoop, NSDate
from AppKit import (
    NSOpenPanel,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSUnderlineStyleAttributeName,
    NSParagraphStyleAttributeName,
    NSMutableParagraphStyle,
    NSColor,
    NSAttributedString,
    NSView,
    NSTextField,
    NSSwitch,
    NSImageView,
    NSImage,
    NSImageSymbolConfiguration,
    NSBox,
    NSBoxSeparator,
    NSControl,
    NSControlStateValueOn,
    NSControlStateValueOff,
    NSMenu,
    NSRect,
    NSPoint,
    NSSize,
    NSObject,
    NSBezierPath,
    NSTrackingArea,
    NSTrackingMouseEnteredAndExited,
    NSTrackingActiveAlways,
    NSTrackingInVisibleRect,
    NSCompositingOperationSourceOver,
    NSCompositingOperationSourceAtop,
    NSRectFillUsingOperation,
    NSCursor,
    NSLineBreakByTruncatingTail,
)

from .config import Config
from .feedback import record_feedback
from .logging_setup import configure_logging
from .permissions import check_folder_access, open_full_disk_access_settings, reveal_codebone_in_finder
from .server import ServerThread
from .service import CodeBoneService, PugService
from .updater import CURRENT_VERSION, check_for_updates, download_and_install_update, restart_app

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


def _set_symbol_icon(menu_item: Optional[rumps.MenuItem], symbol_name: str, size: float = 15.0):
    """Sets a native Apple SF Symbol vector icon on an NSMenuItem with standard point size."""
    if menu_item is None:
        return
    raw_item = getattr(menu_item, "_menuitem", menu_item)
    try:
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
        if img:
            img = img.copy()
            try:
                cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, 4)
                configured = img.imageWithSymbolConfiguration_(cfg)
                if configured:
                    img = configured.copy()
            except Exception:
                pass
            img.setSize_(NSSize(size, size))
            img.setTemplate_(True)
            raw_item.setImage_(img)
    except Exception as exc:
        logger.debug("Could not set SF Symbol '%s': %s", symbol_name, exc)


def choose_folder(title: str) -> Optional[str]:
    """Displays native macOS open folder panel with clean runloop draining and proper activation."""
    try:
        NSMenu.cancelTracking()
    except Exception:
        pass

    # Drain runloop so any active NSMenu tracking window dismisses completely from screen
    try:
        run_loop = NSRunLoop.currentRunLoop()
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.15))
    except Exception:
        pass

    app = NSApplication.sharedApplication()
    prev_policy = app.activationPolicy()
    try:
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        panel = NSOpenPanel.openPanel()
        panel.setTitle_(title)
        panel.setMessage_(title)
        panel.setPrompt_("Select")
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setResolvesAliases_(True)
        panel.setCanCreateDirectories_(True)
        panel.center()

        response = panel.runModal()
        if response == 1:  # NSModalResponseOK
            urls = panel.URLs()
            if urls and len(urls) > 0:
                return str(urls[0].path())
    finally:
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            app.setActivationPolicy_(prev_policy)
        except Exception:
            pass
    return None


def choose_file(title: str, extensions: list[str]) -> Optional[str]:
    """Displays native macOS open file panel with clean runloop draining and proper activation."""
    try:
        NSMenu.cancelTracking()
    except Exception:
        pass

    # Drain runloop so any active NSMenu tracking window dismisses completely from screen
    try:
        run_loop = NSRunLoop.currentRunLoop()
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.15))
    except Exception:
        pass

    app = NSApplication.sharedApplication()
    prev_policy = app.activationPolicy()
    try:
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)

        panel = NSOpenPanel.openPanel()
        panel.setTitle_(title)
        panel.setMessage_(title)
        panel.setPrompt_("Open")
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setResolvesAliases_(True)
        panel.setAllowedFileTypes_(extensions)
        panel.center()

        response = panel.runModal()
        if response == 1:  # NSModalResponseOK
            urls = panel.URLs()
            if urls and len(urls) > 0:
                return str(urls[0].path())
    finally:
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            app.setActivationPolicy_(prev_policy)
        except Exception:
            pass
    return None


def copy_to_clipboard(text: str):
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    except Exception as exc:
        logger.error("Failed to copy to clipboard: %s", exc)


def _create_clean_graph_icon(size: float = 18.0) -> Optional[NSImage]:
    """Creates a clean, native Apple SF Symbol vector icon for the graph card row."""
    try:
        sym = NSImage.imageWithSystemSymbolName_accessibilityDescription_("point.3.connected.trianglepath.dotted", None)
        if not sym:
            sym = NSImage.imageWithSystemSymbolName_accessibilityDescription_("network", None)
        if sym:
            sym = sym.copy()
            sym.setSize_(NSSize(size, size))
            sym.setTemplate_(True)
            return sym
    except Exception as exc:
        logger.debug("Could not create clean graph icon: %s", exc)
    return None


class StatusDotView(NSView):
    """Circular status indicator dot with a soft ambient glow."""

    def initWithFrame_(self, frame):
        self = objc.super(StatusDotView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._color = NSColor.systemGreenColor()
        return self

    def setColor_(self, color):
        if self._color != color:
            self._color = color
            self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        glow_rect = NSRect(NSPoint(1.0, 1.0), NSSize(w - 2.0, h - 2.0))
        glow_path = NSBezierPath.bezierPathWithOvalInRect_(glow_rect)
        self._color.colorWithAlphaComponent_(0.25).setFill()
        glow_path.fill()

        dot_rect = NSRect(NSPoint(3.0, 3.0), NSSize(w - 6.0, h - 6.0))
        dot_path = NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
        self._color.setFill()
        dot_path.fill()


class CardRowView(NSControl):
    """Custom clickable card row with hover and press highlights matching native macOS popovers."""

    def initWithFrame_(self, frame):
        self = objc.super(CardRowView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._target = None
        self._action = None
        self._is_hovered = False
        self._is_pressed = False
        tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect,
            self,
            None,
        )
        self.addTrackingArea_(tracking)
        return self

    def setTarget_(self, target):
        self._target = target

    def setAction_(self, action):
        self._action = action

    def hitTest_(self, point):
        res = objc.super(CardRowView, self).hitTest_(point)
        if res is not None:
            return self
        return None

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.pointingHandCursor())

    def mouseEntered_(self, event):
        self._is_hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._is_hovered = False
        self._is_pressed = False
        self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        self._is_pressed = True
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        was_pressed = self._is_pressed
        self._is_pressed = False
        self.setNeedsDisplay_(True)
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if was_pressed and self.mouse_inRect_(point, self.bounds()):
            if self._target and self._action:
                self.sendAction_to_(self._action, self._target)

    def drawRect_(self, rect):
        if self._is_pressed:
            NSColor.labelColor().colorWithAlphaComponent_(0.15).setFill()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 6.0, 6.0)
            path.fill()
        elif self._is_hovered:
            NSColor.labelColor().colorWithAlphaComponent_(0.08).setFill()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 6.0, 6.0)
            path.fill()


class FolderButton(NSTextField):
    """Clickable, pixel-aligned folder label beneath 'codebone' that reveals the project folder in Finder."""

    def initWithFrame_(self, frame):
        self = objc.super(FolderButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self._target = None
        self._action = None
        self._is_hovered = False
        self._folder_name = ""
        self.setBezeled_(False)
        self.setDrawsBackground_(False)
        self.setEditable_(False)
        self.setSelectable_(False)
        self.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        self.setFont_(NSFont.systemFontOfSize_(11.5))
        self.setTextColor_(NSColor.secondaryLabelColor())
        self.setToolTip_("Click to reveal project folder in Finder")

        tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect,
            self,
            None,
        )
        self.addTrackingArea_(tracking)
        return self

    def setTarget_(self, target):
        self._target = target

    def setAction_(self, action):
        self._action = action

    def setFolderName_(self, name: str):
        val = str(name or "")
        if self._folder_name != val:
            self._folder_name = val
            self._update_appearance()

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.pointingHandCursor())

    def mouseEntered_(self, event):
        self._is_hovered = True
        self._update_appearance()

    def mouseExited_(self, event):
        self._is_hovered = False
        self._update_appearance()

    def mouseDown_(self, event):
        pass

    def mouseUp_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if self.mouse_inRect_(point, self.bounds()):
            try:
                NSMenu.cancelTracking()
            except Exception:
                pass
            if self._target and self._action:
                self.sendAction_to_(self._action, self._target)

    def _update_appearance(self):
        color = NSColor.labelColor() if self._is_hovered else NSColor.secondaryLabelColor()
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineBreakMode_(NSLineBreakByTruncatingTail)
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(11.5),
            NSForegroundColorAttributeName: color,
            NSParagraphStyleAttributeName: para,
        }
        if self._is_hovered:
            attrs[NSUnderlineStyleAttributeName] = 1
        attr_str = NSAttributedString.alloc().initWithString_attributes_(self._folder_name, attrs)
        self.setAttributedStringValue_(attr_str)


class HeaderActionDelegate(NSObject):
    """Action delegate for folder click and card row click."""

    def initWithApp_(self, app):
        self = objc.super(HeaderActionDelegate, self).init()
        if self is None:
            return None
        self.app = app
        return self

    @objc.IBAction
    def folderClicked_(self, sender):
        if not self.app:
            return
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
        if self.app.config.is_configured and self.app.config.project_path and self.app.config.project_path.exists():
            self.app.open_repo(None)
        else:
            self.app.choose_project(None)

    @objc.IBAction
    def cardClicked_(self, sender):
        if not self.app:
            return
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
        if not self.app.config.is_configured:
            self.app.choose_project(None)
        else:
            self.app.view_live_graph(None)


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
        super().__init__("codebone", icon=active_icon, template=True, quit_button=None)
        self.template = True
        if not self.icon:
            self.title = "codebone"

        # Activity callbacks for sniffing status
        self.service.on_activity_start = self._on_sniff_start
        self.service.on_activity_end = self._on_sniff_end

        # Custom Header View (Title, Folder/Prompt, Status Dot, Divider, Knowledge Graph Card)
        (
            self.header_view,
            self.header_action_delegate,
            self.folder_btn,
            self.status_dot,
            self.card_stats_label,
        ) = self._build_header_view()
        self.header_item = rumps.MenuItem("codebone", callback=None)
        try:
            self.header_item._menuitem.setView_(self.header_view)
        except Exception as exc:
            logger.warning("Could not set custom header view: %s", exc)

        # Primary Action: Select Project Folder
        self.select_project_item = rumps.MenuItem("Select Project Folder...", callback=self.choose_project)
        _set_symbol_icon(self.select_project_item, "folder")

        # MCP AI Assistants Setup
        self.mcp_setup_item = rumps.MenuItem("Connect AI Assistants (MCP)...", callback=self.open_mcp_setup)
        _set_symbol_icon(self.mcp_setup_item, "bolt.fill")

        # Recent Projects / History Submenu (Verlauf)
        self.recent_projects_menu = rumps.MenuItem("Recent Projects")
        _set_symbol_icon(self.recent_projects_menu, "clock.arrow.circlepath")

        # Model modules: API endpoints Claude Code can be routed through (for coding, not for indexing)
        self.modules_menu = rumps.MenuItem("Modules")
        _set_symbol_icon(self.modules_menu, "square.stack.3d.up")

        # Model Selection Submenu (Dynamic active model list)
        self.brain_menu = rumps.MenuItem("Model")
        _set_symbol_icon(self.brain_menu, "brain")

        # Settings Items
        self.adopt_scan_item = rumps.MenuItem("Adopt / Link Existing Scan...", callback=self.choose_adopt_scan)
        _set_symbol_icon(self.adopt_scan_item, "link")

        self.copy_curl_item = rumps.MenuItem("Copy Context (curl)", callback=self.copy_curl)
        _set_symbol_icon(self.copy_curl_item, "doc.on.clipboard")

        self.rescan_item = rumps.MenuItem("Scan Project Now", callback=self.rescan_workspace)
        _set_symbol_icon(self.rescan_item, "arrow.clockwise")

        self.open_repo_item = rumps.MenuItem("Open Project in Finder...", callback=self.open_repo)
        _set_symbol_icon(self.open_repo_item, "folder")

        self.view_logs_item = rumps.MenuItem("View Logs...", callback=self.view_logs)
        _set_symbol_icon(self.view_logs_item, "doc.text")

        self.full_disk_access_item = rumps.MenuItem("macOS Disk Access Settings...", callback=self.open_disk_access_settings)
        _set_symbol_icon(self.full_disk_access_item, "lock.shield")

        self.export_scan_item = rumps.MenuItem("Export Scan Snapshot...", callback=self.export_scan_snapshot)
        _set_symbol_icon(self.export_scan_item, "square.and.arrow.up")

        self.import_scan_item = rumps.MenuItem("Import Scan File (.sqlite3)...", callback=self.import_scan_file)
        _set_symbol_icon(self.import_scan_item, "square.and.arrow.down")

        self.reset_map_item = rumps.MenuItem("Reset Knowledge Map", callback=self.reset_map)
        _set_symbol_icon(self.reset_map_item, "trash")

        self.settings_menu = rumps.MenuItem("Settings")
        _set_symbol_icon(self.settings_menu, "gearshape")

        self.feedback_item = rumps.MenuItem("Feedback & Bug Report...", callback=self.open_feedback_dialog)
        _set_symbol_icon(self.feedback_item, "exclamationmark.bubble")

        self.check_updates_item = rumps.MenuItem("Check for Updates...", callback=self.check_updates)
        _set_symbol_icon(self.check_updates_item, "arrow.triangle.2.circlepath")

        self.uninstall_item = rumps.MenuItem("Uninstall codebone...", callback=self.confirm_uninstall)
        _set_symbol_icon(self.uninstall_item, "trash")
        self.settings_menu.update([
            self.brain_menu,
            self.adopt_scan_item,
            self.copy_curl_item,
            None,
            self.open_repo_item,
            self.view_logs_item,
            self.full_disk_access_item,
            None,
            self.check_updates_item,
            self.export_scan_item,
            self.import_scan_item,
            self.reset_map_item,
            None,
            self.uninstall_item,
        ])

        self.about_item = rumps.MenuItem("About codebone...", callback=self.show_about)
        _set_symbol_icon(self.about_item, "info.circle")

        self.quit_item = rumps.MenuItem("Quit codebone", callback=self.quit_app)
        _set_symbol_icon(self.quit_item, "power")

        self.menu = [
            self.header_item,
            self.mcp_setup_item,
            None,
            self.rescan_item,
            self.select_project_item,
            self.recent_projects_menu,
            self.modules_menu,
            None,
            self.settings_menu,
            None,
            self.feedback_item,
            self.about_item,
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
        self.service.ensure_builtin_model()

    def _build_header_view(self):
        """Constructs the native macOS popover header view with live status indicator and knowledge graph card."""
        w, h = 276.0, 94.0
        container = NSView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(w, h)))
        delegate = HeaderActionDelegate.alloc().initWithApp_(self)

        # 1. Top row title: icon + "codebone" (bold 15pt)
        icon_path = _get_icon(ICON_ACTIVE)
        bone_img = None
        if Path(icon_path).exists():
            bone_img = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if not bone_img:
            bone_img = NSImage.imageWithSystemSymbolName_accessibilityDescription_("point.3.connected.trianglepath.dotted", None)
        if bone_img:
            bone_img.setSize_(NSSize(16, 16))
            bone_img.setTemplate_(True)
            logo_iv = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(14, 69), NSSize(16, 16)))
            logo_iv.setImage_(bone_img)
            container.addSubview_(logo_iv)

        title_lbl = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(34, 66), NSSize(200, 20)))
        title_lbl.setStringValue_("codebone")
        title_lbl.setFont_(NSFont.boldSystemFontOfSize_(15.0))
        title_lbl.setTextColor_(NSColor.labelColor())
        title_lbl.setBezeled_(False)
        title_lbl.setDrawsBackground_(False)
        title_lbl.setEditable_(False)
        title_lbl.setSelectable_(False)
        container.addSubview_(title_lbl)

        # 2. Top row folder link: small folder icon + name directly under "codebone"
        folder_sym = NSImage.imageWithSystemSymbolName_accessibilityDescription_("folder", None)
        if folder_sym:
            folder_sym.setSize_(NSSize(13, 13))
            folder_sym.setTemplate_(True)
            f_iv = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(14, 49), NSSize(13, 13)))
            f_iv.setImage_(folder_sym)
            container.addSubview_(f_iv)

        folder_btn = FolderButton.alloc().initWithFrame_(NSRect(NSPoint(31, 47), NSSize(205, 17)))
        folder_btn.setTarget_(delegate)
        folder_btn.setAction_(objc.selector(delegate.folderClicked_, signature=b"v@:@"))
        init_folder = self.config.project_path.name if (self.config.is_configured and self.config.project_path) else "Click to index local codebase"
        folder_btn.setFolderName_(init_folder)
        container.addSubview_(folder_btn)

        # 3. Top row status indicator dot (Green = Active/Watching, Blue = Sniffing/Indexing, Gray = Unconfigured)
        status_dot = StatusDotView.alloc().initWithFrame_(NSRect(NSPoint(248, 60), NSSize(14, 14)))
        status_dot.setColor_(NSColor.systemGreenColor() if self.config.is_configured else NSColor.secondaryLabelColor())
        container.addSubview_(status_dot)

        # 4. Divider line
        div = NSBox.alloc().initWithFrame_(NSRect(NSPoint(12, 41), NSSize(252, 1)))
        div.setBoxType_(NSBoxSeparator)
        container.addSubview_(div)

        # 5. Bottom row: clickable CardRowView for Knowledge Graph HUD
        card = CardRowView.alloc().initWithFrame_(NSRect(NSPoint(6, 5), NSSize(264, 32)))
        card.setTarget_(delegate)
        card.setAction_(objc.selector(delegate.cardClicked_, signature=b"v@:@"))
        card.setToolTip_("Click to open interactive Live Graph in browser")

        # 5a. Clean Apple SF Symbol vector icon
        graph_img = _create_clean_graph_icon(18.0)
        graph_iv = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(8, 7), NSSize(18, 18)))
        if graph_img:
            graph_iv.setImage_(graph_img)
        card.addSubview_(graph_iv)

        # 5b. Card stats line (vertically centered, no extra subtitle below)
        init_files = self.service.storage.file_count() if self.config.is_configured else 0
        init_edges = len(self.service.storage.graph_edges()) if self.config.is_configured else 0
        stats_lbl = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(34, 7), NSSize(204, 18)))
        stats_lbl.setStringValue_(f"{init_files} Nodes  ·  {init_edges} Connections" if self.config.is_configured else "0 Nodes  ·  0 Connections")
        stats_lbl.setFont_(NSFont.systemFontOfSize_(12.0))
        stats_lbl.setTextColor_(NSColor.labelColor())
        stats_lbl.setBezeled_(False)
        stats_lbl.setDrawsBackground_(False)
        stats_lbl.setEditable_(False)
        stats_lbl.setSelectable_(False)
        stats_lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        card.addSubview_(stats_lbl)

        # 5c. Chevron
        chev = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(244, 7), NSSize(14, 18)))
        chev.setStringValue_("›")
        chev.setFont_(NSFont.boldSystemFontOfSize_(15.0))
        chev.setTextColor_(NSColor.tertiaryLabelColor())
        chev.setBezeled_(False)
        chev.setDrawsBackground_(False)
        chev.setEditable_(False)
        chev.setSelectable_(False)
        card.addSubview_(chev)

        container.addSubview_(card)
        return container, delegate, folder_btn, status_dot, stats_lbl

    def show_about(self, _):
        """Displays comprehensive project and architecture overview."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        rumps.alert(
            title="About codebone",
            message=(
                f"codebone (v{CURRENT_VERSION})\n"
                "Real-time Local Codebase Intelligence & Knowledge Graph\n\n"
                "Runs zero-cloud semantic indexing and provides live architecture "
                "context (models, routes, events, and business domains) to AI coding agents.\n\n"
                "• 100% Local & Private (Metal-accelerated GGUF)\n"
                "• Incremental Real-time File System Watcher\n"
                "• Interactive Visual Knowledge Graph HUD\n"
                "• Model Context Protocol (MCP) Server\n\n"
                "Developed by palusc"
            ),
            ok="OK",
        )

    def check_updates(self, _):
        """Checks GitHub Releases for new codebone versions with interactive update and install flow."""
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass

        try:
            run_loop = NSRunLoop.currentRunLoop()
            run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
        except Exception:
            pass

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        try:
            update_info = check_for_updates(current_version=CURRENT_VERSION)
        except Exception as exc:
            logger.error("Failed to check for updates: %s", exc)
            rumps.alert(
                title="Update Check Failed",
                message=f"Could not connect to GitHub to check for updates:\n{exc}",
                ok="OK",
            )
            return

        if not update_info.get("update_available"):
            if update_info.get("error"):
                err_msg = update_info["error"]
                rumps.alert(
                    title="Update Check Failed",
                    message=f"Could not check for updates:\n{err_msg}",
                    ok="OK",
                )
            else:
                latest = update_info.get("latest_version", CURRENT_VERSION)
                rumps.alert(
                    title="codebone is Up to Date",
                    message=f"codebone v{latest} is currently the newest version.",
                    ok="OK",
                )
            return

        # An update is available
        latest_ver = update_info.get("latest_version")
        rel_notes = (update_info.get("release_notes") or "").strip()
        if len(rel_notes) > 350:
            rel_notes = rel_notes[:347] + "..."
        if not rel_notes:
            rel_notes = "Performance improvements, UI refinements, and bug fixes."

        size_mb = update_info.get("asset_size", 0) / (1024 * 1024)
        size_str = f" ({size_mb:.1f} MB)" if size_mb > 0 else ""

        confirm = rumps.alert(
            title=f"codebone v{latest_ver} Available",
            message=(
                f"A new version of codebone is available!\n\n"
                f"Current Version: v{CURRENT_VERSION}\n"
                f"Latest Version:  v{latest_ver}{size_str}\n\n"
                f"Release Notes:\n{rel_notes}\n\n"
                f"Would you like to download and install this update now?"
            ),
            ok="Install & Restart",
            cancel="Later",
        )

        if confirm != 1:
            return

        download_url = update_info.get("download_url")
        if not download_url:
            rumps.alert(
                title="Update Package Missing",
                message=(
                    f"No automated update bundle was found for v{latest_ver}.\n"
                    f"Please visit: {update_info.get('html_url')}"
                ),
                ok="OK",
            )
            return

        rumps.notification(
            title="codebone Update",
            subtitle=f"Downloading v{latest_ver}...",
            message="Installing update in the background.",
        )

        def _do_install():
            try:
                download_and_install_update(download_url, expected_version=latest_ver,
                                            checksum_url=update_info.get("checksum_url"))
                rumps.notification(
                    title="codebone Update",
                    subtitle="Update Installed",
                    message="Restarting codebone now...",
                )
                restart_app()
            except Exception as err:
                logger.error("Failed to install update: %s", err)

                def _show():
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    rumps.alert(
                        title="Update Installation Failed",
                        message=f"An error occurred while installing the update:\n{err}",
                        ok="OK",
                    )
                self._on_main(_show)

        threading.Thread(target=_do_install, daemon=True, name="codebone-updater").start()

    def open_repo(self, _):
        if self.config.project_path and self.config.project_path.exists():
            subprocess.Popen(["open", str(self.config.project_path)])
        else:
            self.choose_project(_)

    def rescan_workspace(self, _):
        if not self.config.is_configured:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("codebone", "No project configured. Please select a project folder first.")
            return
        p_name = self.config.project_path.name if self.config.project_path else "project"
        rumps.notification("codebone", "Scan Started", f"Scanning {p_name} and building knowledge graph...")

        def _run():
            try:
                def _on_prog(cur, tot, f):
                    self._on_main(self._push_stats)

                total, sniffed, skipped = self.service.rescan_all(on_progress=_on_prog, wait=True)
                conn_count = len(self.service.storage.graph_edges())
                rumps.notification(
                    "codebone",
                    "Scan Complete",
                    f"Mapped {total} files & {conn_count} connections ({sniffed} updated, {skipped} cached).",
                )
            except Exception as exc:
                logger.exception("Rescan failed")
                rumps.notification("codebone", "Rescan Failed", str(exc))
            finally:
                self._on_main(self._update_ui_state)

        threading.Thread(target=_run, daemon=True, name="codebone-rescan").start()

    def _push_stats(self, _timer=None):
        data = self.service.stats_snapshot()
        configured = data.get("configured", False)
        running = data.get("running", False)
        sniffing = data.get("sniffing", False)
        scan_progress = data.get("scan_progress")
        repo_name = data.get("repo_name", "None")
        file_count = data.get("file_count", 0)
        connection_count = data.get("connection_count", 0)

        signature = (configured, running, sniffing, repo_name, file_count, connection_count,
                     json.dumps(scan_progress, sort_keys=True) if scan_progress else None)
        if signature == getattr(self, "_last_stats_signature", None):
            return  # nothing changed: do not make AppKit redraw the menu every 2 s
        self._last_stats_signature = signature

        # 1. Update top row folder button (folder name directly under 'codebone')
        if hasattr(self, "folder_btn") and self.folder_btn is not None:
            if configured and self.config.project_path:
                folder_display = self.config.project_path.name
                self.folder_btn.setToolTip_("Click to reveal project in Finder")
            elif configured and repo_name != "None":
                folder_display = repo_name
                self.folder_btn.setToolTip_("Click to reveal project in Finder")
            else:
                folder_display = "Click to index local codebase"
                self.folder_btn.setToolTip_("Click to select and index project folder")
            self.folder_btn.setFolderName_(folder_display)

        # 2. Update status indicator dot
        if hasattr(self, "status_dot") and self.status_dot is not None:
            if not configured:
                self.status_dot.setColor_(NSColor.secondaryLabelColor())
            elif sniffing:
                self.status_dot.setColor_(NSColor.systemBlueColor())
            elif running:
                self.status_dot.setColor_(NSColor.systemGreenColor())
            else:
                self.status_dot.setColor_(NSColor.systemOrangeColor())

        # 3. Update bottom card row stats label
        if hasattr(self, "card_stats_label") and self.card_stats_label is not None:
            if configured:
                if sniffing and scan_progress:
                    curr = scan_progress.get("current", 0)
                    tot = scan_progress.get("total", 0)
                    cur_f = scan_progress.get("current_file", "")
                    short_f = Path(cur_f).name if cur_f else ""
                    if short_f:
                        stats_text = f"Indexing {short_f} ({curr}/{tot})"
                    else:
                        stats_text = f"Indexing ({curr}/{tot})  ·  {file_count} Nodes"
                else:
                    stats_text = f"{file_count} Nodes  ·  {connection_count} Connections"
            else:
                stats_text = "0 Nodes  ·  0 Connections"
            self.card_stats_label.setStringValue_(stats_text)

    def _apply_all_icons(self):
        """Applies native Apple SF Symbol vector icons across the entire menu hierarchy."""
        # Top-level menu items
        _set_symbol_icon(self.mcp_setup_item, "bolt.fill")
        _set_symbol_icon(self.rescan_item, "arrow.clockwise")
        _set_symbol_icon(self.select_project_item, "folder")
        _set_symbol_icon(self.recent_projects_menu, "clock.arrow.circlepath")
        _set_symbol_icon(self.settings_menu, "gearshape")
        _set_symbol_icon(self.feedback_item, "exclamationmark.bubble")
        _set_symbol_icon(self.about_item, "info.circle")
        _set_symbol_icon(self.quit_item, "power")

        # Settings submenu items
        _set_symbol_icon(self.brain_menu, "brain")
        _set_symbol_icon(self.adopt_scan_item, "link")
        _set_symbol_icon(self.copy_curl_item, "doc.on.clipboard")
        _set_symbol_icon(self.open_repo_item, "folder")
        _set_symbol_icon(self.view_logs_item, "doc.text")
        _set_symbol_icon(self.full_disk_access_item, "lock.shield")
        _set_symbol_icon(self.check_updates_item, "arrow.triangle.2.circlepath")
        _set_symbol_icon(self.export_scan_item, "square.and.arrow.up")
        _set_symbol_icon(self.import_scan_item, "square.and.arrow.down")
        _set_symbol_icon(self.reset_map_item, "trash")
        _set_symbol_icon(self.uninstall_item, "trash")

    def _update_ui_state(self):
        """Updates the menu bar icon and refreshes menu status."""
        self.icon = _get_icon(ICON_ACTIVE if self.config.is_configured else ICON_INACTIVE)
        if not self.icon:
            self.title = "codebone"
        if hasattr(self, "mcp_setup_item") and self.mcp_setup_item:
            if self.config.is_first_days():
                self.mcp_setup_item.title = "⚡ Connect AI Assistants (MCP)..."
            else:
                self.mcp_setup_item.title = "Connect AI Assistants (MCP)..."
        self._apply_all_icons()
        self._update_recent_projects_menu()
        self._update_brain_checks()
        self._update_modules_menu()
        self._push_stats()

    @staticmethod
    def _on_main(fn, *args):
        """AppKit objects (menus, labels, alerts) may only be touched on the main thread; the watcher, scans and
        the updater run on background threads and hop over with this."""
        AppHelper.callAfter(fn, *args)

    def _on_sniff_start(self):
        self._on_main(self._push_stats)

    def _on_sniff_end(self):
        self._on_main(self._push_stats)

    def _update_brain_checks(self):
        """Rebuilds the Model & Brain submenu with an active list of known models and providers."""
        provider = self.config.get("brain_provider", "builtin")
        current_model_path = self.config.get("model_path")

        if getattr(self.brain_menu, "_menu", None) is not None:
            self.brain_menu.clear()

        # 1. Active list of known local models
        for m in self.config.known_models:
            m_name = m.get("name", "Model")
            m_path = m.get("path")
            item = rumps.MenuItem(
                m_name,
                callback=lambda _, p=m_path, n=m_name: self.select_model_by_path(p, n)
            )
            _set_symbol_icon(item, "cpu")
            item.state = (provider == "builtin" and current_model_path == m_path)
            self.brain_menu.add(item)

        self.brain_menu.add(None)

        # 2. Remote / Cloud options
        self.brain_local_item = rumps.MenuItem(
            "Local URL (Ollama / LM Studio)...",
            callback=self.select_brain_local
        )
        _set_symbol_icon(self.brain_local_item, "network")
        self.brain_local_item.state = (provider == "local_url")
        self.brain_menu.add(self.brain_local_item)

        self.brain_cloud_item = rumps.MenuItem(
            "Cloud BYOK (OpenAI / Anthropic)...",
            callback=self.select_brain_cloud
        )
        _set_symbol_icon(self.brain_cloud_item, "cloud")
        self.brain_cloud_item.state = (provider == "cloud")
        self.brain_menu.add(self.brain_cloud_item)

        self.brain_menu.add(None)

        # 3. Actions
        self.add_model_item = rumps.MenuItem("Add Model File (.gguf)...", callback=self.add_model_file)
        _set_symbol_icon(self.add_model_item, "plus")
        self.brain_menu.add(self.add_model_item)

        self.deep_scan_item = rumps.MenuItem("Deep Scan Mode (7B)...", callback=self.run_deep_scan)
        _set_symbol_icon(self.deep_scan_item, "bolt")
        self.brain_menu.add(self.deep_scan_item)

    def select_model_by_path(self, path: str, name: str):
        self.config.select_model(path)
        self.config.set("brain_provider", "builtin")
        self.service.reload_provider()
        self._update_ui_state()
        rumps.notification("codebone", "Model switched", f"Active model: {name}")

    def _update_recent_projects_menu(self):
        """Rebuilds the Recent Projects / History submenu from saved config and scan snapshots."""
        if getattr(self.recent_projects_menu, "_menu", None) is not None:
            self.recent_projects_menu.clear()

        # Gather recent projects from config MRU and scan registry
        seen_paths = set()
        recent_list = []

        # 1. From config.recent_projects
        for p_str in self.config.recent_projects:
            if not p_str:
                continue
            p = Path(p_str)
            if p.exists() and str(p) not in seen_paths:
                seen_paths.add(str(p))
                recent_list.append(p)

        # 2. From saved scan snapshots (scans_registry.json)
        try:
            for s in self.service.scans.list_scans():
                p_str = s.get("project_path")
                if p_str:
                    p = Path(p_str)
                    if p.exists() and str(p) not in seen_paths:
                        seen_paths.add(str(p))
                        recent_list.append(p)
        except Exception:
            pass

        # Also ensure current project is in list if configured
        current_proj = self.config.project_path
        if current_proj and current_proj.exists() and str(current_proj) not in seen_paths:
            self.config.add_recent_project(str(current_proj))
            recent_list.insert(0, current_proj)

        if not recent_list:
            empty_item = rumps.MenuItem("No Recent Projects", callback=None)
            self.recent_projects_menu.add(empty_item)
            return

        for p in recent_list[:10]:
            name = p.name or str(p)
            try:
                rel_to_home = f"~/{p.relative_to(Path.home())}"
            except Exception:
                rel_to_home = str(p)

            item_label = f"{name}  ({rel_to_home})"
            item = rumps.MenuItem(
                item_label,
                callback=lambda _, target_path=p: self.open_project_path(target_path),
            )
            _set_symbol_icon(item, "folder")
            if current_proj and current_proj.resolve() == p.resolve():
                item.state = True
            self.recent_projects_menu.add(item)

        self.recent_projects_menu.add(None)
        clear_item = rumps.MenuItem("Clear Recent Projects", callback=self.clear_recent_projects)
        _set_symbol_icon(clear_item, "trash")
        self.recent_projects_menu.add(clear_item)

    # ── model modules ────────────────────────────────────────────────────
    def _update_modules_menu(self):
        from . import modules

        if getattr(self.modules_menu, "_menu", None) is not None:
            self.modules_menu.clear()
        library = modules.list_modules(self.config)
        selected = modules.get_module(self.config, self.config.get("module_selected"))
        active = set(modules.enabled_apps(self.config))

        for m in library:  # which model
            item = rumps.MenuItem(m["name"], callback=lambda _, mid=m["id"]: self.pick_module(mid))
            item.state = bool(selected and selected["id"] == m["id"])
            self.modules_menu.add(item)
        if library:
            self.modules_menu.add(None)
            for app_id, (label, fmt) in modules.APPS.items():  # which apps use it
                needs = "" if (selected is None or modules.supports(selected, app_id)) else f"  (needs {modules.FORMAT_NAMES[fmt]} URL)"
                item = rumps.MenuItem(f"Use for {label}{needs}", callback=lambda _, a=app_id: self.toggle_module_app(a))
                item.state = app_id in active
                self.modules_menu.add(item)
            copy_menu = rumps.MenuItem("Copy for Other Apps")
            for what, fn in (("Anthropic-format base URL", lambda: (selected or {}).get("anthropic_url")),
                             ("OpenAI-format base URL", lambda: (selected or {}).get("openai_url")),
                             ("Model ID", lambda: (selected or {}).get("model")),
                             ("API key", lambda: modules.Keychain().get(selected["id"]) if selected else None)):
                copy_menu.add(rumps.MenuItem(what, callback=lambda _, w=what, f=fn: self.copy_module_value(w, f)))
            self.modules_menu.add(copy_menu)
            self.modules_menu.add(None)
        self.modules_menu.add(rumps.MenuItem("Add Module...", callback=self.add_module_dialog))
        if library:
            self.modules_menu.add(rumps.MenuItem("Test Connection", callback=self.test_selected_module))
            remove_menu = rumps.MenuItem("Remove Module")
            for m in library:
                remove_menu.add(rumps.MenuItem(m["name"], callback=lambda _, mid=m["id"], n=m["name"]: self.remove_module_dialog(mid, n)))
            self.modules_menu.add(remove_menu)

    def toggle_module_app(self, app_id: str):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        label = modules.APPS[app_id][0]
        turning_on = app_id not in modules.enabled_apps(self.config)
        try:
            module = modules.set_app_enabled(self.config, app_id, turning_on)
        except modules.SettingsUnreadable as exc:
            rumps.alert("Modules", f"{label}'s settings file could not be read, so nothing was changed:\n{exc}")
            return
        except ValueError as exc:
            rumps.alert("Modules", str(exc))
            return
        if module:
            rumps.notification("codebone", f"{label} now uses {module['name']}", "New sessions pick this up; running ones keep their model.")
        else:
            rumps.notification("codebone", f"{label} is back on its normal model", "New sessions use your usual setup again.")
        self._update_modules_menu()

    def copy_module_value(self, what: str, getter):
        value = getter()
        if not value:
            rumps.alert("Modules", f"This module has no {what}.")
            return
        copy_to_clipboard(value)
        rumps.notification("codebone", f"{what} copied", "Paste it into the other app's model settings.")

    def pick_module(self, module_id: str):
        from . import modules

        try:
            modules.select_module(self.config, module_id)
        except (ValueError, modules.SettingsUnreadable) as exc:
            rumps.alert("Modules", str(exc))
        self._update_modules_menu()

    def add_module_dialog(self, _):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        preset = modules.PRESETS[0]
        choice = rumps.alert(
            title="Add Module",
            message=(f"A module is a model API your coding apps can use instead of their default.\n\n"
                     f"Preset: {preset['name']}\nModel: {preset['model']}\n\n"
                     "Custom needs a base URL in Anthropic format (for Claude Code) and/or OpenAI format (for opencode)."),
            ok=preset["name"], cancel="Cancel", other="Custom...",
        )
        if choice == 0:
            return
        if choice == 1:
            name, model = preset["name"], preset["model"]
            anthropic_url, openai_url = preset["anthropic_url"], preset["openai_url"]
        else:
            fields = []
            for label, default in (("Name (shown in the menu)", ""), ("Model ID", ""),
                                   ("Anthropic-format base URL (optional, https://...)", ""),
                                   ("OpenAI-format base URL (optional, https://...)", "")):
                resp = rumps.Window(message=label, title="Add Module", default_text=default, ok="Next", cancel="Cancel",
                                    dimensions=(360, 24)).run()
                if not resp.clicked:
                    return
                fields.append(resp.text.strip())
            name, model, anthropic_url, openai_url = fields
        resp = rumps.Window(message=f"API key for {name} (stored in your macOS Keychain)",
                            title="Add Module", default_text="", ok="Add", cancel="Cancel", dimensions=(360, 24),
                            secure=True).run()
        if not resp.clicked:
            return
        key = resp.text.strip()
        try:
            module = modules.add_module(self.config, name, model, key, anthropic_url, openai_url)
            self.config.set("module_selected", module["id"])
        except (ValueError, RuntimeError) as exc:
            rumps.alert("Add Module", str(exc))
            return
        self._update_modules_menu()
        self._check_module(module, key)

    def _check_module(self, module: dict, key: str):
        from . import modules

        def _run():
            for fmt in ("anthropic", "openai"):
                url = modules._url(module, fmt)
                if not url:
                    continue
                ok, msg = modules.test_connection(url, module["model"], key, fmt=fmt)
                rumps.notification("codebone", f"{module['name']} ({fmt} format): " + ("works" if ok else "failed"), msg)

        threading.Thread(target=_run, daemon=True, name="codebone-module-test").start()

    def test_selected_module(self, _):
        from . import modules

        module = modules.get_module(self.config, self.config.get("module_selected"))
        key = modules.Keychain().get(module["id"]) if module else None
        if not module or not key:
            rumps.alert("Modules", "Select a module with a stored key first.")
            return
        self._check_module(module, key)

    def remove_module_dialog(self, module_id: str, name: str):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if rumps.alert("Remove Module", f"Remove {name}, switch its apps back and delete its API key?", ok="Remove", cancel="Cancel") != 1:
            return
        try:
            modules.remove_module(self.config, module_id)
        except modules.SettingsUnreadable as exc:
            rumps.alert("Modules", str(exc))
        self._update_modules_menu()

    def clear_recent_projects(self, _):
        """Clears the recent projects list and refreshes the submenu."""
        self.config.clear_recent_projects()
        self._update_recent_projects_menu()
        rumps.notification("codebone", "Recent Projects Cleared", "The project history has been reset.")

    def choose_project(self, _):
        path = choose_folder("Select Project Folder to Sniff")
        if not path:
            return
        self.open_project_path(Path(path))

    def open_project_path(self, p: Path):
        """Activates and switches to the specified project folder."""
        if not p or not p.exists():
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("Project Not Found", f"The folder '{p}' no longer exists on disk.")
            self.config.remove_recent_project(str(p))
            self._update_recent_projects_menu()
            return

        current_proj = self.config.project_path
        if current_proj and current_proj.resolve() == p.resolve() and self.service.watching:
            rumps.notification("codebone", "Already Active", f"'{p.name}' is already the active project.")
            return

        # Check macOS disk permissions / TCC
        has_access, reason = check_folder_access(p)
        if not has_access:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            res = rumps.alert(
                title="Disk Access Restricted",
                message=(
                    f"codebone cannot read files in '{p.name}' ({reason}).\n\n"
                    "macOS requires permissions to read folders like Desktop, Documents, Downloads, or external volumes.\n\n"
                    "How to enable:\n"
                    "1. Find 'codebone' in Full Disk Access and toggle it ON.\n"
                    "2. If not listed, drag codebone.app from Finder into the list.\n\n"
                    "Click 'Open Settings & Reveal' to open both windows automatically."
                ),
                ok="Open Settings & Reveal",
                cancel="Cancel",
            )
            if res == 1:
                open_full_disk_access_settings()
                reveal_codebone_in_finder()
            return

        self.config.add_recent_project(str(p))
        self.config.set("project_path", str(p))
        self.service.start(auto_scan=False)  # aborts a running scan, drops the old project's rows, watches the new folder
        self._update_ui_state()

        # Step 1: Fast initial assessment (Baseline Overview)
        baseline = self.service.inspect_baseline(p)
        total = baseline["total_files"]
        to_index = baseline["files_to_index"]
        eta = baseline["estimated_time_str"]
        langs = baseline["languages_summary"]

        if total == 0:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("codebone", f"No supported code files found in folder '{p.name}'.")
            return

        # Check if an existing scan matches this folder
        matching = self.service.scans.find_matching_scan(p)
        if matching:
            rumps.notification(
                "codebone — Previous Scan Found",
                f"{matching.get('project_name')} recognized",
                "Reconciling project structure with AI...",
            )

            def _run_matched():
                try:
                    rep = self.service.adopt_scan(matching["id"])
                    reused = rep.get("reused_count", 0)
                    renamed = rep.get("renamed_count", 0)
                    modified = rep.get("modified_count", 0)
                    added = rep.get("added_count", 0)
                    conn_count = len(self.service.storage.graph_edges())
                    rumps.notification(
                        "codebone — Baseline Reused",
                        f"{matching.get('project_name')}",
                        f"{reused} files reused, {renamed} renamed, {conn_count} connections mapped.",
                    )
                except Exception as exc:
                    logger.warning("Matching scan adoption failed, falling back to rescan: %s", exc)
                    self.service.rescan_all(wait=True)
                finally:
                    self._on_main(self._update_ui_state)

            threading.Thread(target=_run_matched, daemon=True, name="codebone-matched-adopt").start()
        else:
            # Baseline Overview Notification
            rumps.notification(
                f"codebone — Indexing Started",
                f"{p.name} ({total} files, {langs})",
                f"Analyzing semantic structures and building knowledge graph...",
            )

            def _run_initial():
                import time
                t0 = time.time()
                try:
                    def _on_prog(cur, tot, f):
                        self._on_main(self._push_stats)

                    total_scanned, sniffed, skipped = self.service.rescan_all(on_progress=_on_prog, wait=True)
                    dur = max(1, round(time.time() - t0))
                    conn_count = len(self.service.storage.graph_edges())
                    rumps.notification(
                        f"codebone — Indexing Complete",
                        f"{p.name} ready ({total_scanned} files)",
                        f"Mapped {total_scanned} nodes & {conn_count} connections in {dur}s. Live watching active.",
                    )
                except Exception as exc:
                    logger.exception("Initial baseline scan failed")
                    rumps.notification("codebone — Scan Error", str(exc), "")
                finally:
                    self._on_main(self._update_ui_state)

            threading.Thread(target=_run_initial, daemon=True, name="codebone-initial-scan").start()

    def choose_adopt_scan(self, _):
        if not self.config.is_configured:
            path = choose_folder("Select Target Project Folder to Reconcile")
            if not path:
                return
            self.config.set("project_path", path)
            self.service.start(auto_scan=False)
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
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
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
                "codebone",
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
                    "codebone",
                    "Scan Adoption Complete!",
                    f"{reused} files reused, {renamed} renamed, {modified} modified, {added} added. Semantic Graph synchronized!",
                )
                self._on_main(self._update_ui_state)
            except Exception as exc:
                logger.exception("Error during scan adoption: %s", exc)
                rumps.notification("codebone", "Adoption Failed", str(exc))

        threading.Thread(target=_run_adopt, daemon=True, name="codebone-user-adopt").start()

    def export_scan_snapshot(self, _):
        if not self.config.is_configured:
            rumps.notification("codebone", "Not Configured", "Configure a project first to export its scan.")
            return
        dest_folder = choose_folder("Select Destination Folder for Scan Snapshot")
        if not dest_folder:
            return
        p_name = self.config.project_path.name
        dest_file = Path(dest_folder) / f"{p_name}_scan.sqlite3"
        try:
            self.service.storage.snapshot_to(dest_file)
            rumps.notification("codebone", "Scan Exported", f"Saved to {dest_file.name}")
        except Exception as exc:
            rumps.notification("codebone", "Export Failed", str(exc))

    def import_scan_file(self, _):
        f_path = choose_file("Select Scan Snapshot File (.sqlite3)", ["sqlite3", "db", "sqlite"])
        if not f_path:
            return
        try:
            meta = self.service.scans.import_scan(Path(f_path))
            rumps.notification("codebone", "Scan Imported", f"Imported '{meta['project_name']}' ({meta['file_count']} files).")
        except Exception as exc:
            rumps.notification("codebone", "Import Failed", str(exc))

    def open_mcp_setup(self, _):
        """Opens the GitHub MCP setup instructions section and re-patches MCP configs."""
        try:
            from .server import patch_mcp_configs
            server_port = getattr(getattr(self, "server", None), "port", None) or self.config.get("active_port") or self.config.get("server_port", 8053)
            patch_mcp_configs(server_port)
        except Exception as exc:
            logger.warning("Could not patch MCP configs during open_mcp_setup: %s", exc)
        from AppKit import NSURL, NSWorkspace
        url = NSURL.URLWithString_("https://github.com/palusc/codebone#mcp-setup")
        if url:
            NSWorkspace.sharedWorkspace().openURL_(url)

    def view_live_graph(self, _):
        port = getattr(getattr(self, "server", None), "port", None) or self.config.get("active_port") or self.config.get("server_port", 8053)
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

    def open_feedback_dialog(self, _):
        """Displays in-app feedback & bug report dialog with automatic diagnostic bundling."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window = rumps.Window(
            message=(
                "Describe your bug, feedback, or suggestion:\n\n"
                "• System diagnostics and recent logs are automatically bundled\n"
                "• Sensitive tokens (sk-..., bearer) are safely redacted\n"
                "• Saved locally to ~/Library/Application Support/codebone/feedback.jsonl"
            ),
            title="codebone Feedback & Bug Report",
            default_text="",
            ok="Submit Report",
            cancel="Cancel",
            dimensions=(380, 110),
        )
        resp = window.run()
        if resp.clicked and resp.text.strip():
            user_text = resp.text.strip()
            extra_diag = {
                "project": str(self.config.project_path) if self.config.project_path else "none",
                "brain_provider": self.config.get("brain_provider"),
                "file_count": self.service.storage.file_count() if self.config.is_configured else 0,
                "connection_count": len(self.service.storage.graph_edges()) if self.config.is_configured else 0,
            }
            first_line = user_text.splitlines()[0][:60]
            f_type = "bug" if any(w in user_text.lower() for w in ("bug", "crash", "error", "fail", "broken", "issue")) else "feedback"

            res = record_feedback(
                feedback_type=f_type,
                title=first_line,
                description=user_text,
                include_logs=True,
                extra_diagnostics=extra_diag,
            )

            prompt = rumps.alert(
                title="Feedback Recorded Locally!",
                message=(
                    "Your report has been saved to:\n"
                    "~/Library/Application Support/codebone/feedback.jsonl\n\n"
                    "Would you like to open a pre-filled GitHub Issue in your browser to submit it directly?"
                ),
                ok="Open in GitHub",
                cancel="Done",
            )
            if prompt == 1 and res.get("github_url"):
                subprocess.Popen(["open", res["github_url"]])

    def confirm_uninstall(self, _):
        """Complete removal from inside the app: shows exactly what will go, then removes it (src/uninstall.py)."""
        from . import uninstall

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        try:
            targets = uninstall.collect_targets()
        except Exception as exc:
            logger.exception("Could not work out what to uninstall")
            rumps.alert("Uninstall codebone", f"Could not inspect this installation:\n{exc}")
            return

        def _size(n):
            return uninstall._fmt_size(n) if n else ""

        lines = []
        for t_ in targets:
            if t_.kind == "process":
                continue
            size = _size(t_.size_bytes)
            lines.append(f"\u2022 {t_.label}" + (f" ({size})" if size else ""))
        shown = lines[:14] + ([f"\u2022 ... and {len(lines) - 14} more items"] if len(lines) > 14 else [])
        message = (
            "This removes codebone completely from your Mac:\n\n" + "\n".join(shown) +
            "\n\nYour project folders are not touched. codebone quits when it is done."
        )
        if rumps.alert(title="Uninstall codebone", message=message, ok="Uninstall", cancel="Cancel") != 1:
            return

        self._stats_timer.stop()  # nothing of ours may write to the files that are about to disappear
        threading.Thread(target=self._run_uninstall, daemon=True, name="codebone-uninstall").start()

    def _run_uninstall(self):
        from . import uninstall

        report_text = ""
        try:
            self.server.stop()
            self.service.close()
            report = uninstall.run_uninstall()
            report_text = report.format()
        except Exception as exc:
            logger.exception("Uninstall failed")
            report_text = f"Uninstall did not finish: {exc}\n\nYou can also run:  python3 -m src.uninstall"

        def _done():
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert(title="Uninstall codebone", message=report_text[:1800], ok="OK")
            rumps.quit_application()

        self._on_main(_done)

    def open_disk_access_settings(self, _):
        """Opens Full Disk Access in macOS System Settings and provides a guided dialog with 1-click Finder reveal."""
        try:
            open_full_disk_access_settings()
        except Exception as exc:
            logger.error("Failed to open Full Disk Access settings: %s", exc)

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        res = rumps.alert(
            title="Enable Full Disk Access",
            message=(
                "codebone requires Full Disk Access to scan projects located in Desktop, Documents, "
                "Downloads, or external volumes.\n\n"
                "How to enable:\n"
                "1. Look for 'codebone' in the Full Disk Access list in System Settings and toggle it ON (🔵).\n\n"
                "2. If 'codebone' is not listed:\n"
                "   Click 'Reveal in Finder' below, then drag codebone.app directly into the System Settings window.\n\n"
                "3. macOS will prompt to restart codebone to apply permissions."
            ),
            ok="Reveal in Finder",
            cancel="Done",
        )
        if res == 1:
            reveal_codebone_in_finder()

    def copy_curl(self, _):
        cmd = self.server.curl_command()
        copy_to_clipboard(cmd)
        rumps.notification("codebone", "Copied to clipboard", cmd)

    def select_brain_builtin(self, _):
        self.config.set("brain_provider", "builtin")
        self._update_brain_checks()
        self.service.reload_provider()
        rumps.notification("codebone", "Model switched", "Built-in Qwen 0.5B (Metal) active.")

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
            rumps.notification("codebone", "Model switched", f"Local URL active: {resp.text.strip()}")

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
            rumps.notification("codebone", "Model switched", f"Cloud BYOK ({vendor.upper()}) active.")

    def add_model_file(self, _):
        path = choose_file("Select .gguf Model File", ["gguf"])
        if path:
            entry = self.config.add_model(path)
            self.config.select_model(path)
            self.config.set("brain_provider", "builtin")
            self._update_brain_checks()
            self.service.reload_provider()
            rumps.notification("codebone", "Model added", f"Loaded model: {entry['name']}")

    def run_deep_scan(self, _):
        if not self.config.is_configured:
            rumps.alert("Deep Scan Mode", "Please select a project folder first.")
            return

        model_path = self.config.get("deep_scan_model_path")
        if not model_path or not Path(model_path).exists():
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
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
            rumps.notification("codebone", "Deep Scan Started", f"Re-analyzing project with {Path(model_path).name}...")
            try:
                total, sniffed, _ = self.service.run_deep_scan()
                rumps.notification("codebone", "Deep Scan Complete", f"{sniffed}/{total} files re-analyzed.")
            except Exception as exc:
                logger.exception("Deep scan failed")
                rumps.notification("codebone", "Deep Scan Failed", str(exc))
            finally:
                self._on_main(self._update_ui_state)

        threading.Thread(target=_run, daemon=True, name="codebone-deep-scan").start()

    def reset_map(self, _):
        self.service.reset_map()
        self._update_ui_state()
        rumps.notification("codebone", "Map reset", "Semantic knowledge graph cleared.")
        if self.config.is_configured:
            threading.Thread(target=self.service.rescan_all, daemon=True).start()

    def quit_app(self, _):
        self._stats_timer.stop()
        self.service.close()  # stops the watcher and unloads the model
        self.server.stop()
        rumps.quit_application()


_instance_lock = None


_REOPEN_DISTRIBUTED_NOTIFICATION = "com.codebone.app.reopen"


def _acquire_single_instance() -> bool:
    """Two instances would index into the same database and fight over the port; the second one just exits."""
    global _instance_lock
    from .config import CONFIG_DIR

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _instance_lock = open(CONFIG_DIR / "app.lock", "w")
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main():
    if not _acquire_single_instance():
        # A relaunch (e.g. double-clicking the app again) would otherwise just exit silently, leaving
        # the user thinking nothing happened. Nudge the already-running instance to open its menu instead.
        try:
            from Foundation import NSDistributedNotificationCenter
            NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_(
                _REOPEN_DISTRIBUTED_NOTIFICATION, None, None
            )
        except Exception:
            pass
        try:
            rumps.notification("codebone", "Already running", "codebone is already active — check your menu bar.")
        except Exception:
            pass
        print("codebone is already running.", file=sys.stderr)
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    app = CodeBoneApp()

    def _open_menu():
        try:
            app._nsapp.nsstatusitem.button().performClick_(None)
        except Exception:
            pass

    # Menu-bar-only app: clicking the .app while it runs would otherwise do nothing visible.
    def _reopen(self, sender, has_windows):
        _open_menu()
        return False

    rumps.rumps.NSApp.applicationShouldHandleReopen_hasVisibleWindows_ = _reopen

    try:
        from Foundation import NSDistributedNotificationCenter
        NSDistributedNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            _REOPEN_DISTRIBUTED_NOTIFICATION, None, None, lambda note: _open_menu()
        )
    except Exception:
        pass

    app.run()


# Backwards compatibility alias
PugApp = CodeBoneApp


if __name__ == "__main__":
    main()
