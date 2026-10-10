"""The 'Bone' UI — codebone macOS menu bar app."""
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import objc
import rumps
from PyObjCTools import AppHelper
from Foundation import NSRunLoop, NSDate
from AppKit import (
    NSAlert,
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
    NSViewWidthSizable,
    NSViewMinXMargin,
)

from .config import Config
from .feedback import record_feedback
from .logging_setup import configure_logging
from .permissions import (
    check_folder_access,
    has_full_disk_access,
    is_protected_user_folder,
    open_full_disk_access_settings,
    reveal_codebone_in_finder,
)
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


def _fmt_count(n: int) -> str:
    """1420 -> "1.420": the HUD shows counts the way the roadmap writes them (German thousands dot)."""
    return f"{int(n):,}".replace(",", ".")


def _set_symbol_icon(menu_item: Optional[rumps.MenuItem], symbol_name: str, size: float = 15.0):
    """Sets a native Apple SF Symbol vector icon on an NSMenuItem with standard point size."""
    if menu_item is None:
        return
    if getattr(menu_item, "_choice_view", None) is not None:
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


def _choose_folders(title: str, multi: bool = False) -> list[str]:
    """Native macOS open folder panel. multi=True lets one pick serve several project folders at once;
    the runloop draining and policy juggling around it are what keeps the menu from staying on screen."""
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
        panel.setAllowsMultipleSelection_(multi)
        panel.setResolvesAliases_(True)
        panel.setCanCreateDirectories_(True)
        panel.center()

        response = panel.runModal()
        if response == 1:  # NSModalResponseOK
            return [str(url.path()) for url in panel.URLs()]
        return []
    finally:
        try:
            panel.orderOut_(None)
        except Exception:
            pass
        try:
            app.setActivationPolicy_(prev_policy)
        except Exception:
            pass


def choose_folder(title: str) -> Optional[str]:
    """Single-folder panel: the first (and only) selection, or None."""
    picked = _choose_folders(title, multi=False)
    return picked[0] if picked else None


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

class NonClickableInfoView(NSView):
    """Non-clickable view for informative menu rows, rendering bold white text with no click capture."""

    def hitTest_(self, point):
        return None

    def viewWillDraw(self):
        objc.super(NonClickableInfoView, self).viewWillDraw()
        if self.superview():
            new_w = self.superview().frame().size.width
            if new_w > 0 and abs(new_w - self.frame().size.width) > 1:
                self.setFrameSize_(NSSize(new_w, self.frame().size.height))


class FullWidthMenuView(NSView):
    """Container view for menu items that automatically stretches to the full width of the parent menu."""

    def viewWillDraw(self):
        objc.super(FullWidthMenuView, self).viewWillDraw()
        if self.superview():
            new_w = self.superview().frame().size.width
            if new_w > 0 and abs(new_w - self.frame().size.width) > 1:
                self.setFrameSize_(NSSize(new_w, self.frame().size.height))


def make_info_item(title: str, bold: bool = True, size: float = 11.5, height: float = 20.0, width: float = 216.0) -> rumps.MenuItem:
    """Creates a native non-clickable menu item displaying crisp bold white text."""
    item = rumps.MenuItem(title, callback=None)
    view = NonClickableInfoView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(width, height)))
    view.setAutoresizingMask_(NSViewWidthSizable)
    label = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(14, 2), NSSize(width - 24, height - 4)))
    label.setAutoresizingMask_(NSViewWidthSizable)
    label.setStringValue_(title)
    if bold:
        label.setFont_(NSFont.boldSystemFontOfSize_(size))
    else:
        label.setFont_(NSFont.systemFontOfSize_(size))
    label.setTextColor_(NSColor.whiteColor())
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    view.addSubview_(label)
    item._info_label = label
    try:
        item._menuitem.setView_(view)
        item._menuitem.setToolTip_(title)
    except Exception as exc:
        logger.debug("Failed to set info view on menu item: %s", exc)
    return item


class ChoiceRowView(NSView):
    """Selectable menu row (checkmark + label) that keeps the menu open when clicked, with a native-style hover highlight."""

    def initWithFrame_(self, frame):
        self = objc.super(ChoiceRowView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._on_click = None
        self._hovered = False
        tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect,
            self,
            None,
        )
        self.addTrackingArea_(tracking)
        return self

    def viewWillDraw(self):
        objc.super(ChoiceRowView, self).viewWillDraw()
        if self.superview():
            new_w = self.superview().frame().size.width
            if new_w > 0 and abs(new_w - self.frame().size.width) > 1:
                self.setFrameSize_(NSSize(new_w, self.frame().size.height))

    def hitTest_(self, point):
        res = objc.super(ChoiceRowView, self).hitTest_(point)
        return self if res is not None else None

    def mouseEntered_(self, event):
        self._hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._hovered = False
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if self._on_click and self.mouse_inRect_(point, self.bounds()):
            # Deferred: the callback rebuilds the menu, which must not happen inside this view's own event handler.
            AppHelper.callAfter(self._on_click)

    def drawRect_(self, rect):
        if self._hovered:
            NSColor.labelColor().colorWithAlphaComponent_(0.12).setFill()
            inset = NSRect(NSPoint(5, 1), NSSize(max(self.bounds().size.width - 10, 0), self.bounds().size.height - 2))
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 5.0, 5.0).fill()


def make_choice_item(title: str, checked: Optional[bool], on_click, tooltip: str = "", height: float = 22.0, width: float = 216.0, icon: str = "") -> rumps.MenuItem:
    """Menu row that can be clicked repeatedly without the menu closing.

    checked=True/False shows a selection checkmark column; checked=None makes it a plain action row,
    optionally with an SF Symbol `icon` in that column."""
    item = rumps.MenuItem(title, callback=None)
    view = ChoiceRowView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(width, height)))
    view.setAutoresizingMask_(NSViewWidthSizable)
    view._on_click = on_click
    glyph = None
    if icon:
        try:
            glyph = NSImage.imageWithSystemSymbolName_accessibilityDescription_(icon, None)
        except Exception:
            glyph = None
    if glyph is not None and checked is None:
        glyph_view = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(9, (height - 15) / 2), NSSize(15, 15)))
        glyph_view.setImage_(glyph)
        try:
            glyph_view.setContentTintColor_(NSColor.labelColor())
        except Exception:
            pass
        view.addSubview_(glyph_view)
    else:
        check = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(10, 2), NSSize(16, height - 4)))
        check.setStringValue_("✓" if checked else "")
        check.setFont_(NSFont.systemFontOfSize_(13))
        check.setTextColor_(NSColor.labelColor())
        check.setBezeled_(False)
        check.setDrawsBackground_(False)
        check.setEditable_(False)
        check.setSelectable_(False)
        view.addSubview_(check)
    label = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(30, 2), NSSize(width - 40, height - 4)))
    label.setAutoresizingMask_(NSViewWidthSizable)
    label.setStringValue_(title)
    label.setFont_(NSFont.systemFontOfSize_(13))
    label.setTextColor_(NSColor.labelColor())
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    view.addSubview_(label)
    view._label = label
    item._choice_view = view
    try:
        item._menuitem.setView_(view)
        item._menuitem.setToolTip_(tooltip or title)
    except Exception as exc:
        logger.debug("Failed to set choice view on menu item: %s", exc)
    return item


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


class ModulesSwitchDelegate(NSObject):
    """Action delegate for the native switch on the coding-agent row (Tailscale-style: the switch itself
    is the on/off control, no need to open a submenu to flip it)."""

    def initWithApp_(self, app):
        self = objc.super(ModulesSwitchDelegate, self).init()
        if self is None:
            return None
        self.app = app
        return self

    @objc.IBAction
    def switchToggled_(self, sender):
        if not self.app:
            return
        self.app.set_modules_master(sender.state() == NSControlStateValueOn)


class MapSwitchDelegate(NSObject):
    """Action delegate for the native switch on the Map Agent row: toggle between custom model and built-in model."""

    def initWithApp_(self, app):
        self = objc.super(MapSwitchDelegate, self).init()
        if self is None:
            return None
        self.app = app
        return self

    @objc.IBAction
    def switchToggled_(self, sender):
        if not self.app:
            return
        self.app.set_map_master(sender.state() == NSControlStateValueOn)


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

        # Custom Header View (Title "codebone", Status Dot LED, Divider, Knowledge Graph Card)
        (
            self.header_view,
            self.header_action_delegate,
            self.status_dot,
            self.card_stats_label,
            self.header_title_lbl,
        ) = self._build_header_view()
        self.folder_btn = None
        self.header_item = rumps.MenuItem("codebone", callback=None)
        try:
            self.header_item._menuitem.setView_(self.header_view)
        except Exception as exc:
            logger.warning("Could not set custom header view: %s", exc)

        self._last_completed_scans: dict[str, float] = {}

        self.pause_scan_item = rumps.MenuItem("Pause Scanning", callback=self.toggle_pause_indexing)
        _set_symbol_icon(self.pause_scan_item, "pause.fill")
        self.cancel_scan_item = rumps.MenuItem("Cancel Scan", callback=self.cancel_indexing)
        _set_symbol_icon(self.cancel_scan_item, "xmark.circle")
        try:
            self.pause_scan_item._menuitem.setHidden_(True)
            self.cancel_scan_item._menuitem.setHidden_(True)
        except Exception:
            pass

        # The three most recently scanned projects are direct one-click rows in the main menu. Empty
        # placeholders are hidden so the layout does not gain another unnecessary submenu.
        self.quick_access_paths: list[Path] = []
        self.quick_access_items: list[rumps.MenuItem] = []
        for _index in range(3):
            item = rumps.MenuItem("Recent Project")
            _set_symbol_icon(item, "clock.arrow.circlepath")
            self.quick_access_items.append(item)

        self.projects_menu = rumps.MenuItem("Projects")
        _set_symbol_icon(self.projects_menu, "folder")

        self.mcp_setup_item = make_choice_item("Connect Coding Agent (MCP)", checked=None, on_click=self.open_mcp_setup, icon="bolt.fill")

        # Model modules: API endpoints Claude Code can be routed through (for coding, not for indexing).
        # The on/off switch lives on its own row (self.modules_switch_item); this submenu holds the
        # rest of the configuration (module list, per-app routing, quick links, recovery).
        (
            self.modules_switch_row,
            self.modules_switch_delegate,
            self.modules_switch,
        ) = self._build_modules_switch_row()
        self.modules_switch_item = rumps.MenuItem("Use Custom Model", callback=None)
        try:
            self.modules_switch_item._menuitem.setView_(self.modules_switch_row)
        except Exception as exc:
            logger.warning("Could not set custom coding-agent switch view: %s", exc)

        self.modules_menu = rumps.MenuItem("Coding Agent")
        _set_symbol_icon(self.modules_menu, "square.stack.3d.up")

        # Map agent switch for custom models vs built-in model
        (
            self.map_switch_row,
            self.map_switch_delegate,
            self.map_switch,
        ) = self._build_map_switch_row()
        self.map_switch_item = rumps.MenuItem("Use Custom Model", callback=None)
        try:
            self.map_switch_item._menuitem.setView_(self.map_switch_row)
        except Exception as exc:
            logger.warning("Could not set map-agent switch view: %s", exc)

        # The map agent analyses files, builds TLDRs and powers the knowledge map. It is deliberately
        # separate from the optional model routed into the user's coding agent.
        self.brain_menu = rumps.MenuItem("Map Agent")
        _set_symbol_icon(self.brain_menu, "brain")

        # Models & API key management: centralized hub for all models and keys
        self.models_menu = rumps.MenuItem("Models...")
        _set_symbol_icon(self.models_menu, "cpu")
        self.api_keys_menu = self.models_menu

        # Settings Items
        self.adopt_scan_item = rumps.MenuItem("Merge with Previous Scan...", callback=self.choose_adopt_scan)
        _set_symbol_icon(self.adopt_scan_item, "arrow.triangle.merge")

        self.copy_curl_item = make_choice_item("Copy AI Context (curl)", checked=None, on_click=self.copy_curl, icon="doc.on.clipboard")

        self.rescan_item = rumps.MenuItem("Scan Project Now", callback=self.rescan_workspace)
        _set_symbol_icon(self.rescan_item, "arrow.clockwise")

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

        self.scan_data_menu = rumps.MenuItem("Scan Data")
        _set_symbol_icon(self.scan_data_menu, "externaldrive")
        self.scan_data_menu.update([
            self.adopt_scan_item,
            self.copy_curl_item,
            None,
            self.export_scan_item,
            self.import_scan_item,
            None,
            self.reset_map_item,
        ])

        self.open_map_item = rumps.MenuItem("Open Knowledge Map...", callback=self.view_live_graph)
        _set_symbol_icon(self.open_map_item, "point.3.connected.trianglepath.dotted")

        self.documentation_item = rumps.MenuItem(
            "Documentation...",
            callback=lambda _: self.open_url("https://github.com/palusc/codebone"),
        )
        _set_symbol_icon(self.documentation_item, "book")

        self.feedback_item = rumps.MenuItem("Feedback & Bug Report...", callback=self.open_feedback_dialog)
        _set_symbol_icon(self.feedback_item, "exclamationmark.bubble")

        self.check_updates_item = rumps.MenuItem("Check for Updates...", callback=self.check_updates)
        _set_symbol_icon(self.check_updates_item, "arrow.triangle.2.circlepath")

        self.about_item = rumps.MenuItem("About codebone...", callback=self.show_about)
        _set_symbol_icon(self.about_item, "info.circle")

        self.uninstall_item = rumps.MenuItem("Uninstall codebone...", callback=self.confirm_uninstall)
        _set_symbol_icon(self.uninstall_item, "trash")

        self.help_menu = rumps.MenuItem("Help & Quick Links")
        _set_symbol_icon(self.help_menu, "questionmark.circle")
        self.help_menu.update([
            self.mcp_setup_item,
            self.open_map_item,
            self.documentation_item,
            None,
            self.view_logs_item,
            self.full_disk_access_item,
            None,
            self.feedback_item,
            self.check_updates_item,
            self.about_item,
            None,
            self.uninstall_item,
        ])

        self.quit_item = rumps.MenuItem("Quit codebone", callback=self.quit_app)
        _set_symbol_icon(self.quit_item, "power")

        # Flat, 1-level-deep menu hierarchy: live status → scan controls → projects → agents → data & help → footer.
        # Eliminates nested submenus (no Level 3) so submenus can never overlap the main menu on macOS.
        self.menu = [
            self.header_item,
            self.pause_scan_item,
            self.cancel_scan_item,
            *self.quick_access_items,
            self.projects_menu,
            None,
            self.brain_menu,
            self.modules_menu,
            self.models_menu,
            None,
            self.scan_data_menu,
            self.help_menu,
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
            project = self.config.project_path
            if project and is_protected_user_folder(project) and not has_full_disk_access():
                # FSEvents can block the whole process while macOS waits on a denied protected folder.
                # Keep the menu and local API responsive so Help > macOS Disk Access Settings remains usable.
                self.service.last_error = "Full Disk Access is required to watch this project folder."
                logger.warning("Watcher not started: Full Disk Access is required for %s", project)
            else:
                self.service.start(auto_scan=True)
        self.service.ensure_builtin_model()

    def _build_header_view(self):
        """Constructs the native macOS popover header view with title + LED indicator and knowledge graph card."""
        w, h = 216.0, 72.0
        container = NSView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(w, h)))
        delegate = HeaderActionDelegate.alloc().initWithApp_(self)

        # 1. Top row title: "codebone" (bold 15pt) + LED status dot
        title_lbl = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(14, 47), NSSize(150, 20)))
        title_lbl.setStringValue_("codebone")
        title_lbl.setFont_(NSFont.boldSystemFontOfSize_(15.0))
        title_lbl.setTextColor_(NSColor.labelColor())
        title_lbl.setBezeled_(False)
        title_lbl.setDrawsBackground_(False)
        title_lbl.setEditable_(False)
        title_lbl.setSelectable_(False)
        container.addSubview_(title_lbl)

        # Status indicator dot LED (Green = Active/Watching, Blue = Sniffing/Indexing, Gray = Unconfigured)
        status_dot = StatusDotView.alloc().initWithFrame_(NSRect(NSPoint(190, 50), NSSize(14, 14)))
        status_dot.setColor_(NSColor.systemGreenColor() if self.config.is_configured else NSColor.secondaryLabelColor())
        container.addSubview_(status_dot)

        # 2. Divider line
        div = NSBox.alloc().initWithFrame_(NSRect(NSPoint(12, 42), NSSize(192, 1)))
        div.setBoxType_(NSBoxSeparator)
        container.addSubview_(div)

        # 3. Bottom row: clickable CardRowView for Knowledge Graph HUD
        card = CardRowView.alloc().initWithFrame_(NSRect(NSPoint(6, 5), NSSize(204, 32)))
        card.setTarget_(delegate)
        card.setAction_(objc.selector(delegate.cardClicked_, signature=b"v@:@"))

        # 3a. Clean Apple SF Symbol vector icon
        graph_img = _create_clean_graph_icon(18.0)
        graph_iv = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(8, 7), NSSize(18, 18)))
        if graph_img:
            graph_iv.setImage_(graph_img)
        card.addSubview_(graph_iv)

        # 3b. Card stats line (always active project: Nodes & Connections)
        init_files = self.service.storage.file_count() if self.config.is_configured else 0
        init_edges = len(self.service.storage.graph_edges(include_domains=True)) if self.config.is_configured else 0
        stats_lbl = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(32, 7), NSSize(150, 18)))
        stats_lbl.setStringValue_(f"{init_files} Nodes  ·  {init_edges} Connections" if self.config.is_configured else "0 Nodes  ·  0 Connections")
        stats_lbl.setFont_(NSFont.systemFontOfSize_(11.5))
        stats_lbl.setTextColor_(NSColor.labelColor())
        stats_lbl.setBezeled_(False)
        stats_lbl.setDrawsBackground_(False)
        stats_lbl.setEditable_(False)
        stats_lbl.setSelectable_(False)
        stats_lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        card.addSubview_(stats_lbl)

        # 3c. Chevron
        chev = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(186, 7), NSSize(14, 18)))
        chev.setStringValue_("›")
        chev.setFont_(NSFont.boldSystemFontOfSize_(15.0))
        chev.setTextColor_(NSColor.tertiaryLabelColor())
        chev.setBezeled_(False)
        chev.setDrawsBackground_(False)
        chev.setEditable_(False)
        chev.setSelectable_(False)
        card.addSubview_(chev)

        container.addSubview_(card)
        return container, delegate, status_dot, stats_lbl, title_lbl

    def _build_modules_switch_row(self):
        """A menu row that IS the on/off control for the custom coding model, native-switch style."""
        w, h = 216.0, 30.0
        container = FullWidthMenuView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(w, h)))
        container.setAutoresizingMask_(NSViewWidthSizable)
        delegate = ModulesSwitchDelegate.alloc().initWithApp_(self)

        label = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(14, 6), NSSize(140, 18)))
        label.setStringValue_("Use Custom Model")
        label.setFont_(NSFont.systemFontOfSize_(13.0))
        label.setTextColor_(NSColor.labelColor())
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        container.addSubview_(label)

        switch = NSSwitch.alloc().initWithFrame_(NSRect(NSPoint(w - 52, 4), NSSize(38, 22)))
        switch.setAutoresizingMask_(NSViewMinXMargin)
        switch.setState_(NSControlStateValueOn if bool(self.config.get("modules_enabled")) else NSControlStateValueOff)
        switch.setTarget_(delegate)
        switch.setAction_(objc.selector(delegate.switchToggled_, signature=b"v@:@"))
        container.addSubview_(switch)

        return container, delegate, switch

    def _build_map_switch_row(self):
        """A menu row that toggles custom cloud model vs local built-in model for Map Agent."""
        w, h = 216.0, 30.0
        container = FullWidthMenuView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(w, h)))
        container.setAutoresizingMask_(NSViewWidthSizable)
        delegate = MapSwitchDelegate.alloc().initWithApp_(self)

        label = NSTextField.alloc().initWithFrame_(NSRect(NSPoint(14, 6), NSSize(140, 18)))
        label.setStringValue_("Use Custom Model")
        label.setFont_(NSFont.systemFontOfSize_(13.0))
        label.setTextColor_(NSColor.labelColor())
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        container.addSubview_(label)

        is_custom = self.config.get("brain_provider") in ("cloud", "local_url")
        switch = NSSwitch.alloc().initWithFrame_(NSRect(NSPoint(w - 52, 4), NSSize(38, 22)))
        switch.setAutoresizingMask_(NSViewMinXMargin)
        switch.setState_(NSControlStateValueOn if is_custom else NSControlStateValueOff)
        switch.setTarget_(delegate)
        switch.setAction_(objc.selector(delegate.switchToggled_, signature=b"v@:@"))
        container.addSubview_(switch)

        return container, delegate, switch

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
            err_str = str(exc)
            if any(m in err_str.lower() for m in ("nodename nor servname", "errno 8", "timed out", "connection refused", "temporary failure")):
                msg = "Could not connect to GitHub. Please check your internet connection and try again."
            else:
                msg = f"Could not check for updates:\n{exc}"
            rumps.alert(
                title="Update Check",
                message=msg,
                ok="OK",
            )
            return

        if not update_info.get("update_available"):
            if update_info.get("error"):
                err_msg = update_info["error"]
                rumps.alert(
                    title="Update Check",
                    message=err_msg,
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
                msg = str(err)  # err is unbound once this block exits; _show runs later on the main thread

                def _show():
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    rumps.alert(
                        title="Update Installation Failed",
                        message=f"An error occurred while installing the update:\n{msg}",
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

        if self.service.sniffing:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Scan Already in Progress")
            is_paused = self.service.is_paused
            current_target = ""
            if self.service.scan_progress:
                current_target = self.service.scan_progress.get("project", "")
            detail = f"A scan is currently active{f' ({current_target})' if current_target else ''}."
            if is_paused:
                detail += " It is currently paused."
            detail += "\n\nRunning multiple scans slows down your Mac. What would you like to do?"
            alert.setInformativeText_(detail)
            alert.addButtonWithTitle_("Wait / Keep Running" if not is_paused else "Keep Paused")
            alert.addButtonWithTitle_("Cancel Ongoing Scan")
            alert.addButtonWithTitle_("Resume Scan" if is_paused else "Pause Scan")
            response = alert.runModal()
            if response == 1001:
                self.cancel_indexing()
            elif response == 1002:
                self.toggle_pause_indexing()
            return

        projects = [p for p in self.config.project_paths if p.exists()]
        if len(projects) <= 1:
            label = projects[0].name if projects else "project"
            rumps.notification("codebone", "Scan Started", f"Scanning {label}...")
        else:
            rumps.notification(
                "codebone", "Scan Started",
                f"Scanning {len(projects)} project folders...",
            )
        self._run_workspace_scan()

    def _run_workspace_scan(self):
        """Background pass over every workspace folder, then one summary notification."""
        def _run():
            def _on_prog(cur, tot, f):
                self._on_main(self._push_stats)

            try:
                results = self.service.scan_all_projects(on_progress=_on_prog)
                if not results:
                    return
                for r in results:
                    proj_p = r.get("project_path")
                    if proj_p:
                        self._last_completed_scans[str(Path(proj_p).resolve())] = time.time()
                if self.service.last_error:
                    # A scan can "succeed" (return normally) while having silently skipped part of a
                    # project (an unreadable subfolder, permissions) — surface that instead of reporting
                    # a clean count that doesn't match what's actually on disk.
                    rumps.notification("codebone", "Scan Finished with Issues", self.service.last_error)
                else:
                    parts = [f"{Path(r['project_path']).name} ({r['total']} files)" for r in results]
                    summary = ", ".join(parts) if len(parts) > 1 else parts[0]
                    rumps.notification("codebone", "Scan Complete", f"Mapped {summary}.")
            except Exception as exc:
                logger.exception("Workspace scan failed")
                rumps.notification("codebone", "Scan Failed", str(exc))
            finally:
                self._on_main(self._update_ui_state)

        threading.Thread(target=_run, daemon=True, name="codebone-workspace-scan").start()

    def _run_single_scan(self, p: Path):
        """Scans exactly one workspace folder and automatically activates it as the current project."""
        def _run():
            def _on_prog(cur, tot, f):
                self._on_main(self._push_stats)
            try:
                result = self.service.scan_project(p, on_progress=_on_prog)
                self._last_completed_scans[str(p.resolve())] = time.time()
                self.config.record_recent_scanned_project(str(p.resolve()))
                try:
                    self.service.activate_project(p)
                except Exception as act_err:
                    logger.warning("Could not automatically activate scanned project %s: %s", p, act_err)
                rumps.notification(
                    "codebone",
                    "Scan Complete",
                    f"{p.name}: {result['total']} files mapped.",
                )
            except Exception as exc:
                logger.exception("Single project scan failed")
                rumps.notification("codebone", "Scan Failed", str(exc))
            finally:
                self._on_main(self._update_ui_state)

        threading.Thread(target=_run, daemon=True, name="codebone-single-scan").start()

    def start_project_scan(self, p: Path):
        p = p.resolve()
        # 1. Guard against overlapping scans: warn user to protect system performance
        if self.service.sniffing:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Scan Already in Progress")
            is_paused = self.service.is_paused
            current_target = ""
            if self.service.scan_progress:
                current_target = self.service.scan_progress.get("project", "")
            detail = f"A scan is currently running{f' ({current_target})' if current_target else ''}."
            if is_paused:
                detail += " It is currently paused."
            detail += (
                f"\n\nStarting another scan for '{p.name}' now would compete for CPU resources and battery power.\n\n"
                "What would you like to do?"
            )
            alert.setInformativeText_(detail)
            alert.addButtonWithTitle_("Wait / Keep Running" if not is_paused else "Keep Paused")
            alert.addButtonWithTitle_("Cancel Ongoing Scan")
            alert.addButtonWithTitle_("Resume Scan" if is_paused else "Pause Scan")
            response = alert.runModal()
            if response == 1001:  # Cancel Ongoing Scan
                self.cancel_indexing()
            elif response == 1002:  # Pause / Resume
                self.toggle_pause_indexing()
            return

        # 2. Guard against redundant scanning (< 120s ago with no changes)
        target_str = str(p)
        last_done = self._last_completed_scans.get(target_str)
        if not last_done:
            snap = self.service._snapshot_for_project(p)
            if snap and snap.get("updated_at"):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(snap["updated_at"])
                    last_done = dt.timestamp()
                except Exception:
                    pass

        if last_done:
            elapsed = time.time() - last_done
            if 0 <= elapsed < 120:
                elapsed_sec = int(round(elapsed))
                ago_str = f"{elapsed_sec}s ago" if elapsed_sec > 1 else "just now"
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                alert = NSAlert.alloc().init()
                alert.setMessageText_("Project Recently Scanned")
                alert.setInformativeText_(
                    f"'{p.name}' was already scanned {ago_str}.\n\n"
                    "Re-scanning right away consumes unnecessary CPU and battery power without finding new changes.\n\n"
                    "Do you want to re-scan anyway?"
                )
                alert.addButtonWithTitle_("Skip (Keep Current Map)")
                alert.addButtonWithTitle_("Re-scan Anyway")
                response = alert.runModal()
                if response != 1001:
                    return

        rumps.notification("codebone", "Scan Started", f"Scanning '{p.name}'...")
        self._run_single_scan(p)

    def _run_project_tldr(self, p: Path):
        """Build and show the short whole-project explanation without changing the active project."""
        def _run():
            try:
                try:
                    result = self.service.project_tldr(p)
                except FileNotFoundError:
                    # A newly added workspace folder has no snapshot yet. Scan it once, then summarize it.
                    self.service.scan_project(p)
                    result = self.service.project_tldr(p)

                def _show():
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    body = result["text"]
                    choice = rumps.alert(
                        title=f"TLDR — {result['project']}",
                        message=body,
                        ok="Done",
                        cancel="Copy TLDR",
                        other="Open Map",
                    )
                    if choice == 0:  # Copy TLDR button
                        import subprocess
                        full_clip = f"# TLDR — {result['project']}\n\n{result['text']}\n"
                        try:
                            subprocess.run(["pbcopy"], input=full_clip.encode("utf-8"), check=False)
                            rumps.notification("codebone", "Copied to Clipboard", f"TLDR for '{result['project']}' copied!")
                        except Exception as e:
                            logger.warning("Failed to copy TLDR to clipboard: %s", e)
                    elif choice == -1:  # Open Map button
                        self.open_url(f"http://127.0.0.1:{self.service.config.port}")

                self._on_main(_show)
            except Exception as exc:
                logger.exception("Project TLDR failed for %s", p)
                message = str(exc)

                def _show_error():
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    rumps.alert("TLDR Failed", message)

                self._on_main(_show_error)
            finally:
                self._on_main(self._update_ui_state)

        rumps.notification("codebone", "Creating Project TLDR", f"Summarizing '{p.name}'...")
        threading.Thread(target=_run, daemon=True, name="codebone-project-tldr").start()

    def _push_stats(self, _timer=None):
        data = self.service.stats_snapshot()
        configured = data.get("configured", False)
        running = data.get("running", False)
        sniffing = data.get("sniffing", False)
        is_paused = bool(data.get("is_paused", False) or (data.get("scan_progress") and data["scan_progress"].get("paused", False)))
        scan_progress = data.get("scan_progress")
        repo_name = data.get("repo_name", "None")
        file_count = data.get("file_count", 0)
        connection_count = data.get("connection_count", 0)
        signature = (configured, running, sniffing, is_paused, repo_name, file_count, connection_count,
                     json.dumps(scan_progress, sort_keys=True) if scan_progress else None)
        if signature == getattr(self, "_last_stats_signature", None):
            return  # nothing changed: do not make AppKit redraw the menu every 2 s
        self._last_stats_signature = signature

        # 0. Update macOS menubar title (e.g. " (codebone · ~14s)" or " (Paused)" next to icon during scan)
        target_name = (
            (scan_progress.get("project") if scan_progress else None)
            or getattr(self.service, "current_scan_project", None)
            or (self.config.project_path.name if self.config.project_path else "codebase")
        )
        if configured and sniffing:
            eta_str = scan_progress.get("eta_str", "") if scan_progress else ""
            if is_paused:
                self.title = f" ({target_name} · Paused)"
            elif eta_str:
                self.title = f" ({target_name} · {eta_str})"
            else:
                self.title = f" ({target_name}…)"
        elif not self.icon:
            self.title = "codebone"
        else:
            self.title = ""

        # 1. Update header title (codebone or codebone · <target> (<eta>) / Paused)
        if hasattr(self, "header_title_lbl") and self.header_title_lbl is not None:
            if configured and sniffing:
                eta_str = scan_progress.get("eta_str", "") if scan_progress else ""
                if is_paused:
                    self.header_title_lbl.setStringValue_(f"codebone  ·  {target_name} (Paused)")
                elif eta_str:
                    self.header_title_lbl.setStringValue_(f"codebone  ·  {target_name} ({eta_str})")
                else:
                    self.header_title_lbl.setStringValue_(f"codebone  ·  Scanning {target_name}")
            else:
                self.header_title_lbl.setStringValue_("codebone")

        # 2. Update status indicator dot (Yellow = Paused, Blue = Scanning, Green = Ready/Watching)
        if hasattr(self, "status_dot") and self.status_dot is not None:
            if not configured:
                self.status_dot.setColor_(NSColor.secondaryLabelColor())
            elif is_paused:
                self.status_dot.setColor_(NSColor.systemYellowColor())
            elif sniffing:
                self.status_dot.setColor_(NSColor.systemBlueColor())
            elif running:
                self.status_dot.setColor_(NSColor.systemGreenColor())
            else:
                self.status_dot.setColor_(NSColor.systemOrangeColor())

        # 3. Update bottom card row stats label — always show the currently selected project's info
        if hasattr(self, "card_stats_label") and self.card_stats_label is not None:
            if configured:
                if sniffing and scan_progress:
                    curr = scan_progress.get("current", 0)
                    tot = scan_progress.get("total", 0)
                    cur_f = scan_progress.get("current_file", "")
                    short_f = Path(cur_f).name if cur_f else ""
                    eta_str = scan_progress.get("eta_str", "")
                    prefix = f"{target_name}: " if target_name and target_name != "codebase" else ""
                    if is_paused:
                        stats_text = f"Paused ({prefix}{curr}/{tot})  ·  Resume to continue"
                    else:
                        eta_part = f"  ·  {eta_str} left" if eta_str else ""
                        if short_f:
                            stats_text = f"{prefix}Scanning {short_f} ({curr}/{tot}){eta_part}"
                        else:
                            stats_text = f"{prefix}Scanning ({curr}/{tot}){eta_part}"
                elif sniffing:
                    stats_text = f"Scanning {target_name}..."
                else:
                    stats_text = f"{_fmt_count(file_count)} Nodes  ·  {_fmt_count(connection_count)} Connections"
            else:
                stats_text = "No project selected yet"
            self.card_stats_label.setStringValue_(stats_text)

        # 4. Update scan control menu items (Pause/Resume and Cancel)
        if hasattr(self, "pause_scan_item") and hasattr(self, "cancel_scan_item"):
            if sniffing:
                try:
                    self.pause_scan_item._menuitem.setHidden_(False)
                    self.cancel_scan_item._menuitem.setHidden_(False)
                except Exception:
                    pass
                if is_paused:
                    self.pause_scan_item.title = "Resume Scanning"
                    _set_symbol_icon(self.pause_scan_item, "play.fill")
                else:
                    self.pause_scan_item.title = "Pause Scanning"
                    _set_symbol_icon(self.pause_scan_item, "pause.fill")
                self.cancel_scan_item.title = "Cancel Scan"
                _set_symbol_icon(self.cancel_scan_item, "xmark.circle")
            else:
                try:
                    self.pause_scan_item._menuitem.setHidden_(True)
                    self.cancel_scan_item._menuitem.setHidden_(True)
                except Exception:
                    pass

    def toggle_pause_scanning(self, _sender=None):
        """Toggle scan pause/resume state with immediate notification and UI refresh."""
        paused = self.service.toggle_pause_scan()
        if paused:
            rumps.notification("codebone", "Scan Paused", "Scanning paused. Background CPU usage suspended.")
        else:
            rumps.notification("codebone", "Scan Resumed", "Scanning resumed.")
        self._push_stats()

    toggle_pause_indexing = toggle_pause_scanning

    def pause_scanning(self, _sender=None):
        """Pause active scanning."""
        self.service.pause_scan()
        rumps.notification("codebone", "Scan Paused", "Scanning paused. Background CPU usage suspended.")
        self._push_stats()

    pause_indexing = pause_scanning

    def resume_scanning(self, _sender=None):
        """Resume paused scanning."""
        self.service.resume_scan()
        rumps.notification("codebone", "Scan Resumed", "Scanning resumed.")
        self._push_stats()

    resume_indexing = resume_scanning

    def cancel_scanning(self, _sender=None):
        """Cancel ongoing scan and release CPU resources immediately."""
        self.service.cancel_scan()
        rumps.notification("codebone", "Scan Cancelled", "Scan cancelled. Background CPU load stopped.")
        self._push_stats()
        self._update_ui_state()

    cancel_indexing = cancel_scanning

    def _apply_all_icons(self):
        """Applies native Apple SF Symbol vector icons across the entire menu hierarchy."""
        # Top-level menu items
        if hasattr(self, "pause_scan_item"):
            is_paused = getattr(self.service, "is_paused", False)
            _set_symbol_icon(self.pause_scan_item, "play.fill" if is_paused else "pause.fill")
        if hasattr(self, "cancel_scan_item"):
            _set_symbol_icon(self.cancel_scan_item, "xmark.circle")
        _set_symbol_icon(self.mcp_setup_item, "bolt.fill")
        for item in self.quick_access_items:
            _set_symbol_icon(item, "clock.arrow.circlepath")
        _set_symbol_icon(self.projects_menu, "folder")
        _set_symbol_icon(self.brain_menu, "brain")
        _set_symbol_icon(self.modules_menu, "square.stack.3d.up")
        _set_symbol_icon(self.models_menu, "cpu")
        _set_symbol_icon(self.scan_data_menu, "externaldrive")
        _set_symbol_icon(self.help_menu, "questionmark.circle")
        _set_symbol_icon(self.feedback_item, "exclamationmark.bubble")
        _set_symbol_icon(self.about_item, "info.circle")
        _set_symbol_icon(self.quit_item, "power")

        # Submenu items
        _set_symbol_icon(self.open_map_item, "point.3.connected.trianglepath.dotted")
        _set_symbol_icon(self.documentation_item, "book")
        _set_symbol_icon(self.adopt_scan_item, "arrow.triangle.merge")
        _set_symbol_icon(self.copy_curl_item, "doc.on.clipboard")
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
            mcp_t = "⚡ Connect Coding Agent (MCP)" if self.config.is_first_days() else "Connect Coding Agent (MCP)"
            self.mcp_setup_item.title = mcp_t
            v = getattr(self.mcp_setup_item, "_choice_view", None)
            if v and hasattr(v, "_label") and v._label:
                try:
                    v._label.setStringValue_(mcp_t)
                except Exception:
                    pass
        self._apply_all_icons()
        self._update_quick_access_menu()
        self._update_projects_menu()
        self._update_brain_checks()
        self._update_modules_menu()
        self._update_models_menu()
        self._sync_modules_switch()
        self._sync_map_switch()
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

    # Provider profiles for the Map Agent menu: (config vendor id, label, default model id).
    # The model ids are the ones CloudProvider itself falls back to — no second list to keep in sync.
    BRAIN_PROFILES = (
        ("openrouter", "OpenRouter", "openai/gpt-4o-mini"),
        ("anthropic", "Claude (Anthropic)", "claude-sonnet-5"),
        ("openai", "OpenAI", "gpt-6"),
    )

    def _brain_status(self) -> tuple[str, str]:
        """(active model, state) for the status line. Deliberately offline: the menu may rebuild on the
        2 s stats timer and must never turn that into a network probe."""
        provider = self.config.get("brain_provider", "builtin")
        name = self.config.active_model_display_name
        if provider == "cloud":
            if len((self.config.get("brain_cloud_api_key") or "").strip()) <= 8:
                return name, "API key missing"
            return name, "Ready ✓" if self._brain_connection_verified() else "Not tested"
        if provider == "local_url":
            if not self.config.get("brain_local_url"):
                return name, "Server URL missing"
            return name, "Ready ✓" if self._brain_connection_verified() else "Not tested"
        return name, "Ready" if self.service.model_ready else "Model loading"

    def _brain_signature(self) -> str:
        """Non-secret fingerprint binding a successful test to the exact current provider settings."""
        provider = self.config.get("brain_provider", "builtin")
        if provider == "cloud":
            key_hash = hashlib.sha256(
                (self.config.get("brain_cloud_api_key") or "").encode("utf-8")
            ).hexdigest()[:12]
            raw = ":".join((
                "cloud",
                self.config.get("brain_cloud_vendor", "openai"),
                self.config.get("brain_cloud_model", ""),
                key_hash,
            ))
        elif provider == "local_url":
            raw = f"local_url:{self.config.get('brain_local_url', '')}"
        else:
            raw = f"builtin:{self.config.get('model_path', '')}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _brain_connection_verified(self) -> bool:
        return self.config.get("brain_tested_signature", "") == self._brain_signature()

    def _update_brain_checks(self):
        """Rebuilds the Map Agent menu: active model status at the top, local models,
        and online API models."""
        from . import modules

        if getattr(self.brain_menu, "_menu", None) is not None:
            self.brain_menu.clear()

        provider = self.config.get("brain_provider", "builtin")
        selected_mod_id = self.config.get("brain_selected_module")
        selected_mod = modules.get_module(self.config, selected_mod_id) if selected_mod_id else None

        if provider == "builtin" or not selected_mod_id:
            active_map_name = "Built-in Qwen 0.5B (Metal GPU)"
        elif selected_mod:
            active_map_name = modules.format_model_name(selected_mod)
        elif provider == "cloud":
            m_id = self.config.get("brain_cloud_model", "Model")
            v_id = self.config.get("brain_cloud_vendor", "Cloud").title()
            active_map_name = f"{m_id} ({v_id})"
        else:
            active_map_name = "Local Server (Ollama)"

        # 1. Active Model info
        self.brain_menu.add(make_info_item("Active Model"))
        self.brain_menu.add(make_info_item(active_map_name))
        self.brain_menu.add(None)

        # 2. Local Models section
        self.brain_menu.add(make_info_item("Local Models"))
        builtin_item = make_choice_item(
            "Built-in Qwen 0.5B (Metal GPU)",
            checked=bool(provider == "builtin"),
            on_click=self.select_builtin_map_model,
        )
        self.brain_menu.add(builtin_item)

        library = modules.list_modules(self.config)
        local_mods = [
            m for m in library
            if "localhost" in (m.get("openai_url") or "")
            or "127.0.0.1" in (m.get("openai_url") or "")
            or "ollama" in m.get("name", "").lower()
            or "local" in m.get("name", "").lower()
        ]
        online_mods = [m for m in library if m not in local_mods]

        for m in local_mods:
            item = make_choice_item(
                modules.format_model_name(m),
                checked=bool(provider == "local_url" and selected_mod_id == m["id"]),
                on_click=lambda mid=m["id"]: self.select_map_module(mid),
            )
            self.brain_menu.add(item)

        self.brain_menu.add(None)

        # 3. Online API Models section
        self.brain_menu.add(make_info_item("Online API Models"))
        if online_mods:
            for m in online_mods:
                item = make_choice_item(
                    modules.format_model_name(m),
                    checked=bool(provider == "cloud" and selected_mod_id == m["id"]),
                    on_click=lambda mid=m["id"]: self.select_map_module(mid),
                )
                self.brain_menu.add(item)
        else:
            add_hint = rumps.MenuItem("Add Model in Models...", callback=None)
            _set_symbol_icon(add_hint, "cloud")
            self.brain_menu.add(add_hint)

    def select_map_module(self, module_id: str):
        from . import modules
        mod = modules.get_module(self.config, module_id)
        if not mod:
            return
        key = modules.get_module_key(self.config, module_id)
        provider = modules.detect_provider(mod)
        url = mod.get("openai_url") or mod.get("anthropic_url") or ""
        self.config.set("brain_selected_module", module_id)
        self.config.set("brain_provider", "cloud" if "local" not in provider.lower() else "local_url")
        self.config.set("brain_cloud_vendor", provider.lower())
        self.config.set("brain_cloud_model", mod.get("model", ""))
        self.config.set("brain_cloud_url", url)
        self.config.set("brain_cloud_api_key", key)
        self._update_brain_checks()
        self._update_models_menu()
        self._sync_map_switch()
        rumps.notification("codebone", "Map Agent Model Updated", f"Map Agent now uses {modules.format_model_name(mod)}.")

    def select_builtin_map_model(self):
        self.config.set("brain_selected_module", None)
        self.config.set("brain_provider", "builtin")
        self._update_brain_checks()
        self._update_models_menu()
        self._sync_map_switch()
        rumps.notification("codebone", "Map Agent Model Updated", "Map Agent now uses Built-in (Qwen 0.5B) on Apple Metal.")

    def set_map_master(self, turning_on: bool):
        from . import modules
        if turning_on:
            selected_id = self.config.get("brain_selected_module")
            mod = modules.get_module(self.config, selected_id) if selected_id else None
            if not mod:
                mods = modules.list_modules(self.config)
                if mods:
                    mod = mods[0]
                    selected_id = mod["id"]
            if mod:
                self.select_map_module(selected_id)
            else:
                self.add_module_dialog(None)
        else:
            self.select_builtin_map_model()

    def _sync_map_switch(self):
        if hasattr(self, "map_switch") and self.map_switch is not None:
            is_custom = self.config.get("brain_provider") in ("cloud", "local_url")
            self.map_switch.setState_(NSControlStateValueOn if is_custom else NSControlStateValueOff)

    def setup_brain_profile(self, vendor: str, model: str, label: str):
        """Dead-simple model setup: paste the API key once, codebone saves it and checks the connection."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        current = ""
        if self.config.get("brain_cloud_vendor") == vendor:
            current = self.config.get("brain_cloud_api_key", "")
        resp = rumps.Window(
            message=f"API key for {label} (saved in codebone's config on this Mac):",
            title=f"Connect {label}",
            default_text=current,
            ok="Save & Test Connection",
            cancel="Cancel",
            dimensions=(360, 24),
            secure=True,
        ).run()
        if not resp.clicked:
            return
        key = resp.text.strip()
        if not key:
            return
        self.config.set("brain_cloud_vendor", vendor)
        self.config.set("brain_cloud_model", model)
        self.config.set("brain_cloud_api_key", key)
        self.config.set("brain_provider", "cloud")
        self.config.set("brain_tested_signature", "")
        self.service.reload_provider()
        self._update_ui_state()
        self._test_brain(f"{label} ({model})")

    def _test_brain(self, label: str):
        """Verifies the configured model really answers. Success is what the status line's "(Ready)"
        means, so the check runs in the background and reports through a notification/alert."""
        signature = self._brain_signature()
        provider = self.service.provider

        def _run():
            try:
                out = provider.generate("Reply with the single word OK.", max_tokens=16)
            except Exception as exc:
                logger.warning("Brain connection test failed: %s", exc)
                out = ""
            ok = bool(out and out.strip())

            def _done():
                still_current = self._brain_signature() == signature
                if not still_current:
                    return  # the user selected another provider while this request was in flight
                self.config.set("brain_tested_signature", signature if ok else "")
                if ok:
                    rumps.notification(
                        "codebone",
                        f"Connected: {label}",
                        f"Active model: {self.config.active_model_display_name}",
                    )
                else:
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    rumps.alert(
                        "Connection Test Failed",
                        f"{label} did not answer.\n\nCheck the API key (or that the local server is "
                        "running) and try again.",
                    )
                self._update_ui_state()

            self._on_main(_done)

        threading.Thread(target=_run, daemon=True, name="codebone-brain-test").start()

    def test_selected_brain(self, _=None):
        """Tests connection to the currently configured Map Agent provider."""
        name = self.config.active_model_display_name
        self._test_brain(name)

    def rename_module_dialog(self, module_id: str, current_name: str):
        from . import modules
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        resp = rumps.Window(
            message=f"Enter new name for '{current_name}':",
            title="Rename Model",
            default_text=current_name,
            ok="Save",
            cancel="Cancel",
            dimensions=(320, 24),
        ).run()
        if not resp.clicked:
            return
        new_name = resp.text.strip()
        if not new_name or new_name == current_name:
            return
        modules.rename_module(self.config, module_id, new_name)
        self._update_modules_menu()
        self._update_brain_checks()
        self._update_models_menu()
        rumps.notification("codebone", "Model Renamed", f"Model is now named '{new_name}'.")

    def test_module_by_id(self, module_id: str):
        from . import modules
        mod = modules.get_module(self.config, module_id)
        if not mod:
            return
        self.test_selected_module(None, target_mod=mod)

    def _copy_text(self, text: str, label: str):
        if not text:
            rumps.notification("codebone", "Copy", f"No {label} available to copy.")
            return
        copy_to_clipboard(text)
        rumps.notification("codebone", f"{label} Copied", f"Copied '{text}' to clipboard.")

    def _copy_module_key(self, module_id: str):
        from . import modules
        key = modules.Keychain().get(module_id)
        if not key:
            rumps.notification("codebone", "API Key", "No API key stored for this model.")
            return
        copy_to_clipboard(key)
        rumps.notification("codebone", "API Key Copied", "API key copied to clipboard.")

    def _update_models_menu(self):
        """Rebuilds the Models... menu: list of all configured models, Add Model,
        per-model rename, key editing, copy endpoints, and removal."""
        from . import modules

        if getattr(self.models_menu, "_menu", None) is not None:
            self.models_menu.clear()

        # Header info
        self.models_menu.add(make_info_item("Models & APIs"))
        self.models_menu.add(None)

        # 1. Built-in Local Model (Apple Silicon Metal)
        builtin_item = rumps.MenuItem("Built-in Qwen 0.5B (Metal GPU) — Ready (Map Agent)")
        _set_symbol_icon(builtin_item, "cpu")
        builtin_info = rumps.MenuItem("Engine: Local Apple Silicon Metal (GGUF)", callback=None)
        _set_symbol_icon(builtin_info, "info.circle")
        builtin_item.add(builtin_info)
        builtin_scope = rumps.MenuItem("Scope: Knowledge Graph & Architecture Indexing", callback=None)
        _set_symbol_icon(builtin_scope, "sparkles")
        builtin_item.add(builtin_scope)
        builtin_privacy = rumps.MenuItem("Privacy: Fully Local (No API Key Required)", callback=None)
        _set_symbol_icon(builtin_privacy, "lock.shield")
        builtin_item.add(builtin_privacy)
        builtin_item.add(None)
        builtin_test = make_choice_item("Test Local Inference", None, lambda: self.test_selected_brain(None), icon="bolt")
        builtin_item.add(builtin_test)
        self.models_menu.add(builtin_item)
        self.models_menu.add(None)

        library = modules.list_modules(self.config)

        if library:
            for m in library:
                m_label = modules.format_model_name(m)
                has_key = bool(modules.Keychain().get(m["id"]))
                key_text = "Key Set ✓" if has_key else "No Key"
                item = rumps.MenuItem(f"{m_label} — {key_text}")
                _set_symbol_icon(item, "network" if "local" in m_label.lower() else "cloud")

                # Copy Endpoints & Credentials directly in model settings
                model_id_val = m.get("model", "")
                item.add(make_choice_item(f"Copy Model ID ({model_id_val})", None, lambda val=model_id_val: self._copy_text(val, "Model ID"), icon="doc.on.clipboard"))
                item.add(make_choice_item("Copy API Key", None, lambda mid=m["id"]: self._copy_module_key(mid), icon="key"))

                openai_url = m.get("openai_url")
                if openai_url:
                    item.add(make_choice_item("Copy OpenAI Base URL", None, lambda val=openai_url: self._copy_text(val, "OpenAI URL"), icon="link"))

                anthropic_url = m.get("anthropic_url")
                if anthropic_url:
                    item.add(make_choice_item("Copy Anthropic Base URL", None, lambda val=anthropic_url: self._copy_text(val, "Anthropic URL"), icon="link"))

                item.add(None)

                edit_key_item = rumps.MenuItem(
                    "Edit API Key...",
                    callback=lambda _, mid=m["id"], n=m["name"]: self.edit_module_key(mid, n),
                )
                _set_symbol_icon(edit_key_item, "key.fill")
                item.add(edit_key_item)

                rename_item = rumps.MenuItem(
                    "Rename Model...",
                    callback=lambda _, mid=m["id"], n=m["name"]: self.rename_module_dialog(mid, n),
                )
                _set_symbol_icon(rename_item, "pencil")
                item.add(rename_item)

                item.add(make_choice_item("Test Connection", None, lambda mid=m["id"]: self.test_module_by_id(mid), icon="bolt"))

                item.add(None)
                remove_item = rumps.MenuItem(
                    "Remove Model",
                    callback=lambda _, mid=m["id"], n=m["name"]: self.remove_module_dialog(mid, n),
                )
                _set_symbol_icon(remove_item, "trash")
                item.add(remove_item)

                self.models_menu.add(item)
        else:
            self.models_menu.add(make_info_item("No custom models added yet"))

        self.models_menu.add(None)

        # Actions
        add_item = rumps.MenuItem("Add Model...", callback=self.add_module_dialog)
        _set_symbol_icon(add_item, "plus")
        self.models_menu.add(add_item)

        add_gguf_item = rumps.MenuItem("Add Model File (.gguf)...", callback=self.add_model_file)
        _set_symbol_icon(add_gguf_item, "doc.badge.plus")
        self.models_menu.add(add_gguf_item)

    def _update_api_keys_menu(self):
        """Backward compatibility alias."""
        return self._update_models_menu()

    def edit_module_key(self, module_id: str, name: str):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        current = modules.Keychain().get(module_id) or ""
        resp = rumps.Window(
            message=f"API key for '{name}' (stored in your macOS Keychain):",
            title="Edit API Key",
            default_text=current,
            ok="Save Key",
            cancel="Cancel",
            dimensions=(360, 24),
            secure=True,
        ).run()
        if not resp.clicked:
            return
        key = resp.text.strip()
        if not key or key == current:
            return
        try:
            modules.Keychain().set(module_id, key)
            self._update_modules_menu()
            self._update_brain_checks()
            self._update_models_menu()
            rumps.notification("codebone", "API Key Saved", f"Updated API key for '{name}'.")
        except RuntimeError as exc:
            rumps.alert("API Keys", str(exc))

    def select_model_by_path(self, path: str, name: str):
        self.config.select_model(path)
        self.config.set("brain_provider", "builtin")
        self.service.reload_provider()
        self._update_ui_state()
        rumps.notification("codebone", "Model switched", f"Active model: {name}")

    def _update_quick_access_menu(self):
        """Show the three latest successful scans as full project menus, newest first."""
        recent = self.config.recent_scanned_projects
        if recent is None:
            # One-time migration for existing installs: the snapshot registry is already ordered newest first.
            seeded: list[str] = []
            for scan in self.service.scans.list_scans():
                raw = scan.get("project_path")
                if not raw:
                    continue
                path = Path(raw).expanduser()
                resolved = str(path.resolve())
                if path.exists() and resolved not in seeded:
                    seeded.append(resolved)
            self.config.set("recent_scanned_projects", seeded[:10])
            recent = seeded[:10]

        visible: list[Path] = []
        seen_resolved: set[str] = set()
        for raw in recent or []:
            path = Path(raw).expanduser()
            if path.exists() and path.is_dir():
                resolved = str(path.resolve())
                if resolved not in seen_resolved:
                    seen_resolved.add(resolved)
                    visible.append(path.resolve())
            if len(visible) == 3:
                break

        self.quick_access_paths = visible
        active = self.config.project_path
        active_str = str(active) if active else None
        ws_by_path = {p["path"]: p for p in self.service.workspace_stats()["projects"]}
        names = [p.name for p in visible]
        for index, item in enumerate(self.quick_access_items):
            show = index < len(visible)
            try:
                item._menuitem.setHidden_(not show)
            except Exception:
                pass
            if show:
                path = visible[index]
                if names.count(path.name) > 1:
                    item.title = f"{path.name} ({path.parent.name})"
                else:
                    item.title = path.name or str(path)
                try:
                    item._menuitem.setToolTip_(str(path))
                except Exception:
                    pass
                item.state = False
                self._populate_project_actions(item, path, ws_by_path.get(str(path)), active_str)
            elif getattr(item, "_menu", None) is not None:
                item.clear()

    def _populate_project_actions(
        self,
        item: rumps.MenuItem,
        project: Path,
        info: Optional[dict],
        active_str: Optional[str],
    ):
        """Give recent shortcuts and Projects entries the exact same project submenu."""
        if getattr(item, "_menu", None) is not None:
            item.clear()

        info_item = make_choice_item(
            "Info...",
            checked=None,
            on_click=lambda target=project: self.show_project_info(target),
            icon="info.circle",
            tooltip=str(project.resolve()),
        )
        item.add(info_item)

        copy_path_item = make_choice_item(
            "Copy Path",
            checked=None,
            on_click=lambda target=project: self._copy_text(str(target.resolve()), "Project Path"),
            icon="doc.on.clipboard",
        )
        item.add(copy_path_item)

        tldr_item = make_choice_item(
            "TLDR...",
            checked=None,
            on_click=lambda target=project: self._run_project_tldr(target),
            icon="text.quote",
        )
        item.add(tldr_item)

        item.add(None)
        scan_item = make_choice_item(
            "Scan",
            checked=None,
            on_click=lambda target=project: self.start_project_scan(target),
            icon="arrow.clockwise",
        )
        item.add(scan_item)

        auto_scan_on = self.config.is_auto_scan_enabled(project)
        auto_scan_item = make_choice_item(
            "Auto-Scan on Save",
            checked=auto_scan_on,
            on_click=lambda target=project: self.toggle_project_auto_scan(target, auto_scan_item),
        )
        item.add(auto_scan_item)

        item.add(None)
        if info:
            map_label = f"Open Map ({_fmt_count(info['nodes'])} Nodes · {_fmt_count(info['connections'])} Connections)"
            map_item = make_choice_item(
                map_label,
                checked=None,
                on_click=lambda target=project: self.view_project_map(target),
                icon="point.3.connected.trianglepath.dotted",
                width=240.0,
            )
            item.add(map_item)
        else:
            item.add(make_info_item("Not Scanned Yet"))

        reveal = make_choice_item(
            "Show in Finder...",
            checked=None,
            on_click=lambda target=project: self.reveal_project(target),
            icon="folder",
        )
        item.add(reveal)

        item.add(None)
        remove = make_choice_item(
            "Remove Project...",
            checked=None,
            on_click=lambda target=project: self.remove_from_workspace(target),
            icon="minus.circle",
        )
        item.add(remove)

    def _update_projects_menu(self):
        """Keep the first level to project names; actions and details live one level deeper."""
        if getattr(self.projects_menu, "_menu", None) is not None:
            self.projects_menu.clear()

        active = self.config.project_path
        recent_paths = {str(p) for p in self.quick_access_paths}
        workspace = [p for p in self.config.project_paths if p.exists() and str(p) not in recent_paths]
        active_str = str(active) if active else None
        ws_by_path = {p["path"]: p for p in self.service.workspace_stats()["projects"]}

        if workspace:
            names = [p.name for p in workspace]
            for p in workspace:
                info = ws_by_path.get(str(p))
                if names.count(p.name) > 1:
                    title = f"{p.name} ({p.parent.name})"
                else:
                    title = p.name or str(p)
                item = rumps.MenuItem(title)
                _set_symbol_icon(item, "folder.fill" if active_str == str(p) else "folder")
                item.state = False
                try:
                    item._menuitem.setToolTip_(str(p.resolve()))
                except Exception:
                    pass
                self._populate_project_actions(item, p, info, active_str)
                self.projects_menu.add(item)
        else:
            message = "All Projects Are Shown Above" if self.quick_access_paths else "No Project Folders Yet"
            self.projects_menu.add(make_info_item(message))

        self.projects_menu.add(None)
        add_item = rumps.MenuItem("+ Add Project...", callback=self.choose_project)
        _set_symbol_icon(add_item, "folder.badge.plus")
        self.projects_menu.add(add_item)

        if self.config.recent_scanned_projects:
            self.projects_menu.add(None)
            clear_item = rumps.MenuItem("Clear Recent Projects...", callback=self.clear_recent_projects)
            _set_symbol_icon(clear_item, "trash")
            self.projects_menu.add(clear_item)

    def toggle_project_auto_scan(self, project: Path, sender: Optional[rumps.MenuItem] = None):
        """Toggle automatic scanning on file save for the given project folder."""
        is_enabled = self.config.is_auto_scan_enabled(project)
        new_state = not is_enabled
        self.config.set_auto_scan_enabled(project, new_state)
        if sender is not None:
            sender.state = new_state
        state_word = "enabled" if new_state else "disabled"
        rumps.notification(
            "codebone",
            f"Auto-Scan {state_word.capitalize()}",
            f"Auto-scan on save is now {state_word} for '{project.name}'.",
        )
        self._update_projects_menu()
        self._update_quick_access_menu()

    def remove_from_workspace(self, p: Path):
        """Remove a project from the workspace without deleting its folder or saved map."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if rumps.alert(
            "Remove Project?",
            f"Remove '{p.name}' from Projects?\n\nIts folder and saved map stay on your Mac.",
            ok="Remove",
            cancel="Cancel",
        ) != 1:
            return

        was_active = self.config.project_path == p
        self.config.remove_project_path(str(p))
        self.config.remove_recent_project(str(p))
        self.config.remove_recent_scanned_project(str(p))
        remaining = [path for path in self.config.project_paths if path.exists()]
        if not was_active:
            self._update_ui_state()
            rumps.notification("codebone", "Project Removed", f"'{p.name}' is no longer in Projects.")
            return

        if not remaining:
            self.service.stop()
            self.config.set("project_path", None)
            self._update_ui_state()
            rumps.notification("codebone", "Project Removed", "Add a project whenever you're ready.")
            return

        next_project = remaining[0]

        def _switch_after_remove():
            try:
                self.service.activate_project(next_project)
            except FileNotFoundError:
                self.config.set("project_path", str(next_project))
                self.service.start(auto_scan=True)
            finally:
                self._on_main(self._update_ui_state)

        threading.Thread(target=_switch_after_remove, daemon=True, name="codebone-remove-project").start()
        rumps.notification("codebone", "Project Removed", f"Now using '{next_project.name}'.")

    def activate_project_from_menu(self, p: Path):
        self._activate_project(p, open_map=False)

    def view_project_map(self, p: Path):
        self._activate_project(p, open_map=True)

    def _activate_project(self, p: Path, open_map: bool):
        """Restore a project's saved map, then optionally open that exact map in the browser."""
        if open_map:
            try:
                NSMenu.cancelTracking()
            except Exception:
                pass
        if self.config.project_path == p and self.service.watching:
            if open_map:
                self.view_live_graph(None)
            return

        def _run():
            try:
                self.service.activate_project(p)
            except Exception as exc:
                message = str(exc)

                def _show_error():
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                    rumps.alert("Project Could Not Be Opened", message)

                self._on_main(_show_error)
                return

            def _done():
                self._update_ui_state()
                if open_map:
                    self.view_live_graph(None)
                else:
                    rumps.notification("codebone", "Project Switched", f"Now active: '{p.name}'.")

            self._on_main(_done)

        threading.Thread(target=_run, daemon=True, name="codebone-activate-project").start()

    def show_project_info(self, p: Path):
        """Displays project directory location, status, and gives a quick link to reveal in Finder or copy path."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        resolved = p.resolve()
        path_str = str(resolved)
        is_active = self.config.project_path and self.config.project_path.resolve() == resolved
        status_line = "Active Project" if is_active else "Inactive Project"

        ws_by_path = {item["path"]: item for item in self.service.workspace_stats()["projects"]}
        info = ws_by_path.get(path_str)
        if info:
            stats_line = f"Knowledge Graph: {_fmt_count(info['nodes'])} Nodes · {_fmt_count(info['connections'])} Connections"
        else:
            stats_line = "Knowledge Graph: Not scanned yet"

        auto_scan_str = "Enabled (watching on save)" if self.config.is_auto_scan_enabled(p) else "Disabled (manual scan only)"
        msg = (
            f"Directory:\n{path_str}\n\n"
            f"Status: {status_line}\n"
            f"Auto-Scan on Save: {auto_scan_str}\n\n"
            f"{stats_line}"
        )
        res = rumps.alert(
            title=f"Project Info: {p.name}",
            message=msg,
            ok="Open in Finder",
            cancel="Close",
            other="View TLDR",
        )
        if res == 1:
            self.reveal_project(p)
        elif res == -1:
            self._run_project_tldr(p)

    def reveal_project(self, p: Path):
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
        try:
            subprocess.Popen(["open", str(p)])
        except Exception as exc:
            logger.error("Failed to reveal project %s: %s", p, exc)

    # ── model modules ────────────────────────────────────────────────────
    def _update_modules_menu(self):
        from . import modules

        if getattr(self.modules_menu, "_menu", None) is not None:
            self.modules_menu.clear()
        library = modules.list_modules(self.config)
        selected = modules.get_module(self.config, self.config.get("module_selected"))
        master_on = bool(self.config.get("modules_enabled"))
        active = set(modules.enabled_apps(self.config))

        if not master_on:
            active_coding_name = "Default Setup (Off)"
        elif selected:
            active_coding_name = modules.format_model_name(selected)
        else:
            active_coding_name = "Custom Model (None Selected)"

        # 1. Active Model info
        self.modules_menu.add(make_info_item("Active Model"))
        self.modules_menu.add(make_info_item(active_coding_name))
        self.modules_menu.add(None)

        # 2. Switch row
        self.modules_menu.add(self.modules_switch_item)
        self.modules_menu.add(None)

        # 3. Local Models section
        self.modules_menu.add(make_info_item("Local Models"))
        local_mods = [
            m for m in library
            if "localhost" in (m.get("openai_url") or "")
            or "127.0.0.1" in (m.get("openai_url") or "")
            or "ollama" in m.get("name", "").lower()
            or "local" in m.get("name", "").lower()
        ]
        online_mods = [m for m in library if m not in local_mods]

        def _model_row(m: dict, icon: str):
            label = modules.format_model_name(m)
            is_selected = bool(selected and selected["id"] == m["id"])
            if master_on:
                return make_choice_item(label, checked=is_selected, on_click=lambda mid=m["id"]: self.pick_module(mid))
            row = rumps.MenuItem(label, callback=None)
            _set_symbol_icon(row, icon)
            row.state = is_selected
            return row

        # Built-in model: never usable for coding agents, so it is greyed out and only explains itself on hover.
        builtin_hint = rumps.MenuItem("Built-in Qwen 0.5B (Metal GPU)", callback=None)
        _set_symbol_icon(builtin_hint, "cpu")
        try:
            builtin_hint._menuitem.setToolTip_(
                "Greyed out on purpose: the built-in Qwen 0.5B only powers the Map Agent (knowledge map indexing). "
                "Coding agents need a full coding model - add one in Models..."
            )
        except Exception:
            pass
        self.modules_menu.add(builtin_hint)
        for m in local_mods:
            self.modules_menu.add(_model_row(m, "network"))

        self.modules_menu.add(None)

        # 4. Online API Models section
        self.modules_menu.add(make_info_item("Online API Models"))
        if online_mods:
            for m in online_mods:
                self.modules_menu.add(_model_row(m, "cloud"))
        else:
            add_hint = rumps.MenuItem("Add Model in Models...", callback=None)
            _set_symbol_icon(add_hint, "cloud")
            self.modules_menu.add(add_hint)

        self.modules_menu.add(None)

        # Agent Routing
        agents_menu = rumps.MenuItem("Use in Coding Agent")
        _set_symbol_icon(agents_menu, "arrow.triangle.branch")
        for app_id, (label, fmt) in modules.APPS.items():
            item = rumps.MenuItem(
                f"Use in {label}",
                callback=(lambda _, a=app_id: self.toggle_module_app(a)) if master_on else None,
            )
            item.state = app_id in active
            agents_menu.add(item)
        self.modules_menu.add(agents_menu)

        self.modules_menu.add(None)
        self.modules_menu.add(rumps.MenuItem("Reset Agent Routing", callback=self.reset_modules_to_normal))

    def _add_local_ollama_module(self):
        from . import modules
        try:
            mod = modules.add_module(
                self.config,
                name="Local Server (Ollama)",
                model="qwen2.5-coder:7b",
                key="local",
                anthropic_url="",
                openai_url="http://localhost:11434/v1",
            )
            self.config.set("module_selected", mod["id"])
            self.config.set("modules_enabled", True)
            self._update_modules_menu()
            self._update_models_menu()
            rumps.notification("codebone", "Local Server Connected", "Coding agents routed through Ollama.")
        except Exception as exc:
            rumps.alert("Local Server", f"Failed to add local server: {exc}")

    def _add_preset_module(self, preset: dict):
        from . import modules
        name = preset["name"]
        model = preset["model"]
        anthropic_url = preset.get("anthropic_url", "")
        openai_url = preset.get("openai_url", "")

        map_key = (self.config.get("brain_cloud_api_key") or "").strip()
        map_vendor = self.config.get("brain_cloud_vendor", "openai")
        key = ""
        if map_key and map_vendor.lower() in name.lower():
            key = map_key

        if not key and "local" not in name.lower():
            resp = rumps.Window(
                message=f"Enter API key for {name}:",
                title=f"Connect {name}",
                default_text="",
                ok="Save & Connect",
                cancel="Cancel",
                dimensions=(360, 24),
                secure=True,
            ).run()
            if not resp.clicked:
                return
            key = resp.text.strip()
            if not key:
                return

        try:
            mod = modules.add_module(self.config, name, model, key or "none", anthropic_url, openai_url)
            self.config.set("module_selected", mod["id"])
            self.config.set("modules_enabled", True)
            self._update_modules_menu()
            self._update_models_menu()
            rumps.notification("codebone", f"{name} Connected", "Selected coding agents now use this model.")
        except Exception as exc:
            rumps.alert("Add Model", f"Failed to add model: {exc}")

    def open_url(self, url: str):
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
        try:
            subprocess.Popen(["open", url])
        except Exception as exc:
            logger.error("Failed to open URL %s: %s", url, exc)

    def set_modules_master(self, turning_on: bool):
        """The switch row's on/off action: on = previously active apps route through their module
        again, off = every app goes straight back to normal and nothing is routed."""
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        try:
            modules.set_modules_master(self.config, turning_on)
        except modules.SettingsUnreadable as exc:
            rumps.alert("Coding Agent", f"Settings file could not be read, so nothing was changed:\n{exc}")
            self._sync_modules_switch()
            return
        if turning_on:
            rumps.notification("codebone", "Custom Coding Model On", "Selected coding agents now use this model.")
            selected = modules.get_module(self.config, self.config.get("module_selected"))
            if selected:
                for app_id in modules.enabled_apps(self.config):
                    self._verify_module_or_revert(app_id, selected)
        else:
            rumps.notification("codebone", "Custom Coding Model Off", "Every coding agent is back on its normal setup.")
        self._update_modules_menu()
        self._sync_modules_switch()

    def _sync_modules_switch(self):
        """Keeps the switch row's visible state matching config, including when something other than
        a direct click on the switch changed it (for example, an automatic connection reset)."""
        if getattr(self, "modules_switch", None) is not None:
            self.modules_switch.setState_(
                NSControlStateValueOn if bool(self.config.get("modules_enabled")) else NSControlStateValueOff
            )

    def reset_modules_to_normal(self, _):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if rumps.alert(
            "Reset Coding Agent Connection",
            "This puts all coding agents (Claude Code, Codex, Cursor, Antigravity, and opencode) back "
            "on their normal setup, whatever codebone currently thinks their state is. Use this if a "
            "model's API key stopped working and switching it off didn't fix it.",
            ok="Reset to Normal", cancel="Cancel",
        ) != 1:
            return
        modules.force_restore_all(self.config)
        rumps.notification("codebone", "Coding Agents Reset", "All coding agents are back on their normal setup.")
        self._update_modules_menu()
        self._sync_modules_switch()

    def toggle_module_app(self, app_id: str):
        from . import modules

        label = modules.APPS[app_id][0]
        turning_on = app_id not in modules.enabled_apps(self.config)
        try:
            module = modules.set_app_enabled(self.config, app_id, turning_on)
        except modules.SettingsUnreadable as exc:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("Coding Agent", f"{label}'s settings file could not be read, so nothing was changed:\n{exc}")
            return
        except ValueError as exc:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("Coding Agent", str(exc))
            return
        if module:
            rumps.notification("codebone", f"{label} now uses {module['name']}", "New sessions pick this up; running ones keep their model.")
            self._verify_module_or_revert(app_id, module)
        else:
            rumps.notification("codebone", f"{label} is back on its normal model", "New sessions use your usual setup again.")
        self._update_modules_menu()

    def _verify_module_or_revert(self, app_id: str, module: dict):
        """After switching an app onto a module, confirms the endpoint answers in the background.
        If it doesn't, it alerts the user with diagnostic advice, but does NOT silently uncheck
        or revert the user's setting."""
        from . import modules

        label = modules.APPS[app_id][0]
        fmt = modules.APPS[app_id][1]
        url = modules._url(module, fmt, self.server.port if getattr(self, "server", None) else None)
        key = modules.Keychain().get(module["id"])
        if not url or not key:
            return

        def _run():
            try:
                ok, msg = modules.test_connection(url, module["model"], key, fmt=fmt)
            except Exception as exc:
                ok, msg = False, str(exc)
            if ok:
                return

            def _warn():
                rumps.notification(
                    "codebone", f"{label}: Connection Warning",
                    f"{module['name']} did not answer ({msg}). Check your key in Settings > API Keys.",
                )

            self._on_main(_warn)

        threading.Thread(target=_run, daemon=True, name="codebone-module-verify").start()

    def copy_module_value(self, what: str, getter):
        value = getter()
        if not value:
            rumps.alert("Coding Agent", f"This model has no {what}.")
            return
        copy_to_clipboard(value)
        rumps.notification("codebone", f"{what} copied", "Paste it into the other app's model settings.")

    def pick_module(self, module_id: str):
        from . import modules

        try:
            modules.select_module(self.config, module_id)
        except (ValueError, modules.SettingsUnreadable) as exc:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("Coding Agent", str(exc))
        self._update_modules_menu()
        self._update_models_menu()

    def add_module_dialog(self, _):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        # 1-click sync if user already configured a model in Map Agent
        map_key = (self.config.get("brain_cloud_api_key") or "").strip()
        map_vendor = self.config.get("brain_cloud_vendor", "openai")
        map_model = self.config.get("brain_cloud_model", "")
        if map_key and len(map_key) > 8:
            vendor_display = {
                "openai": "OpenAI",
                "anthropic": "Claude (Anthropic)",
                "openrouter": "OpenRouter",
            }.get(map_vendor, map_vendor.title())
            use_map = rumps.alert(
                title="Add Coding Model",
                message=f"You already have a {vendor_display} key configured in Map Agent.\n\nWould you like to route Coding Agents through your existing {vendor_display} configuration?",
                ok=f"Use Map {vendor_display}",
                cancel="Other / Custom...",
            )
            if use_map == 1:
                preset_match = next((p for p in modules.PRESETS if vendor_display.lower() in p["name"].lower()), None)
                if preset_match:
                    name = preset_match["name"]
                    model = map_model or preset_match["model"]
                    anthropic_url = preset_match.get("anthropic_url", "")
                    openai_url = preset_match.get("openai_url", "")
                else:
                    name = f"{vendor_display} (Synced)"
                    model = map_model or "default"
                    anthropic_url = "https://api.anthropic.com/v1" if map_vendor == "anthropic" else ""
                    openai_url = "https://api.openai.com/v1" if map_vendor == "openai" else ""
                key = map_key
                try:
                    module = modules.add_module(self.config, name, model, key, anthropic_url, openai_url)
                    self.config.set("module_selected", module["id"])
                    self.config.set("modules_enabled", True)
                    self._update_modules_menu()
                    self._update_brain_checks()
                    self._update_models_menu()
                    rumps.notification("codebone", "Coding Agent Synced", f"Now using {name} for coding agents.")
                    return
                except Exception as exc:
                    logger.warning("Could not sync Map Agent model to coding agent: %s", exc)

        name = model = anthropic_url = openai_url = None
        for i, preset in enumerate(modules.PRESETS):
            last = i == len(modules.PRESETS) - 1
            choice = rumps.alert(
                title="Add Coding Model",
                message=(f"This model API can be used by your coding agent instead of its default.\n\n"
                         f"Preset: {preset['name']}\nModel: {preset['model']}\n\n"
                         "Custom needs a base URL in Anthropic format (for Claude Code) and/or OpenAI format (for opencode)."),
                ok=preset["name"], cancel="Cancel", other=("Custom..." if last else "Other provider..."),
            )
            if choice == 0:
                return
            if choice == 1:
                name, model = preset["name"], preset["model"]
                anthropic_url = preset.get("anthropic_url", "")
                openai_url = preset.get("openai_url", "")
                break
            if last:
                name = ""  # falls through to the custom-entry form below
        if name is None or name == "":
            fields = []
            for label, default in (("Name (shown in the menu)", ""), ("Model ID", ""),
                                   ("Anthropic-format base URL (optional, https://...)", ""),
                                   ("OpenAI-format base URL (optional, https://...)", "")):
                resp = rumps.Window(message=label, title="Add Coding Model", default_text=default, ok="Next", cancel="Cancel",
                                    dimensions=(360, 24)).run()
                if not resp.clicked:
                    return
                fields.append(resp.text.strip())
            name, model, anthropic_url, openai_url = fields
        resp = rumps.Window(message=f"API key for {name} (stored in your macOS Keychain)",
                            title="Add Coding Model", default_text="", ok="Add", cancel="Cancel", dimensions=(360, 24),
                            secure=True).run()
        if not resp.clicked:
            return
        key = resp.text.strip()
        try:
            module = modules.add_module(self.config, name, model, key, anthropic_url, openai_url)
            self.config.set("module_selected", module["id"])
        except (ValueError, RuntimeError) as exc:
            rumps.alert("Add Model", str(exc))
            return
        self._update_modules_menu()
        self._update_brain_checks()
        self._update_models_menu()
        self._check_module(module, key)

    def _check_module(self, module: dict, key: str):
        from . import modules

        def _run():
            results = []
            try:
                for fmt in ("anthropic", "openai"):
                    url = modules._url(module, fmt, self.server.port if getattr(self, "server", None) else None)
                    if not url:
                        continue
                    ok, msg = modules.test_connection(url, module["model"], key, fmt=fmt)
                    results.append((fmt, ok, msg))
            except Exception as exc:  # a dead notification center must never make this look like nothing happened
                results.append(("error", False, str(exc)))

            def _show():
                if not results:
                    rumps.notification("codebone", "Test Connection", f"{module['name']} has no Anthropic- or OpenAI-format URL to test.")
                    return
                all_ok = all(ok for _, ok, _ in results)
                lines = [f"{modules.FORMAT_NAMES.get(fmt, fmt)}: {'OK' if ok else 'failed'} — {msg}" for fmt, ok, msg in results]
                rumps.notification(
                    "codebone",
                    f"{module['name']}: {'Connection Verified' if all_ok else 'Connection Failed'}",
                    " · ".join(lines),
                )

            self._on_main(_show)

        threading.Thread(target=_run, daemon=True, name="codebone-module-test").start()

    def test_selected_module(self, _, target_mod: Optional[dict] = None):
        from . import modules

        module = target_mod or modules.get_module(self.config, self.config.get("module_selected"))
        key = modules.Keychain().get(module["id"]) if module else None
        if not module or not key:
            rumps.alert("Model Test", "Select a model with a stored key first.")
            return
        self._check_module(module, key)

    def remove_module_dialog(self, module_id: str, name: str):
        from . import modules

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if rumps.alert("Remove Model", f"Remove '{name}', switch its apps back and delete its API key?", ok="Remove", cancel="Cancel") != 1:
            return
        try:
            modules.remove_module(self.config, module_id)
        except modules.SettingsUnreadable as exc:
            rumps.alert("Model", str(exc))
        self._update_modules_menu()
        self._update_brain_checks()
        self._update_models_menu()

    def clear_recent_projects(self, _):
        """Explain the scope before clearing only the three recent main-menu shortcuts."""
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if rumps.alert(
            "Clear Recent Projects?",
            "This only removes the three recent project shortcuts from the main menu.\n\n"
            "Your Projects list, saved maps and source folders stay untouched.",
            ok="Clear",
            cancel="Cancel",
        ) != 1:
            return
        self.config.clear_recent_projects()
        self._update_ui_state()
        rumps.notification("codebone", "Recent Shortcuts Cleared", "Projects and saved maps were not changed.")

    def choose_project(self, _):
        paths = _choose_folders("Select Project Folders to Scan", multi=True)
        if not paths:
            return
        if len(paths) == 1:
            # One folder keeps the guided flow: TCC dialog, baseline overview, snapshot adoption
            self.open_project_path(Path(paths[0]))
            return

        # Several folders at once: add them to the workspace, activate the first, scan isolated indexes in parallel
        accessible, blocked = [], []
        for p_str in paths:
            ok, _reason = check_folder_access(Path(p_str))
            (accessible if ok else blocked).append(p_str)
        if blocked:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert(
                "Disk Access Restricted",
                f"{len(blocked)} selected folder(s) cannot be read by codebone yet.\n\n"
                "Enable Full Disk Access for codebone in macOS settings and add the folders again.\n\n"
                + "\n".join(Path(p).name for p in blocked),
            )
        if not accessible:
            return
        for p_str in accessible:
            self.config.add_project_path(p_str)
        self.config.set("project_path", accessible[0])
        self.service.start(auto_scan=False)  # aborts a running scan, rebinds the index, watches the first folder
        self._update_ui_state()
        rumps.notification(
            "codebone", "Workspace Updated",
            f"{len(accessible)} folders queued — scanning them now.",
        )
        self._run_workspace_scan()

    def open_project_path(self, p: Path):
        """Activates and switches to the specified project folder."""
        if not p or not p.exists():
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            rumps.alert("Project Not Found", f"The folder '{p}' no longer exists on disk.")
            self.config.remove_recent_project(str(p))
            self._update_projects_menu()
            return

        current_proj = self.config.project_path
        if current_proj and current_proj.resolve() == p.resolve() and self.service.watching:
            # Scan and TLDR have their own visible actions in the Projects menu; selecting the already-active
            # project is intentionally a no-op instead of triggering an unexpected expensive scan.
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
                "Updating existing index...",
            )

            def _run_matched():
                try:
                    rep = self.service.adopt_scan(matching["id"])
                    reused = rep.get("reused_count", 0)
                    renamed = rep.get("renamed_count", 0)
                    modified = rep.get("modified_count", 0)
                    added = rep.get("added_count", 0)
                    conn_count = len(self.service.storage.graph_edges(include_domains=True))
                    rumps.notification(
                        "codebone — Earlier Scan Reused",
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
                f"codebone — Scan Started",
                f"{p.name} ({total} files, {langs})",
                f"Scanning files and connections...",
            )

            def _run_initial():
                import time
                t0 = time.time()
                try:
                    def _on_prog(cur, tot, f):
                        self._on_main(self._push_stats)

                    total_scanned, sniffed, skipped = self.service.rescan_all(on_progress=_on_prog, wait=True)
                    dur = max(1, round(time.time() - t0))
                    conn_count = len(self.service.storage.graph_edges(include_domains=True))
                    rumps.notification(
                        f"codebone — Scan Complete",
                        f"{p.name} ready ({total_scanned} files)",
                        f"Scanned {total_scanned} files & {conn_count} connections in {dur}s. Live watching active.",
                    )
                except Exception as exc:
                    logger.exception("Initial baseline scan failed")
                    rumps.notification("codebone — Scan Error", str(exc), "")
                finally:
                    self._on_main(self._update_ui_state)

            threading.Thread(target=_run_initial, daemon=True, name="codebone-initial-scan").start()

    def choose_adopt_scan(self, _):
        if not self.config.is_configured:
            path = choose_folder("Select Project Folder")
            if not path:
                return
            self.config.set("project_path", path)
            self.service.start(auto_scan=False)
            self._update_ui_state()

        scans = self.service.scans.list_scans()
        source_target = None

        if scans:
            msg_lines = ["Merge files, connections, and architectural domains from an earlier scan into the current project:\n"]
            for i, s in enumerate(scans[:8], 1):
                name = s.get("project_name", "Unknown")
                f_count = s.get("file_count", 0)
                domains = ", ".join(s.get("domains", [])[:2]) or "no domains"
                msg_lines.append(f"{i}. {name} ({f_count} files, {domains})")
            msg_lines.append("\nEnter number (or leave empty to browse for a .sqlite3 file):")

            window = rumps.Window(
                message="\n".join(msg_lines),
                title="Merge with Previous Scan",
                default_text="1",
                ok="Merge Scan",
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
            f_path = choose_file("Select Existing Scan Database to Merge (.sqlite3)", ["sqlite3", "db", "sqlite"])
            if not f_path:
                return
            source_target = f_path

        def _run_adopt():
            rumps.notification(
                "codebone",
                "Merging Previous Scan",
                "Comparing files and merging saved graph insights...",
            )
            try:
                rep = self.service.adopt_scan(source_target)
                reused = rep.get("reused_count", 0)
                renamed = rep.get("renamed_count", 0)
                modified = rep.get("modified_count", 0)
                added = rep.get("added_count", 0)
                rumps.notification(
                    "codebone",
                    "Scan Merged Successfully",
                    f"{reused} files merged, {renamed} renamed, {modified} modified, {added} added.",
                )
                self._on_main(self._update_ui_state)
            except Exception as exc:
                logger.exception("Error during scan merge: %s", exc)
                rumps.notification("codebone", "Merge Failed", str(exc))

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

    def open_mcp_setup(self, _=None):
        """Re-patches MCP configs for installed coding agents without navigating away."""
        try:
            from .server import patch_mcp_configs
            server_port = getattr(getattr(self, "server", None), "port", None) or self.config.get("active_port") or self.config.get("server_port", 8053)
            patch_mcp_configs(server_port)
            rumps.notification("codebone", "Coding Agents Connected", "MCP configured for Claude Desktop, Claude Code, Cursor, Antigravity & Codex.")
        except Exception as exc:
            logger.warning("Could not patch MCP configs during open_mcp_setup: %s", exc)

    def view_live_graph(self, _=None):
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
        port = getattr(getattr(self, "server", None), "port", None) or self.config.get("active_port") or self.config.get("server_port", 8053)
        url = f"http://127.0.0.1:{port}/codebone/graph/ui"
        try:
            subprocess.Popen(["open", url])
        except Exception as exc:
            logger.error("Failed to open graph UI: %s", exc)

    def view_logs(self, _=None):
        try:
            NSMenu.cancelTracking()
        except Exception:
            pass
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
                "connection_count": len(self.service.storage.graph_edges(include_domains=True)) if self.config.is_configured else 0,
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
            NSMenu.cancelTracking()
        except Exception:
            pass
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
            self.config.set("brain_tested_signature", "")
            self._update_brain_checks()
            self.service.reload_provider()
            self._test_brain(f"Local server ({resp.text.strip()})")

    def select_brain_cloud(self, _):
        current_vendor = self.config.get("brain_cloud_vendor", "openai")
        current_key = self.config.get("brain_cloud_api_key", "")
        window = rumps.Window(
            message="Enter your API key:\nFormat: 'openai:sk-...', 'anthropic:sk-ant-...' or 'openrouter:sk-or-...'",
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
            defaults = {vendor_id: model for vendor_id, _label, model in self.BRAIN_PROFILES}
            if vendor not in defaults:
                rumps.alert("Cloud BYOK", "Provider must be openai, anthropic or openrouter.")
                return
            self.config.set("brain_cloud_vendor", vendor)
            self.config.set("brain_cloud_model", defaults[vendor])
            self.config.set("brain_cloud_api_key", api_key)
            self.config.set("brain_provider", "cloud")
            self.config.set("brain_tested_signature", "")
            self._update_brain_checks()
            self.service.reload_provider()
            self._test_brain(f"Cloud ({vendor.upper()})")

    def add_model_file(self, _):
        path = choose_file("Select .gguf Model File", ["gguf"])
        if path:
            entry = self.config.add_model(path)
            self.config.select_model(path)
            self.config.set("brain_provider", "builtin")
            self.config.set("brain_tested_signature", "")
            self._update_brain_checks()
            self.service.reload_provider()
            self._test_brain(f"Local model ({entry['name']})")

    def reset_map(self, _):
        self.service.reset_map()
        self._update_ui_state()
        rumps.notification("codebone", "Map reset", "Saved index cleared.")
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
