#!/usr/bin/env python3
"""Flache - a floating dock for the applications you choose - v1.2.2

Flache (pronounced "flash") is a small panel of application icons that
floats above every window on every Space.  A click opens the application; a
right-click offers Help, Delete, New and the three arrangements: a
horizontal strip, a vertical column or a square grid.  The whole panel is
shown and hidden by one system-wide chord, ⌃⌥⌘F unless another is recorded
in Preferences, and it can be dragged anywhere; each arrangement remembers
where it was left.

Flache is an accessory application: no Dock icon and no menu bar of its
own, only the Old English F in the menu bar and the panel itself.  Like
Stache it needs NO permissions.  The chord is a Carbon hot key, which the
window server delivers without Accessibility, and opening an application is
an ordinary NSWorkspace request.

Settings live in the com.timmccoy.flache defaults domain:
    FlacheApps          the applications, in order: [{path, bundle}, ...]
    FlacheLayout        strip | column | grid
    FlacheIconSize      small | medium | large
    FlacheHotKeyCode    Carbon key code of the chord
    FlacheHotKeyMods    Carbon modifier mask of the chord
    FlacheVisible       whether the panel was showing at quit
    FlacheTopLeft-<layout>   where each arrangement was left, "x,y"
"""

import math
import os
import subprocess
import sys
import ctypes

import objc
from AppKit import (
    NSAlert, NSApp, NSApplication, NSBeep, NSBitmapImageRep,
    NSDeviceRGBColorSpace, NSGraphicsContext, NSBackingStoreBuffered, NSBezierPath,
    NSButton, NSColor, NSDragOperationCopy, NSDragOperationNone, NSEvent,
    NSEventMaskKeyDown, NSEventModifierFlagCommand, NSEventModifierFlagControl,
    NSEventModifierFlagOption, NSEventModifierFlagShift, NSFont, NSImage,
    NSMenu, NSMenuItem, NSOpenPanel, NSPanel, NSPasteboardTypeFileURL,
    NSPopUpButton, NSRunningApplication, NSScreen, NSScrollView, NSStatusBar, NSTextField,
    NSTextView, NSVariableStatusItemLength, NSView, NSVisualEffectView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
    NSWindowStyleMaskClosable, NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskResizable, NSWindowStyleMaskTitled,
    NSWindowStyleMaskUtilityWindow, NSWorkspace, NSWorkspaceOpenConfiguration,
    NSFloatingWindowLevel, NSFontAttributeName, NSForegroundColorAttributeName,
    NSAttributedString, NSMutableAttributedString, NSParagraphStyleAttributeName,
    NSMutableParagraphStyle, NSEdgeInsetsMake,
)
from Foundation import (
    NSBundle, NSFileManager, NSMakePoint, NSMakeRect, NSMakeSize,
    NSNotificationCenter, NSObject, NSString, NSURL, NSUserDefaults,
)

APP_NAME = "Flache"
APP_VERSION = "1.2.2"
BUNDLE_ID = "com.timmccoy.flache"
AGENT_PLIST = os.path.expanduser(
    "~/Library/LaunchAgents/%s.plist" % BUNDLE_ID)

DEF_APPS = "FlacheApps"
DEF_LAYOUT = "FlacheLayout"
DEF_ICON_SIZE = "FlacheIconSize"
DEF_HOTKEY_CODE = "FlacheHotKeyCode"
DEF_HOTKEY_MODS = "FlacheHotKeyMods"
DEF_VISIBLE = "FlacheVisible"
DEF_TOP_LEFT = "FlacheTopLeft-"          # + layout

LAYOUTS = ("strip", "column", "grid")
ICON_SIZES = {"small": 32, "medium": 48, "large": 64}

# ⌃⌥⌘F: key code 3 is F on every layout Apple ships.
cmdKey, shiftKey, optionKey, controlKey = 0x0100, 0x0200, 0x0800, 0x1000
DEFAULT_HOTKEY = (3, controlKey | optionKey | cmdKey)

# Stache's chord, so Flache never claims the same one.
STACHE_DOMAIN = "com.timmccoy.stache"
STACHE_DEFAULT_HOTKEY = (49, controlKey | optionKey | cmdKey)   # ⌃⌥⌘Space

DEFAULTS = {
    DEF_APPS: [],
    DEF_LAYOUT: "strip",
    DEF_ICON_SIZE: "medium",
    DEF_HOTKEY_CODE: DEFAULT_HOTKEY[0],
    DEF_HOTKEY_MODS: DEFAULT_HOTKEY[1],
    DEF_VISIBLE: True,
}

CELL_PAD = 2              # around each icon, inside its cell
EDGE = 4                  # between the cells and the panel's edge
GRIP = 10                 # each grip the panel is dragged by
GAP = 10                  # room opened for the blue bar while placing
CORNER = 10               # the panel's corner radius
SCREEN_MARGIN = 8         # how close the panel may come to a screen edge
DRAG_SLOP = 3.0           # points the pointer may wander and still click
MENU_BAR_HEIGHT = 18.0    # points; the glyph PNG is rendered at 2x


def defaults():
    return NSUserDefaults.standardUserDefaults()


def pref(key):
    value = defaults().objectForKey_(key)
    return DEFAULTS.get(key) if value is None else value


def set_pref(key, value):
    defaults().setObject_forKey_(value, key)


def layout_pref():
    value = str(pref(DEF_LAYOUT))
    return value if value in LAYOUTS else "strip"


def icon_px():
    return ICON_SIZES.get(str(pref(DEF_ICON_SIZE)), ICON_SIZES["medium"])


# ---------------------------------------------------------------------------
# The applications
# ---------------------------------------------------------------------------
#
# Each entry keeps the bundle identifier beside the path, so an application
# that is moved or updated in place is found again rather than going blank.

def saved_apps():
    out = []
    for entry in pref(DEF_APPS) or []:
        try:
            path = str(entry["path"])
        except (KeyError, TypeError):
            continue
        bundle = entry.get("bundle")
        out.append({"path": path, "bundle": str(bundle) if bundle else ""})
    return out


def set_saved_apps(apps):
    set_pref(DEF_APPS, [{"path": a["path"], "bundle": a.get("bundle", "")}
                        for a in apps])


def bundle_id_of(path):
    bundle = NSBundle.bundleWithPath_(path)
    ident = bundle.bundleIdentifier() if bundle is not None else None
    return str(ident) if ident else ""


def resolve(entry):
    """The application's current path, or None if it cannot be found.

    A missing path falls back to the bundle identifier, and the entry is
    updated in place so the new path is what gets saved.
    """
    if os.path.isdir(entry["path"]):
        return entry["path"]
    if entry.get("bundle"):
        url = NSWorkspace.sharedWorkspace(). \
            URLForApplicationWithBundleIdentifier_(entry["bundle"])
        if url is not None:
            entry["path"] = str(url.path())
            return entry["path"]
    return None


def app_name(path):
    name = str(NSFileManager.defaultManager().displayNameAtPath_(path))
    return name[:-4] if name.endswith(".app") else name


def insert_apps(apps, paths, at=None):
    """Add applications at index `at` (the end if None), skipping any that
    are already in the list.  Returns how many were added."""
    have = {os.path.realpath(a["path"]) for a in apps}
    at = len(apps) if at is None else max(0, min(len(apps), at))
    added = 0
    for path in paths:
        path = str(path).rstrip("/")
        if not path.endswith(".app") or os.path.realpath(path) in have:
            continue
        apps.insert(at + added, {"path": path, "bundle": bundle_id_of(path)})
        have.add(os.path.realpath(path))
        added += 1
    return added


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
#
# Pure functions of the count, the arrangement and the icon size, so they
# can be tested without a window.  The dock view is flipped: row 0 is the
# top row.  An empty Flache still has one cell, the "+" that adds an app.
#
# Dragging an icon rearranges the icons, so the panel itself is moved by
# its grips: a dotted bar at both ends of a strip, and along the top and
# bottom of a column or a grid.
#
# While an icon is being placed, the icons part at the insertion point to
# open a GAP for the blue bar, and the panel grows by that much to hold it.
# `gap_at` is that insertion point, or None when nothing is being placed.
# Hit-testing always uses the closed layout, so the gap opening under the
# pointer cannot move the insertion point and set it flickering.

def grip_offset(layout):
    """(dx, dy) the leading grip pushes the cells by."""
    return (GRIP, 0) if layout == "strip" else (0, GRIP)


def grip_rects(layout, w, h):
    """The two grips, leading and trailing, as (x, y, w, h) in a (w x h)
    dock view."""
    if layout == "strip":
        return [(0, 0, EDGE + GRIP, h), (w - EDGE - GRIP, 0, EDGE + GRIP, h)]
    return [(0, 0, w, EDGE + GRIP), (0, h - EDGE - GRIP, w, EDGE + GRIP)]


def grid_shape(count, layout):
    """(rows, columns) for `count` applications."""
    n = max(1, count)
    if layout == "column":
        return n, 1
    if layout == "grid":
        cols = int(math.ceil(math.sqrt(n)))
        return int(math.ceil(n / float(cols))), cols
    return 1, n


def cell_size(icon):
    return icon + 2 * CELL_PAD


def content_size(count, layout, icon, gap=False):
    rows, cols = grid_shape(count, layout)
    c = cell_size(icon)
    dx, dy = grip_offset(layout)
    w, h = cols * c + 2 * EDGE + 2 * dx, rows * c + 2 * EDGE + 2 * dy
    if gap:
        if layout == "column":
            h += GAP
        else:
            w += GAP
    return w, h


def cell_rect(index, count, layout, icon, gap_at=None):
    """(x, y, w, h) of a cell, in the flipped dock view.  With `gap_at`,
    the cells from that insertion point on are pushed along by GAP: down a
    column, or along the row it falls in."""
    rows, cols = grid_shape(count, layout)
    row, col = divmod(index, cols)
    c = cell_size(icon)
    dx, dy = grip_offset(layout)
    x, y = EDGE + dx + col * c, EDGE + dy + row * c
    if gap_at is not None and index >= gap_at:
        if layout == "column":
            y += GAP
        elif row == gap_at // cols:
            x += GAP
    return x, y, c, c


def index_at(x, y, count, layout, icon):
    """Which cell holds the point, or None for the margin or an empty slot."""
    rows, cols = grid_shape(count, layout)
    c = cell_size(icon)
    dx, dy = grip_offset(layout)
    col = int(math.floor((x - EDGE - dx) / c))
    row = int(math.floor((y - EDGE - dy) / c))
    if not (0 <= col < cols and 0 <= row < rows):
        return None
    index = row * cols + col
    return index if index < max(1, count) else None


def insertion_index(x, y, count, layout, icon):
    """Where a dropped application goes: before the cell under the point if
    it lands in that cell's leading half, otherwise after it."""
    if count == 0:
        return 0
    index = index_at(x, y, count, layout, icon)
    if index is None:
        return count
    cx, cy, c, _ = cell_rect(index, count, layout, icon)
    leading = (y - cy) < c / 2.0 if layout == "column" else (x - cx) < c / 2.0
    return index if leading else index + 1


def move_index(src, at):
    """The index an item taken from `src` ends up at when it is dropped at
    insertion point `at`, counted before it was taken out."""
    return at - 1 if at > src else at


def move_item(apps, src, at):
    """Move apps[src] to insertion point `at`.  True if the order changed."""
    dst = move_index(src, at)
    if dst == src or not (0 <= src < len(apps)):
        return False
    apps.insert(dst, apps.pop(src))
    return True


def clamp_origin(x, y, w, h, visible):
    """Keep a (w x h) window whose origin is (x, y) wholly on the visible
    rectangle (vx, vy, vw, vh), in screen coordinates."""
    vx, vy, vw, vh = visible
    x = max(vx + SCREEN_MARGIN, min(x, vx + vw - w - SCREEN_MARGIN))
    y = max(vy + SCREEN_MARGIN, min(y, vy + vh - h - SCREEN_MARGIN))
    return x, y


def default_top_left(layout, w, h, visible):
    """Where an arrangement appears before it has ever been moved: a strip
    along the top, centred; a column down the left edge; a grid centred."""
    vx, vy, vw, vh = visible
    top = vy + vh - SCREEN_MARGIN
    if layout == "column":
        return vx + SCREEN_MARGIN, top - max(0, (vh - h) / 4.0)
    if layout == "grid":
        return vx + (vw - w) / 2.0, vy + (vh + h) / 2.0
    return vx + (vw - w) / 2.0, top


def _rect_tuple(rect):
    return (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)


def screen_for_point(x, y):
    """The visible frame of the screen holding the point, else the main one."""
    for screen in NSScreen.screens() or []:
        fx, fy, fw, fh = _rect_tuple(screen.frame())
        if fx <= x <= fx + fw and fy <= y <= fy + fh:
            return _rect_tuple(screen.visibleFrame())
    return _rect_tuple(NSScreen.mainScreen().visibleFrame())


def saved_top_left(layout):
    value = defaults().stringForKey_(DEF_TOP_LEFT + layout)
    if not value:
        return None
    try:
        x, y = (float(v) for v in str(value).split(","))
    except ValueError:
        return None
    return x, y


# ---------------------------------------------------------------------------
# Global hot key (Carbon)
# ---------------------------------------------------------------------------
#
# RegisterEventHotKey claims a system-wide chord without Accessibility, and
# the window server swallows the keystroke so it never reaches the app
# underneath.  PyObjC does not wrap the Carbon Event Manager, hence ctypes.

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")

kEventClassKeyboard = 0x6B657962         # 'keyb'
kEventHotKeyPressed = 5


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p)

_carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
_carbon.RegisterEventHotKey.argtypes = [
    ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID, ctypes.c_void_p,
    ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
_carbon.RegisterEventHotKey.restype = ctypes.c_int32
_carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
_carbon.UnregisterEventHotKey.restype = ctypes.c_int32
_carbon.InstallEventHandler.argtypes = [
    ctypes.c_void_p, _HANDLER, ctypes.c_ulong,
    ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p)]
_carbon.InstallEventHandler.restype = ctypes.c_int32


class HotKey(object):
    """One registered chord.  The ctypes callback must stay referenced: if
    Python collects it the window server calls a freed trampoline and the
    app dies the first time the chord is pressed."""

    def __init__(self, callback):
        self._callback = callback
        self._ref = ctypes.c_void_p()
        self._registered = False
        self._trampoline = _HANDLER(self._fire)
        spec = _EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
        handler_ref = ctypes.c_void_p()
        _carbon.InstallEventHandler(
            _carbon.GetApplicationEventTarget(), self._trampoline, 1,
            ctypes.byref(spec), None, ctypes.byref(handler_ref))

    def _fire(self, next_handler, event, user_data):
        try:
            self._callback()
        except Exception as exc:                      # never let it reach C
            sys.stderr.write("Flache: hotkey handler: %r\n" % (exc,))
        return 0                                      # noErr

    def register(self, key_code, modifiers):
        self.unregister()
        hk_id = _EventHotKeyID(0x464C5348, 1)         # 'FLSH'
        status = _carbon.RegisterEventHotKey(
            int(key_code), int(modifiers), hk_id,
            _carbon.GetApplicationEventTarget(), 0, ctypes.byref(self._ref))
        self._registered = (status == 0)
        return self._registered

    def unregister(self):
        if self._registered and self._ref:
            _carbon.UnregisterEventHotKey(self._ref)
        self._registered = False
        self._ref = ctypes.c_void_p()


KEY_NAMES = {
    36: "Return", 48: "Tab", 49: "Space", 51: "Delete", 53: "Esc",
    76: "Enter", 96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8",
    101: "F9", 103: "F11", 105: "F13", 107: "F14", 109: "F10", 111: "F12",
    113: "F15", 114: "Help", 115: "Home", 116: "Page Up", 117: "Fwd Del",
    118: "F4", 119: "End", 120: "F2", 121: "Page Down", 122: "F1",
    123: "Left", 124: "Right", 125: "Down", 126: "Up",
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X", 8: "C",
    9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R", 16: "Y", 17: "T",
    18: "1", 19: "2", 20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9",
    26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "O", 32: "U", 33: "[",
    34: "I", 35: "P", 37: "L", 38: "J", 39: "'", 40: "K", 41: ";", 42: "\\",
    43: ",", 44: "/", 45: "N", 46: "M", 47: ".", 50: "`",
}


def hotkey_label(code, mods):
    out = ""
    if mods & controlKey:
        out += "⌃"
    if mods & optionKey:
        out += "⌥"
    if mods & shiftKey:
        out += "⇧"
    if mods & cmdKey:
        out += "⌘"
    return out + KEY_NAMES.get(int(code), "Key %d" % code)


def carbon_mods(ns_flags):
    mods = 0
    if ns_flags & NSEventModifierFlagCommand:
        mods |= cmdKey
    if ns_flags & NSEventModifierFlagShift:
        mods |= shiftKey
    if ns_flags & NSEventModifierFlagOption:
        mods |= optionKey
    if ns_flags & NSEventModifierFlagControl:
        mods |= controlKey
    return mods


def current_hotkey():
    return int(pref(DEF_HOTKEY_CODE)), int(pref(DEF_HOTKEY_MODS))


def stache_hotkey():
    """Stache's chord as Stache has it saved, or its default."""
    stache = NSUserDefaults.alloc().initWithSuiteName_(STACHE_DOMAIN)
    code = stache.objectForKey_("StacheHotKeyCode") if stache else None
    mods = stache.objectForKey_("StacheHotKeyMods") if stache else None
    if code is None or mods is None:
        return STACHE_DEFAULT_HOTKEY
    return int(code), int(mods)


# ---------------------------------------------------------------------------
# The dock view
# ---------------------------------------------------------------------------

INK_SIDE = 128            # pixels the icon is measured at
INK_ALPHA = 128           # opacity that counts as art rather than shadow


def ink_rect(image):
    """The square part of an icon that holds its art, in the image's own
    coordinates.

    macOS icons sit on an 824-in-1024 grid, so about a tenth of every side
    is transparent; drawn whole, that margin is most of the space between
    icons.  Drawing only this square makes the art itself fill the cell.
    Icons without the margin (old full-bleed ones) come back whole.
    """
    size = image.size()
    whole = NSMakeRect(0, 0, size.width, size.height)
    rep = NSBitmapImageRep.alloc().\
        initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, INK_SIDE, INK_SIDE, 8, 4, True, False,
            NSDeviceRGBColorSpace, INK_SIDE * 4, 32)
    if rep is None or size.width <= 0 or size.height <= 0:
        return whole
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    image.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(0, 0, INK_SIDE, INK_SIDE), NSMakeRect(0, 0, 0, 0), 2, 1.0)
    NSGraphicsContext.restoreGraphicsState()
    # Faint pixels are the drop shadow baked into the margin, not art.
    alpha = bytes(rep.bitmapData())[3::4]
    solid = [a > INK_ALPHA for a in alpha]
    rows = [r for r in range(INK_SIDE)
            if any(solid[r * INK_SIDE:(r + 1) * INK_SIDE])]
    if not rows:
        return whole
    cols = [c for c in range(INK_SIDE)
            if any(solid[r * INK_SIDE + c] for r in rows)]
    left, right = cols[0], cols[-1] + 1
    top, bottom = rows[0], rows[-1] + 1               # bitmap rows run down
    side = max(right - left, bottom - top)
    cx, cy = (left + right) / 2.0, INK_SIDE - (top + bottom) / 2.0
    x = max(0.0, min(INK_SIDE - side, cx - side / 2.0))
    y = max(0.0, min(INK_SIDE - side, cy - side / 2.0))
    k = size.width / float(INK_SIDE)
    return NSMakeRect(x * k, y * k, side * k, side * k)


class DockView(NSView):
    """Every icon, drawn by one view.  A press that moves the pointer less
    than DRAG_SLOP is a click.  One that moves further drags: an icon is
    carried to a new slot, and anywhere else (the grip or the margin) the
    whole panel moves."""

    def initWithFrame_(self, frame):
        self = objc.super(DockView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.controller = None
        self._pressed = None
        self._drop_at = None
        self._start = None
        self._origin = None
        self._dragging = False
        self._moving = None                # index of the icon being carried
        self._cursor = None                # where it is, in view coordinates
        self.registerForDraggedTypes_([NSPasteboardTypeFileURL])
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        # The panel never becomes key, so every click is a "first" click.
        return True

    def mouseDownCanMoveWindow(self):
        return False

    # -- drawing ----------------------------------------------------------

    def drawRect_(self, rect):
        ctrl = self.controller
        if ctrl is None:
            return
        apps, layout, icon = ctrl.apps, layout_pref(), icon_px()
        count = len(apps)
        self._drawGrips()
        if count == 0:
            self._drawPlus_(cell_rect(0, 0, layout, icon))
        for i, entry in enumerate(apps):
            x, y, c, _ = cell_rect(i, count, layout, icon, self._drop_at)
            if i == self._pressed:
                NSColor.labelColor().colorWithAlphaComponent_(0.18).set()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(x + 1, y + 1, c - 2, c - 2), 8, 8).fill()
            alpha = 1.0 if ctrl.isPresent_(entry) else 0.3
            if i == self._moving:
                alpha = 0.25                     # the slot it is leaving
            ctrl.iconFor_(entry).\
                drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                    NSMakeRect(x + CELL_PAD, y + CELL_PAD, icon, icon),
                    ctrl.inkFor_(entry), 2, alpha, True, None)
        if self._drop_at is not None:
            self._drawDropMarker()
        if self._moving is not None and self._cursor is not None:
            ctrl.iconFor_(apps[self._moving]).\
                drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                    NSMakeRect(self._cursor.x - icon / 2.0,
                               self._cursor.y - icon / 2.0, icon, icon),
                    ctrl.inkFor_(apps[self._moving]), 2, 0.85, True, None)

    def _drawGrips(self):
        """Two rows of dots across each grip, like a handle."""
        layout = layout_pref()
        size = self.bounds().size
        NSColor.tertiaryLabelColor().set()
        step, dot = 5.0, 2.0
        for gx, gy, gw, gh in grip_rects(layout, size.width, size.height):
            if layout == "strip":
                span = min(gh - 2 * EDGE, 40.0)
                mid = gx + gw / 2.0
                start = gy + (gh - span) / 2.0
                for lx in (mid - 2.5, mid + 2.5):
                    y = start
                    while y <= start + span:
                        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(
                            lx - dot / 2.0, y - dot / 2.0, dot, dot)).fill()
                        y += step
            else:
                span = min(gw - 2 * EDGE, 40.0)
                mid = gy + gh / 2.0
                start = gx + (gw - span) / 2.0
                for ly in (mid - 2.5, mid + 2.5):
                    x = start
                    while x <= start + span:
                        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(
                            x - dot / 2.0, ly - dot / 2.0, dot, dot)).fill()
                        x += step

    def _drawPlus_(self, cell):
        x, y, c, _ = cell
        box = NSMakeRect(x + CELL_PAD, y + CELL_PAD,
                         c - 2 * CELL_PAD, c - 2 * CELL_PAD)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            box, 8, 8)
        path.setLineWidth_(1.5)
        path.setLineDash_count_phase_([4.0, 3.0], 2, 0.0)
        NSColor.secondaryLabelColor().set()
        path.stroke()
        mid_x, mid_y = x + c / 2.0, y + c / 2.0
        arm = (c - 2 * CELL_PAD) * 0.22
        plus = NSBezierPath.bezierPath()
        plus.setLineWidth_(2.0)
        plus.moveToPoint_(NSMakePoint(mid_x - arm, mid_y))
        plus.lineToPoint_(NSMakePoint(mid_x + arm, mid_y))
        plus.moveToPoint_(NSMakePoint(mid_x, mid_y - arm))
        plus.lineToPoint_(NSMakePoint(mid_x, mid_y + arm))
        plus.stroke()

    def _drawDropMarker(self):
        ctrl = self.controller
        layout, icon, count = layout_pref(), icon_px(), len(ctrl.apps)
        at = self._drop_at
        if count == 0:
            x, y, c, _ = cell_rect(0, 0, layout, icon)
            NSColor.controlAccentColor().set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x + 1, y + 1, c - 2, c - 2), 8, 8).stroke()
            return
        # The bar stands in the middle of the gap: just before the cell at
        # the insertion point, or just after the last cell.
        ref = min(at, count - 1)
        x, y, c, _ = cell_rect(ref, count, layout, icon, at)
        after = at == count
        NSColor.controlAccentColor().set()
        if layout == "column":
            line_y = (y + c + GAP / 2.0 if after else y - GAP / 2.0) - 1
            NSBezierPath.fillRect_(NSMakeRect(x + 4, line_y, c - 8, 2))
        else:
            line_x = (x + c + GAP / 2.0 if after else x - GAP / 2.0) - 1
            NSBezierPath.fillRect_(NSMakeRect(line_x, y + 4, 2, c - 8))

    # -- mouse ------------------------------------------------------------

    def _setDropAt_(self, at):
        """Move the insertion point, opening or closing the gap for it."""
        was_open = self._drop_at is not None
        self._drop_at = at
        is_open = at is not None and bool(self.controller.apps)
        if is_open != was_open:
            self.controller.openGap_(is_open)
        self.setNeedsDisplay_(True)

    def _indexForEvent_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        return index_at(p.x, p.y, len(self.controller.apps),
                        layout_pref(), icon_px())

    def mouseDown_(self, event):
        if event.modifierFlags() & NSEventModifierFlagControl:
            self.rightMouseDown_(event)
            return
        self._pressed = self._indexForEvent_(event)
        self._start = NSEvent.mouseLocation()
        self._origin = self.window().frame().origin
        self._dragging = False
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        if self._start is None:
            return
        now = NSEvent.mouseLocation()
        dx, dy = now.x - self._start.x, now.y - self._start.y
        if not self._dragging and math.hypot(dx, dy) < DRAG_SLOP:
            return
        if not self._dragging:
            self._dragging = True
            # A press on an icon carries the icon; anywhere else, or on
            # the "+" of an empty Flache, moves the panel.
            if self._pressed is not None and self.controller.apps:
                self._moving = self._pressed
            self._pressed = None
            self.setNeedsDisplay_(True)
        if self._moving is not None:
            self._trackMove_(event)
            return
        self.window().setFrameOrigin_(
            NSMakePoint(self._origin.x + dx, self._origin.y + dy))

    def _trackMove_(self, event):
        """Follow the carried icon, and mark where it would land.  Carried
        off the panel it lands nowhere: letting go there changes nothing."""
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        self._cursor = p
        inside = self.mouse_inRect_(p, self.bounds())
        self._setDropAt_(insertion_index(p.x, p.y, len(self.controller.apps),
                                         layout_pref(), icon_px())
                         if inside else None)

    def mouseUp_(self, event):
        if self._start is None:
            return
        pressed, dragging = self._pressed, self._dragging
        moving, drop_at = self._moving, self._drop_at
        self._pressed, self._start, self._dragging = None, None, False
        self._moving, self._cursor = None, None
        self._setDropAt_(None)
        if moving is not None:
            if drop_at is not None:
                self.controller.moveApp_to_(moving, drop_at)
            return
        if dragging:
            self.controller.panelWasMoved()
            return
        if pressed is not None and pressed == self._indexForEvent_(event):
            if not self.controller.apps:
                self.controller.chooseAppsAt_(0)
            else:
                self.controller.launchAt_(pressed)

    def menuForEvent_(self, event):
        return self.controller.menuForIndex_(self._indexForEvent_(event))

    def rightMouseDown_(self, event):
        menu = self.menuForEvent_(event)
        if menu is not None:
            NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    # -- dropping applications from the Finder -----------------------------

    def _appPathsIn_(self, info):
        urls = info.draggingPasteboard().readObjectsForClasses_options_(
            [NSURL], None) or []
        return [str(u.path()) for u in urls
                if u.isFileURL() and str(u.path()).rstrip("/").endswith(".app")]

    def _dropIndexFor_(self, info):
        p = self.convertPoint_fromView_(info.draggingLocation(), None)
        return insertion_index(p.x, p.y, len(self.controller.apps),
                               layout_pref(), icon_px())

    def draggingEntered_(self, info):
        return self.draggingUpdated_(info)

    def draggingUpdated_(self, info):
        if not self._appPathsIn_(info):
            return NSDragOperationNone
        at = self._dropIndexFor_(info)
        if at != self._drop_at:
            self._setDropAt_(at)
        return NSDragOperationCopy

    def draggingExited_(self, info):
        self._setDropAt_(None)

    def performDragOperation_(self, info):
        paths = self._appPathsIn_(info)
        at = self._drop_at if self._drop_at is not None \
            else self._dropIndexFor_(info)
        self._setDropAt_(None)
        if not paths:
            return False
        self.controller.addPaths_at_(paths, at)
        return True

    def concludeDragOperation_(self, info):
        self._setDropAt_(None)


# ---------------------------------------------------------------------------
# The panel
# ---------------------------------------------------------------------------

class DockPanel(NSPanel):
    """Borderless and non-activating: clicking an icon opens its app without
    first pulling focus away from the one being worked in."""

    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


def rounded_mask(radius):
    """A stretchable rounded-rectangle mask for the visual effect view."""
    side = radius * 2 + 1

    def draw(rect):
        NSColor.blackColor().set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, radius, radius).fill()
        return True

    image = NSImage.imageWithSize_flipped_drawingHandler_(
        NSMakeSize(side, side), False, draw)
    image.setCapInsets_(NSEdgeInsetsMake(radius, radius, radius, radius))
    image.setResizingMode_(1)                    # NSImageResizingModeStretch
    return image


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

HELP_SECTIONS = [
    ("Flache", (
        "Flache (pronounced “flash”) is a dock for the applications you "
        "choose. It floats above every window on every Space, and a click "
        "on an icon opens that application, or brings it forward if it is "
        "already running.")),
    ("Showing and hiding it", (
        "Press %(hotkey)s from anywhere to show or hide Flache, or use "
        "the Old English F in the menu bar. The chord can be changed in "
        "Preferences.")),
    ("Always ready", (
        "The key sequence works only while Flache is running. Turn on "
        "“Open Flache at login” in Preferences and Flache starts when you "
        "log in and is restarted automatically if it ever stops "
        "unexpectedly. Quit Flache from the menu bar and it stays quit "
        "until you next log in. Adding Flache to Login Items as well is "
        "harmless; only one copy ever runs.")),
    ("Adding and removing applications", (
        "Right-click Flache and choose New… to pick applications; they go "
        "in after the icon you right-clicked, and applications already in "
        "Flache are grayed out. You can also drag "
        "applications from the Finder straight onto Flache — a blue line "
        "shows where they will land. Right-click an icon and choose "
        "Delete to take it out of Flache; the application itself is not "
        "touched.")),
    ("Strip, column or grid", (
        "Right-click and choose Strip for one row, Column for one column, "
        "or Grid for a square block. Icon size (small, medium or large) is "
        "in Preferences.")),
    ("Rearranging the icons", (
        "Drag an icon to a new place; the icons part and a blue line shows "
        "where it will land. "
        "Let go off Flache and nothing changes. The order is shared by the "
        "strip, the column and the grid.")),
    ("Moving it", (
        "Drag Flache by either of its grips, the dotted bars at both ends "
        "of a strip or along the top and bottom of a column or grid, or "
        "by its edge. Each "
        "arrangement remembers where you left it, so a strip along the top "
        "and a column down the side can each keep their own place.")),
    ("A faded icon", (
        "The application has been removed or moved somewhere Flache cannot "
        "find it. Right-click it and choose Delete, then add the "
        "application again.")),
]


def help_text(hotkey):
    out = NSMutableAttributedString.alloc().init()
    para = NSMutableParagraphStyle.alloc().init()
    para.setParagraphSpacing_(10)
    head = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(14),
            NSForegroundColorAttributeName: NSColor.labelColor(),
            NSParagraphStyleAttributeName: para}
    body = {NSFontAttributeName: NSFont.systemFontOfSize_(13),
            NSForegroundColorAttributeName: NSColor.labelColor(),
            NSParagraphStyleAttributeName: para}
    for title, text in HELP_SECTIONS:
        out.appendAttributedString_(NSAttributedString.alloc().
                                    initWithString_attributes_(title + "\n", head))
        out.appendAttributedString_(NSAttributedString.alloc().
                                    initWithString_attributes_(
                                        text % {"hotkey": hotkey} + "\n\n", body))
    return out


class HelpController(NSObject):

    def init(self):
        self = objc.super(HelpController, self).init()
        if self is None:
            return None
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 460, 420),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskResizable | NSWindowStyleMaskUtilityWindow,
            NSBackingStoreBuffered, False)
        panel.setTitle_("Flache Help")
        panel.setReleasedWhenClosed_(False)
        panel.setHidesOnDeactivate_(False)
        scroll = NSScrollView.alloc().initWithFrame_(
            panel.contentView().bounds())
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(18)          # width + height sizable
        text = NSTextView.alloc().initWithFrame_(scroll.bounds())
        text.setEditable_(False)
        text.setTextContainerInset_(NSMakeSize(16, 14))
        text.setAutoresizingMask_(2)
        scroll.setDocumentView_(text)
        panel.contentView().addSubview_(scroll)
        self.panel, self.text = panel, text
        return self

    def show(self):
        self.text.textStorage().setAttributedString_(
            help_text(hotkey_label(*current_hotkey())))
        self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

PREFS_W = 440
FIELD_X = 130
ROW_H = 34
TOP_PAD = 18
BOTTOM_PAD = 36


def _right_label(text, y, width=FIELD_X - 30):
    field = NSTextField.labelWithString_(text)
    field.setFrame_(NSMakeRect(18, y, width, 18))
    field.setAlignment_(1)                       # right
    return field


def _plain(text, x, y, width):
    field = NSTextField.labelWithString_(text)
    field.setFrame_(NSMakeRect(x, y, width, 18))
    field.setTextColor_(NSColor.secondaryLabelColor())
    field.setFont_(NSFont.systemFontOfSize_(11))
    return field


def _popup(titles, y, target, action):
    menu = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(FIELD_X, y, 150, 26), False)
    menu.addItemsWithTitles_(titles)
    menu.setTarget_(target)
    menu.setAction_(action)
    return menu


class PrefsController(NSObject):
    """Chord, arrangement, icon size and login item, in one small panel."""

    def initWithApp_(self, app):
        self = objc.super(PrefsController, self).init()
        if self is None:
            return None
        self.app = app
        self._monitor = None
        self._build()
        return self

    def _build(self):
        rows = 4
        height = TOP_PAD + rows * ROW_H + BOTTOM_PAD
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PREFS_W, height),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskUtilityWindow,
            NSBackingStoreBuffered, False)
        panel.setTitle_("Flache Preferences")
        panel.setReleasedWhenClosed_(False)
        # An accessory app stops being active at the slightest provocation,
        # and NSPanel hides itself whenever its app is not active.
        panel.setHidesOnDeactivate_(False)
        view = panel.contentView()

        def row(n):
            """The baseline of row n, counting from the top."""
            return height - TOP_PAD - (n + 1) * ROW_H

        view.addSubview_(_right_label("Show / hide:", row(0) + 6))
        self.hotkey_button = NSButton.alloc().initWithFrame_(
            NSMakeRect(FIELD_X, row(0), 150, 30))
        self.hotkey_button.setBezelStyle_(1)
        self.hotkey_button.setTarget_(self)
        self.hotkey_button.setAction_("recordHotkey:")
        view.addSubview_(self.hotkey_button)
        view.addSubview_(_plain("click, then press the chord",
                                FIELD_X + 158, row(0) + 7, 150))

        view.addSubview_(_right_label("Arrangement:", row(1) + 6))
        self.layout_menu = _popup(["Strip", "Column", "Grid"], row(1) + 1,
                                  self, "layoutChanged:")
        view.addSubview_(self.layout_menu)

        view.addSubview_(_right_label("Icon size:", row(2) + 6))
        self.size_menu = _popup(["Small", "Medium", "Large"], row(2) + 1,
                                self, "sizeChanged:")
        view.addSubview_(self.size_menu)

        self.login_item = NSButton.alloc().initWithFrame_(
            NSMakeRect(FIELD_X, row(3) + 6, 280, 20))
        self.login_item.setButtonType_(3)        # switch
        self.login_item.setTitle_("Open Flache at login")
        self.login_item.setTarget_(self)
        self.login_item.setAction_("loginItemChanged:")
        view.addSubview_(self.login_item)

        version = _plain("Flache %s" % APP_VERSION, PREFS_W - 130, 12, 112)
        version.setAlignment_(1)
        view.addSubview_(version)
        self.panel = panel

    def show(self):
        self.refresh()
        self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)

    def refresh(self):
        self.hotkey_button.setTitle_(hotkey_label(*current_hotkey()))
        self.layout_menu.selectItemAtIndex_(LAYOUTS.index(layout_pref()))
        self.size_menu.selectItemAtIndex_(
            ("small", "medium", "large").index(
                str(pref(DEF_ICON_SIZE))
                if str(pref(DEF_ICON_SIZE)) in ICON_SIZES else "medium"))
        self.login_item.setState_(1 if os.path.exists(AGENT_PLIST) else 0)

    # -- actions ----------------------------------------------------------

    def recordHotkey_(self, sender):
        if self._monitor is not None:
            return
        self.hotkey_button.setTitle_("Press a chord…")
        # While recording, the old chord must not fire and hide the panel.
        self.app.hotkey.unregister()

        def handler(event):
            code = int(event.keyCode())
            if code in (54, 55, 56, 57, 58, 59, 60, 61, 62, 63):
                return None                       # a modifier on its own
            mods = carbon_mods(event.modifierFlags())
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
            problem = chord_problem(code, mods)
            if problem is None and not self.app.hotkey.register(code, mods):
                problem = ("That chord is already taken",
                           "Another application has claimed %s. Choose a "
                           "different one." % hotkey_label(code, mods))
            if problem is not None:
                self.app.applyHotkey()           # back to the saved chord
                self.refresh()
                _alert(*problem)
                return None
            set_pref(DEF_HOTKEY_CODE, code)
            set_pref(DEF_HOTKEY_MODS, mods)
            self.app.applyHotkey()
            self.refresh()
            return None

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, handler)

    def layoutChanged_(self, sender):
        self.app.useLayout_(LAYOUTS[max(0, min(2, sender.indexOfSelectedItem()))])

    def sizeChanged_(self, sender):
        chosen = ("small", "medium", "large")[
            max(0, min(2, sender.indexOfSelectedItem()))]
        set_pref(DEF_ICON_SIZE, chosen)
        self.app.relayout()

    def loginItemChanged_(self, sender):
        if sender.state():
            install_login_item()
        else:
            remove_login_item()
        self.refresh()


def chord_problem(code, mods):
    """Why a recorded chord cannot be used, as (title, body), or None."""
    if mods == 0 or mods == shiftKey:
        # A bare key would be claimed system-wide and swallowed from every
        # app on the Mac.
        return ("That chord needs a modifier",
                "Hold at least one of ⌃ ⌥ ⌘ along with the key. A chord "
                "without one would be taken away from every other app.")
    if (code, mods) == stache_hotkey():
        # macOS lets two apps claim one chord and fires both, so a chord
        # known to be in use is refused here; the message names no app.
        return ("That chord is already in use",
                "%s is already used by another application. Choose a "
                "different chord for Flache." % hotkey_label(code, mods))
    return None


def _alert(title, body):
    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(body)
    alert.addButtonWithTitle_("OK")
    NSApp.activateIgnoringOtherApps_(True)
    alert.runModal()


# ---------------------------------------------------------------------------
# Login item
# ---------------------------------------------------------------------------

def _executable_path():
    return os.path.join(
        os.path.abspath(os.path.join(sys.argv[0], "..")), APP_NAME)


def install_login_item():
    """A LaunchAgent rather than a Login Item, so launchd relaunches
    Flache if it ever dies."""
    import plistlib
    os.makedirs(os.path.dirname(AGENT_PLIST), exist_ok=True)
    plist = {
        "Label": BUNDLE_ID,
        "ProgramArguments": [_executable_path()],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Interactive",
    }
    with open(AGENT_PLIST, "wb") as fh:
        plistlib.dump(plist, fh)
    target = "gui/%d" % os.getuid()
    subprocess.run(["/bin/launchctl", "bootout", target + "/" + BUNDLE_ID],
                   capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", target, AGENT_PLIST],
                   capture_output=True)


def remove_login_item():
    subprocess.run(["/bin/launchctl", "bootout",
                    "gui/%d/%s" % (os.getuid(), BUNDLE_ID)],
                   capture_output=True)
    try:
        os.unlink(AGENT_PLIST)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# The application
# ---------------------------------------------------------------------------

class AddPanelDelegate(NSObject,
                       protocols=[objc.protocolNamed("NSOpenSavePanelDelegate")]):
    """Grays out, in the Add dialog, every application already in Flache.
    Folders stay enabled so the dialog can still be navigated."""

    def initWithApps_(self, apps):
        self = objc.super(AddPanelDelegate, self).init()
        if self is None:
            return None
        self.have = {os.path.realpath(resolve(a) or a["path"]) for a in apps}
        return self

    def panel_shouldEnableURL_(self, sender, url):
        path = str(url.path()).rstrip("/")
        return not (path.endswith(".app") and
                    os.path.realpath(path) in self.have)


class FlacheApp(NSObject):

    def applicationDidFinishLaunching_(self, note):
        self.apps = saved_apps()
        self._icons = {}
        self.help = None
        self.prefs = None
        self._buildPanel()
        self._buildStatusItem()
        self.hotkey = HotKey(self.toggle)
        if not self.applyHotkey():
            # Say so, rather than leave a chord that silently does nothing.
            _alert("Flache’s key sequence is taken",
                   "Another application has claimed %s, so it will not show "
                   "or hide Flache. Choose a different one in Flache > "
                   "Preferences." % hotkey_label(*current_hotkey()))
        NSNotificationCenter.defaultCenter().\
            addObserver_selector_name_object_(
                self, "screensChanged:",
                "NSApplicationDidChangeScreenParametersNotification", None)
        if pref(DEF_VISIBLE):
            self.showPanel()

    # -- building ---------------------------------------------------------

    def _buildPanel(self):
        panel = DockPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 100, 100),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        panel.setLevel_(NSFloatingWindowLevel)
        panel.setFloatingPanel_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorFullScreenAuxiliary |
            NSWindowCollectionBehaviorStationary)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)

        effect = NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 100, 100))
        effect.setMaterial_(6)                   # popover: follows light/dark
        effect.setBlendingMode_(0)               # behind the window
        effect.setState_(1)                      # always active
        effect.setMaskImage_(rounded_mask(CORNER))
        panel.setContentView_(effect)

        view = DockView.alloc().initWithFrame_(effect.bounds())
        view.controller = self
        view.setAutoresizingMask_(18)
        effect.addSubview_(view)
        self.panel, self.view = panel, view

    def _buildStatusItem(self):
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        image = menu_bar_glyph()
        if image is not None:
            image.setTemplate_(True)
            item.button().setImage_(image)
        else:
            item.button().setTitle_("F")
        item.button().setToolTip_("Flache")

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self)
        menu.addItem_(_item("About Flache", "about:", self))
        menu.addItem_(_item("Preferences…", "showPrefs:", self))
        menu.addItem_(_item("Help…", "showHelp:", self))
        menu.addItem_(NSMenuItem.separatorItem())
        self.toggle_item = _item("Show Flache", "toggleFromMenu:", self)
        menu.addItem_(self.toggle_item)
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(_item("Quit Flache", "terminate:", NSApp))
        item.setMenu_(menu)
        self.status_item = item

    def menuNeedsUpdate_(self, menu):
        verb = "Hide" if self.panel.isVisible() else "Show"
        show_chord(self.toggle_item, "%s Flache" % verb, *current_hotkey())

    # -- hotkey -----------------------------------------------------------

    def applyHotkey(self):
        code, mods = current_hotkey()
        ok = self.hotkey.register(code, mods)
        if not ok:
            sys.stderr.write("Flache: could not register %s\n"
                             % hotkey_label(code, mods))
        return ok

    # -- showing and placing ----------------------------------------------

    def toggle(self):
        if self.panel.isVisible():
            self.panel.orderOut_(None)
            set_pref(DEF_VISIBLE, False)
        else:
            self.showPanel()

    def toggleFromMenu_(self, sender):
        self.toggle()

    def showPanel(self):
        self.relayout()
        self.panel.orderFrontRegardless()
        set_pref(DEF_VISIBLE, True)

    def relayout(self):
        """Size the panel for its icons and put it where this arrangement
        was last left.  The top-left corner is the anchor, so adding an app
        grows the panel right or down rather than shifting it."""
        layout, icon = layout_pref(), icon_px()
        w, h = content_size(len(self.apps), layout, icon)
        top_left = saved_top_left(layout)
        if top_left is None:
            main = _rect_tuple(NSScreen.mainScreen().visibleFrame())
            top_left = default_top_left(layout, w, h, main)
        x, top = top_left
        visible = screen_for_point(x + 1, top - 1)
        x, y = clamp_origin(x, top - h, w, h, visible)
        self.panel.setFrame_display_(NSMakeRect(x, y, w, h), True)
        self._refreshToolTips()
        self.view.setNeedsDisplay_(True)

    def panelWasMoved(self):
        frame = self.panel.frame()
        x, top = frame.origin.x, frame.origin.y + frame.size.height
        visible = screen_for_point(x + frame.size.width / 2.0,
                                   top - frame.size.height / 2.0)
        x, y = clamp_origin(x, frame.origin.y, frame.size.width,
                            frame.size.height, visible)
        self.panel.setFrameOrigin_(NSMakePoint(x, y))
        defaults().setObject_forKey_(
            "%g,%g" % (x, y + frame.size.height), DEF_TOP_LEFT + layout_pref())

    def screensChanged_(self, note):
        if self.panel.isVisible():
            self.relayout()

    def _refreshToolTips(self):
        """One tooltip rect per icon, owned by an NSString holding the
        app's name.  AppKit holds a tooltip's owner WEAKLY, so every owner
        is kept in self._tips until its rect is removed; a temporary string
        is freed at once and the tooltip timer then messages freed memory.
        """
        view = self.view
        view.removeAllToolTips()
        layout, icon, count = layout_pref(), icon_px(), len(self.apps)
        if count == 0:
            names = ["Click to add an application, or drag one here"]
        else:
            names = [app_name(entry["path"]) for entry in self.apps]
        self._tips = [NSString.stringWithString_(n) for n in names]
        for i, owner in enumerate(self._tips):
            x, y, c, _ = cell_rect(i, count, layout, icon)
            view.addToolTipRect_owner_userData_(
                NSMakeRect(x, y, c, c), owner, None)

    # -- icons ------------------------------------------------------------

    def isPresent_(self, entry):
        return resolve(entry) is not None

    def iconFor_(self, entry):
        return self._iconAndInk_(entry)[0]

    def inkFor_(self, entry):
        return self._iconAndInk_(entry)[1]

    def _iconAndInk_(self, entry):
        path = resolve(entry) or entry["path"]
        cached = self._icons.get(path)
        if cached is None:
            image = NSWorkspace.sharedWorkspace().iconForFile_(path)
            cached = (image, ink_rect(image))
            self._icons[path] = cached
        return cached

    # -- the context menu -------------------------------------------------

    def menuForIndex_(self, index):
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        menu.addItem_(_item("Help", "showHelp:", self))
        menu.addItem_(NSMenuItem.separatorItem())

        present = index is not None and index < len(self.apps)
        title = ("Delete “%s”" % app_name(self.apps[index]["path"])
                 if present else "Delete")
        delete = _item(title, "deleteApp:", self)
        delete.setEnabled_(present)
        if present:
            delete.setTag_(index)
        menu.addItem_(delete)
        new = _item("New…", "newApp:", self)
        new.setTag_(index + 1 if present else len(self.apps))
        menu.addItem_(new)
        menu.addItem_(NSMenuItem.separatorItem())

        current = layout_pref()
        for layout in ("grid", "column", "strip"):
            entry = _item(layout.capitalize(), "chooseLayout:", self)
            entry.setRepresentedObject_(layout)
            entry.setState_(1 if layout == current else 0)
            menu.addItem_(entry)
        return menu

    def deleteApp_(self, sender):
        index = int(sender.tag())
        if 0 <= index < len(self.apps):
            del self.apps[index]
            set_saved_apps(self.apps)
            self.relayout()

    def newApp_(self, sender):
        self.chooseAppsAt_(int(sender.tag()))

    def chooseAppsAt_(self, at):
        panel = NSOpenPanel.openPanel()
        panel.setTitle_("Add to Flache")
        panel.setPrompt_("Add")
        panel.setMessage_("Choose one or more applications to add to Flache.")
        panel.setAllowedFileTypes_(["app"])
        panel.setAllowsMultipleSelection_(True)
        panel.setCanChooseDirectories_(False)
        panel.setTreatsFilePackagesAsDirectories_(False)
        panel.setDirectoryURL_(NSURL.fileURLWithPath_("/Applications"))
        # The panel holds its delegate weakly; keep it until runModal ends.
        delegate = AddPanelDelegate.alloc().initWithApps_(self.apps)
        panel.setDelegate_(delegate)
        NSApp.activateIgnoringOtherApps_(True)
        response = panel.runModal()
        panel.setDelegate_(None)
        del delegate
        if response != 1:                        # NSModalResponseOK
            return
        self.addPaths_at_([str(u.path()) for u in panel.URLs()], at)

    def openGap_(self, is_open):
        """Grow the panel by GAP while an icon is being placed, and shrink
        it back afterwards, keeping the top-left corner where it is."""
        frame = self.panel.frame()
        top = frame.origin.y + frame.size.height
        w, h = content_size(len(self.apps), layout_pref(), icon_px(), is_open)
        self.panel.setFrame_display_(
            NSMakeRect(frame.origin.x, top - h, w, h), True)

    def moveApp_to_(self, src, at):
        if move_item(self.apps, src, at):
            set_saved_apps(self.apps)
            self.relayout()

    def addPaths_at_(self, paths, at):
        if insert_apps(self.apps, paths, at):
            set_saved_apps(self.apps)
            self.relayout()

    def chooseLayout_(self, sender):
        self.useLayout_(str(sender.representedObject()))

    def useLayout_(self, layout):
        if layout not in LAYOUTS or layout == layout_pref():
            return
        set_pref(DEF_LAYOUT, layout)
        self.relayout()
        if self.prefs is not None:
            self.prefs.refresh()

    # -- launching --------------------------------------------------------

    def launchAt_(self, index):
        if not (0 <= index < len(self.apps)):
            return
        entry = self.apps[index]
        before = entry["path"]
        path = resolve(entry)
        if path is None:
            NSBeep()
            return
        if path != before:
            set_saved_apps(self.apps)
        config = NSWorkspaceOpenConfiguration.configuration()
        config.setActivates_(True)
        NSWorkspace.sharedWorkspace().\
            openApplicationAtURL_configuration_completionHandler_(
                NSURL.fileURLWithPath_(path), config, None)

    # -- menu bar actions -------------------------------------------------

    def about_(self, sender):
        NSApp.activateIgnoringOtherApps_(True)
        NSApp.orderFrontStandardAboutPanelWithOptions_({
            "ApplicationName": APP_NAME,
            "ApplicationVersion": APP_VERSION,
            "Version": APP_VERSION,
            "Credits": NSAttributedString.alloc().initWithString_attributes_(
                "A floating dock for the applications you choose.",
                {NSFontAttributeName: NSFont.systemFontOfSize_(11),
                 NSForegroundColorAttributeName: NSColor.labelColor()}),
        })

    def showPrefs_(self, sender):
        if self.prefs is None:
            self.prefs = PrefsController.alloc().initWithApp_(self)
        self.prefs.show()

    def showHelp_(self, sender):
        if self.help is None:
            self.help = HelpController.alloc().init()
        self.help.show()


def _item(title, action, target):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        title, action, "")
    item.setTarget_(target)
    return item


def show_chord(item, title, code, mods):
    """Title a menu item and show the chord at its right edge, the way
    menus show shortcuts.  A key with no single character to show (Space,
    F-keys, arrows) goes into the title instead."""
    name = KEY_NAMES.get(int(code), "")
    if len(name) == 1:
        item.setTitle_(title)
        item.setKeyEquivalent_(name.lower())
        mask = 0
        if mods & controlKey:
            mask |= NSEventModifierFlagControl
        if mods & optionKey:
            mask |= NSEventModifierFlagOption
        if mods & shiftKey:
            mask |= NSEventModifierFlagShift
        if mods & cmdKey:
            mask |= NSEventModifierFlagCommand
        item.setKeyEquivalentModifierMask_(mask)
    else:
        item.setKeyEquivalent_("")
        item.setTitle_("%s  %s" % (title, hotkey_label(code, mods)))


def menu_bar_glyph():
    """The Old English F, shipped as a PNG so the app does not depend on the
    "Olde English" font being installed."""
    path = NSBundle.mainBundle().pathForResource_ofType_("Flache_glyph", "png")
    if path is None:                       # running from source
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "icon", "Flache_glyph.png")
        path = local if os.path.exists(local) else None
    if path is None:
        return None
    image = NSImage.alloc().initWithContentsOfFile_(path)
    if image is None:
        return None
    size = image.size()
    if size.height > 0:
        image.setSize_(NSMakeSize(
            round(size.width * MENU_BAR_HEIGHT / size.height),
            MENU_BAR_HEIGHT))
    return image


# ---------------------------------------------------------------------------

def already_running():
    """True if another copy of Flache is already running.

    Flache can be started both by its own LaunchAgent and by a Login Item.
    Two copies would draw two panels, and only the first would get the key
    sequence, so the second one quits at once.  It exits with status 0 so
    the LaunchAgent does not treat that as a crash and relaunch it.
    """
    me = os.getpid()
    others = NSRunningApplication.\
        runningApplicationsWithBundleIdentifier_(BUNDLE_ID) or []
    return any(int(a.processIdentifier()) != me for a in others)


def main():
    if already_running():
        sys.exit(0)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                 # accessory: no Dock icon
    delegate = FlacheApp.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
