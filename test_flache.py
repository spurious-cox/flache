"""Tests for Flache - v1.2.2

    ./venv/bin/python test_flache.py

Pure logic first, then an offscreen render of the dock in each arrangement,
light and dark, written to test_render_*.png.  Nothing here writes
preferences: running from source reads the org.python.python domain, and
the render path only reads.
"""

import os
import sys

from AppKit import (NSApplication, NSAppearance, NSBitmapImageFileTypePNG,
                    NSAppearanceNameAqua, NSAppearanceNameDarkAqua)

import flache as F

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def check(name, cond):
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond:
        FAILED.append(name)


def test_shapes():
    check("strip of 5 is 1x5", F.grid_shape(5, "strip") == (1, 5))
    check("column of 5 is 5x1", F.grid_shape(5, "column") == (5, 1))
    check("grid of 5 is 2x3", F.grid_shape(5, "grid") == (2, 3))
    check("grid of 9 is 3x3", F.grid_shape(9, "grid") == (3, 3))
    check("grid of 10 is 3x4", F.grid_shape(10, "grid") == (3, 4))
    check("empty still has the + cell", F.grid_shape(0, "grid") == (1, 1))
    c = F.cell_size(48)
    check("strip size includes the grip at its end",
          F.content_size(3, "strip", 48) ==
          (3 * c + 2 * F.EDGE + 2 * F.GRIP, c + 2 * F.EDGE))
    check("column size includes a grip at each end",
          F.content_size(3, "column", 48) ==
          (c + 2 * F.EDGE, 3 * c + 2 * F.EDGE + 2 * F.GRIP))
    check("an open gap widens a strip",
          F.content_size(3, "strip", 48, True)[0] ==
          F.content_size(3, "strip", 48)[0] + F.GAP)
    check("an open gap lengthens a column",
          F.content_size(3, "column", 48, True)[1] ==
          F.content_size(3, "column", 48)[1] + F.GAP)


def test_hit_testing():
    icon, c = 48, F.cell_size(48)
    for layout in F.LAYOUTS:
        for n in (1, 4, 7):
            ok = True
            for i in range(n):
                x, y, w, h = F.cell_rect(i, n, layout, icon)
                ok &= F.index_at(x + w / 2.0, y + h / 2.0, n, layout, icon) == i
            check("every cell hits itself: %s x%d" % (layout, n), ok)
    check("margin is no cell", F.index_at(1, 1, 3, "strip", icon) is None)
    for layout in F.LAYOUTS:
        w, h = F.content_size(3, layout, icon)
        grips = F.grip_rects(layout, w, h)
        check("two grips, neither a cell (%s)" % layout,
              len(grips) == 2 and all(
                  F.index_at(gx + gw / 2.0, gy + gh / 2.0, 3, layout, icon)
                  is None for gx, gy, gw, gh in grips))
        last = F.cell_rect(2, 3, layout, icon, gap_at=3)
        check("last cell stays clear of the trailing grip (%s)" % layout,
              (last[0] + last[2] <= grips[1][0]) if layout == "strip"
              else (last[1] + last[3] <= grips[1][1]))
    x0 = F.cell_rect(0, 4, "strip", icon, gap_at=2)[0]
    x2 = F.cell_rect(2, 4, "strip", icon)[0]
    check("gap leaves earlier cells alone",
          x0 == F.cell_rect(0, 4, "strip", icon)[0])
    check("gap pushes later cells along",
          F.cell_rect(2, 4, "strip", icon, gap_at=2)[0] == x2 + F.GAP)
    # grid of 5 is 2x3: a gap at 1 moves only the rest of row 0
    check("grid gap moves only its own row",
          F.cell_rect(2, 5, "grid", icon, gap_at=1)[0] ==
          F.cell_rect(2, 5, "grid", icon)[0] + F.GAP and
          F.cell_rect(4, 5, "grid", icon, gap_at=1)[0] ==
          F.cell_rect(4, 5, "grid", icon)[0])
    w, h = F.content_size(4, "strip", icon, True)
    last = F.cell_rect(3, 4, "strip", icon, gap_at=0)
    check("opened strip still holds its last cell before the grip",
          last[0] + last[2] <= F.grip_rects("strip", w, h)[1][0])
    # grid of 5 is 2x3; slot 5 (row 1, col 2) is empty
    x, y, w, h = F.cell_rect(5, 6, "grid", icon)
    check("empty grid slot is no cell",
          F.index_at(x + 5, y + 5, 5, "grid", icon) is None)
    x, y, _, _ = F.cell_rect(1, 3, "strip", icon)
    check("drop in leading half goes before",
          F.insertion_index(x + 2, y + 10, 3, "strip", icon) == 1)
    check("drop in trailing half goes after",
          F.insertion_index(x + c - 2, y + 10, 3, "strip", icon) == 2)
    x, y, _, _ = F.cell_rect(0, 3, "column", icon)
    check("column drop uses the vertical half",
          F.insertion_index(x + c - 2, y + 2, 3, "column", icon) == 0)
    check("drop on empty Flache goes first",
          F.insertion_index(20, 20, 0, "strip", icon) == 0)


def test_placement():
    screen = (0, 0, 1440, 875)
    x, y = F.clamp_origin(-50, -50, 200, 60, screen)
    check("clamped onto the screen, bottom-left",
          (x, y) == (F.SCREEN_MARGIN, F.SCREEN_MARGIN))
    x, y = F.clamp_origin(2000, 2000, 200, 60, screen)
    check("clamped onto the screen, top-right",
          (x, y) == (1440 - 200 - F.SCREEN_MARGIN, 875 - 60 - F.SCREEN_MARGIN))
    x, top = F.default_top_left("strip", 300, 60, screen)
    check("strip starts centred along the top",
          x == 570 and top == 875 - F.SCREEN_MARGIN)
    x, top = F.default_top_left("column", 60, 300, screen)
    check("column starts at the left edge", x == F.SCREEN_MARGIN)


def test_app_list():
    apps = []
    n = F.insert_apps(apps, ["/System/Applications/Calculator.app",
                             "/System/Applications/Notes.app/"])
    check("two apps added", n == 2 and len(apps) == 2)
    check("bundle id recorded",
          apps[0]["bundle"] == "com.apple.calculator")
    check("trailing slash dropped", apps[1]["path"].endswith("Notes.app"))
    n = F.insert_apps(apps, ["/System/Applications/Calculator.app"])
    check("duplicate refused", n == 0 and len(apps) == 2)
    n = F.insert_apps(apps, ["/System/Applications/Chess.app"], at=1)
    check("inserted at index", n == 1 and apps[1]["path"].endswith("Chess.app"))
    check("non-app refused", F.insert_apps(apps, ["/etc/hosts"]) == 0)
    moved = {"path": "/nowhere/Calculator.app",
             "bundle": "com.apple.calculator"}
    check("moved app found by bundle id",
          F.resolve(moved) == "/System/Applications/Calculator.app")
    check("resolve updates the path", moved["path"].startswith("/System"))
    gone = {"path": "/nowhere/Nothing.app", "bundle": "com.example.nothing"}
    check("missing app resolves to None", F.resolve(gone) is None)
    check("app name drops .app",
          F.app_name("/System/Applications/Calculator.app") == "Calculator")


def test_reorder():
    def moved(src, at):
        apps = list("ABCD")
        F.move_item(apps, src, at)
        return "".join(apps)
    check("first to end", moved(0, 4) == "BCDA")
    check("last to front", moved(3, 0) == "DABC")
    check("B after C", moved(1, 3) == "ACBD")
    check("C before B", moved(2, 1) == "ACBD")
    check("dropped on itself: no change",
          moved(1, 1) == "ABCD" and moved(1, 2) == "ABCD")
    check("no change reports False", not F.move_item(list("AB"), 0, 1))


def test_add_dialog():
    from Foundation import NSURL
    d = F.AddPanelDelegate.alloc().initWithApps_(
        [{"path": "/System/Applications/Calculator.app", "bundle": ""}])
    url = NSURL.fileURLWithPath_
    check("app already in Flache is disabled",
          not d.panel_shouldEnableURL_(None, url(
              "/System/Applications/Calculator.app")))
    check("other app is enabled", d.panel_shouldEnableURL_(
        None, url("/System/Applications/Notes.app")))
    check("folders stay enabled", d.panel_shouldEnableURL_(
        None, url("/System/Applications/Utilities")))


def test_chords():
    code, mods = F.DEFAULT_HOTKEY
    check("default chord is ⌃⌥⌘F", F.hotkey_label(code, mods) == "⌃⌥⌘F")
    check("default chord is acceptable", F.chord_problem(code, mods) is None)
    check("bare key refused", F.chord_problem(3, 0) is not None)
    check("shift-only refused", F.chord_problem(3, F.shiftKey) is not None)
    check("a chord already in use is refused",
          F.chord_problem(*F.stache_hotkey()) is not None)


def test_single_instance():
    # From source this process is Python, not Flache, so "another copy"
    # means the installed app - which is running whenever its login agent is.
    import subprocess
    installed = subprocess.run(["pgrep", "-x", "Flache"],
                               capture_output=True).returncode == 0
    check("already_running() matches the installed app (%s)"
          % ("running" if installed else "not running"),
          F.already_running() == installed)


def test_help():
    text = str(F.help_text("⌃⌥⌘F").string())
    check("help names the chord", "⌃⌥⌘F" in text)
    check("help says how to pronounce it", "flash" in text)


def render(app, layout, dark):
    F.set_pref = lambda k, v: None                 # never write prefs here
    F.layout_pref = lambda: layout
    app.relayout()
    view = app.panel.contentView()
    view.setAppearance_(NSAppearance.appearanceNamed_(
        NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua))
    for v in [view] + list(view.subviews()):
        v.setNeedsDisplay_(True)
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    out = os.path.join(HERE, "test_render_%s%s.png" %
                       (layout, "_dark" if dark else ""))
    rep.representationUsingType_properties_(
        NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(out, True)
    return out, bounds.size


def test_render():
    NSApplication.sharedApplication()
    app = F.FlacheApp.alloc().init()
    app.apps = []
    app._icons = {}
    app._buildPanel()
    out, size = render(app, "strip", False)
    check("empty Flache is one + cell wide",
          size.width == F.cell_size(F.icon_px()) + 2 * F.EDGE + 2 * F.GRIP)
    F.insert_apps(app.apps, [
        "/System/Applications/Calculator.app",
        "/System/Applications/Notes.app",
        "/System/Applications/Calendar.app",
        "/System/Applications/Mail.app",
        "/System/Applications/Music.app",
    ])
    app.apps.append({"path": "/nowhere/Gone.app", "bundle": ""})
    for layout in F.LAYOUTS:
        for dark in (False, True):
            out, size = render(app, layout, dark)
            w, h = F.content_size(6, layout, F.icon_px())
            check("one retained tooltip owner per app (%s)" % layout,
                  len(app._tips) == len(app.apps))
            check("rendered %s" % os.path.basename(out),
                  os.path.exists(out) and (size.width, size.height) == (w, h))


if __name__ == "__main__":
    test_shapes()
    test_hit_testing()
    test_placement()
    test_app_list()
    test_reorder()
    test_add_dialog()
    test_chords()
    test_single_instance()
    test_help()
    test_render()
    print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
    sys.exit(1 if FAILED else 0)
