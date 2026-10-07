"""Tests for Flache - v1.7.5

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


def test_recents():
    import tempfile
    from Foundation import NSKeyedArchiver, NSURL
    tmp = tempfile.mkdtemp()
    doc = os.path.join(tmp, "a doc.txt")
    open(doc, "w").close()
    gone = os.path.join(tmp, "gone.txt")
    open(gone, "w").close()
    marks = []
    for path in (doc, gone):
        data, _err = NSURL.fileURLWithPath_(path).\
            bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(
                0, None, None, None)
        marks.append(data)
    os.remove(gone)
    root = {"items": [{"Bookmark": marks[0]}, {"uuid": "no bookmark"},
                      {"Bookmark": marks[1]}]}
    NSKeyedArchiver.archivedDataWithRootObject_(root).writeToFile_atomically_(
        os.path.join(tmp, "com.example.docs.sfl4"), True)
    saved, F.RECENTS_DIR = F.RECENTS_DIR, tmp
    try:
        found = F.recent_documents("com.Example.Docs")
        check("recents read, missing and bookmark-less skipped",
              [os.path.realpath(p) for p in found] == [os.path.realpath(doc)])
        check("no list, no recents", F.recent_documents("com.example.none") == [])
        check("no bundle id, no recents", F.recent_documents("") == [])
    finally:
        F.RECENTS_DIR = saved


def test_app_help():
    import tempfile
    app = os.path.join(tempfile.mkdtemp(), "Thing.app")
    res = os.path.join(app, "Contents", "Resources")
    os.makedirs(res)
    check("no Resources README, no help", F.app_help(app) is None)
    open(os.path.join(res, "Other-README.txt"), "w").close()
    check("another name's README ignored", F.app_help(app) is None)
    open(os.path.join(res, "Thing-README.txt"), "w").close()
    check("own README found", F.app_help(app).endswith("Thing-README.txt"))
    os.makedirs(os.path.join(res, "Thing-README.rtfd"))
    check("RTFD preferred over text", F.app_help(app).endswith("Thing-README.rtfd"))
    check("missing app, no help", F.app_help("/nowhere/X.app") is None)
    art = "/Applications/Art Text 4.app"
    if os.path.isdir(art):
        page = F.app_help(art) or ""
        check("Help book start page found", page.endswith("index.html")
              and os.path.isfile(page))


def test_launch_environment():
    env = {"PYTHONHOME": "/x", "PYTHONPATH": "/x", "RESOURCEPATH": "/x",
           "ARGVZERO": "a", "EXECUTABLEPATH": "e", "HOME": "/Users/t",
           "PATH": "/usr/bin"}
    F.clean_launch_environment(env)
    check("Python and py2app settings removed before launching apps",
          env == {"HOME": "/Users/t", "PATH": "/usr/bin"})


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


def test_panels():
    """Named panels, against an in-memory stand-in for the defaults."""
    store = {}
    saved = F.pref, F.set_pref, F.remove_pref
    F.pref = lambda k: store[k] if k in store else F.DEFAULTS.get(k)
    F.set_pref = lambda k, v: store.__setitem__(k, v)
    F.remove_pref = lambda k: store.pop(k, None)
    try:
        a = {"path": "/Applications/A.app", "bundle": "a"}
        b = {"path": "/Applications/B.app", "bundle": "b"}
        F.set_saved_apps([a, b])
        store[F.DEF_LAYOUT] = "column"
        store[F.DEF_TOP_LEFT + "column"] = "100,800"
        check("the original panel is named PixPro",
              F.panel_names() == ["PixPro"])
        check("a lone panel cannot be deleted", not F.delete_panel("PixPro"))

        check("new panel", F.add_panel("  Art   Text "))
        check("its name is tidied", F.current_panel() == "Art Text")
        check("it starts empty", F.saved_apps() == [])
        check("in the same arrangement and place",
              F.layout_pref() == "column"
              and store.get(F.DEF_TOP_LEFT + "column") == "100,800")
        check("names clash ignoring case", not F.add_panel("pixpro"))

        F.set_saved_apps([b])
        store[F.DEF_LAYOUT] = "grid"
        store[F.DEF_TOP_LEFT + "grid"] = "500,500"
        check("switch back", F.switch_panel("PixPro"))
        check("PixPro's apps return", [x["path"] for x in F.saved_apps()]
              == [a["path"], b["path"]])
        check("and its arrangement", F.layout_pref() == "column")
        check("a place it never had is cleared",
              F.DEF_TOP_LEFT + "grid" not in store)
        check("switching to itself does nothing", not F.switch_panel("PixPro"))

        check("switch forward", F.switch_panel("Art Text"))
        check("Art Text kept its own apps and place",
              [x["path"] for x in F.saved_apps()] == [b["path"]]
              and F.layout_pref() == "grid"
              and store.get(F.DEF_TOP_LEFT + "grid") == "500,500")

        check("rename the current panel", F.rename_panel("Art Text", "ArtText"))
        check("the current name follows", F.current_panel() == "ArtText")
        check("rename to its own name in new case",
              F.rename_panel("ArtText", "Arttext"))
        F.rename_panel("Arttext", "ArtText")
        check("rename onto another panel is refused",
              not F.rename_panel("ArtText", "PIXPRO"))
        check("menu order", F.panel_names() == ["PixPro", "ArtText"])

        F.add_panel("Affinity")
        check("delete the current panel", F.delete_panel("Affinity"))
        check("the one before it comes on screen",
              F.current_panel() == "ArtText"
              and [x["path"] for x in F.saved_apps()] == [b["path"]])
        check("delete another panel", F.delete_panel("PixPro"))
        check("one left", F.panel_names() == ["ArtText"])

        # ArtText holds B.  Copy and move between it and a new panel.
        F.add_panel("Affinity")
        F.set_saved_apps([a, b])
        check("copy to another panel", F.transfer_app(0, "ArtText", False))
        check("a copy stays here", len(F.saved_apps()) == 2)
        check("copying it again is refused",
              not F.transfer_app(0, "ArtText", False))
        check("so is one the target already has (by bundle id)",
              not F.transfer_app(1, "ArtText", True))
        check("nor to the panel on screen", not F.transfer_app(0, "Affinity", True))
        F.set_saved_apps([a, b, {"path": "/Applications/C.app", "bundle": "c"}])
        check("move to another panel", F.transfer_app(2, "ArtText", True))
        check("a move leaves this panel",
              [x["bundle"] for x in F.saved_apps()] == ["a", "b"])
        F.switch_panel("ArtText")
        check("the target has them at the end, in order",
              [x["bundle"] for x in F.saved_apps()] == ["b", "a", "c"])
    finally:
        F.pref, F.set_pref, F.remove_pref = saved


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


def test_icon_refresh():
    """A rebuilt app's icon is re-read; an untouched one is served from cache."""
    import shutil
    import tempfile
    NSApplication.sharedApplication()
    app = F.FlacheApp.alloc().init()
    app._icons = {}
    tmp = tempfile.mkdtemp()
    try:
        bundle = os.path.join(tmp, "Fake.app")
        os.makedirs(os.path.join(bundle, "Contents"))
        entry = {"path": bundle, "bundle": "x.fake"}
        first = app._iconAndInk_(entry)
        check("untouched app keeps its cached icon", app._iconAndInk_(entry) is not None
              and app._icons[bundle][0] is first[0])
        stamp = app._icons[bundle][2]
        os.utime(os.path.join(bundle, "Contents"), ns=(stamp + 5_000_000_000,) * 2)
        app._iconAndInk_(entry)
        check("a changed bundle is looked up again", app._icons[bundle][2] != stamp)
    finally:
        shutil.rmtree(tmp)


def test_menus():
    """An icon's menu is about the application; Flache's own items are on the
    empty space's menu, and the arrangements are in the menu bar too."""
    NSApplication.sharedApplication()
    app = F.FlacheApp.alloc().init()
    app.apps = [{"path": "/System/Applications/Calculator.app", "bundle": ""}]
    app._icons = {}
    icon = [i.title() for i in app.menuForIndex_(0).itemArray()
            if not i.isSeparatorItem()]
    space = [i.title() for i in app.menuForIndex_(None).itemArray()
             if not i.isSeparatorItem()]
    for word in ("Flache Help", "Panels", "Grid", "Column", "Strip",
                 "Hide Flache"):
        check("an icon's menu has no %s" % word, word not in icon)
        check("the empty space's menu has %s" % word, word in space)
    for word in ("Move to", "Copy to", "New…", "Locate Calculator"):
        check("an icon's menu keeps %s" % word, word in icon)
    check("and Remove from Flache comes last",
          icon[-1] == "Remove from Flache")


def test_quiet_update():
    """The check at launch: once a day, silent unless newer."""
    store = {}
    calls = []
    saved = F.latest_release, F.APP_VERSION, F.defaults

    class Fake(object):
        def stringForKey_(self, k):
            return store.get(k)

        def setObject_forKey_(self, v, k):
            store[k] = v

    F.defaults = lambda: Fake()
    try:
        F.latest_release = lambda seconds=10: (
            calls.append(seconds) or ["9.9.9", "page"])
        F.APP_VERSION = "1.0.0"
        line = F.quiet_update_line()
        check("a newer release is reported with the brew line",
              line.startswith("Update available: 9.9.9")
              and "brew upgrade --cask flache" in line)
        check("it gives up after three seconds", calls == [3])
        F.quiet_update_line()
        check("and asks only once a day", len(calls) == 1)
        F.APP_VERSION = "9.9.9"
        check("silent when this build is current", F.quiet_update_line() == "")
        store.clear()
        F.latest_release = lambda seconds=10: None
        check("silent when GitHub cannot be reached",
              F.quiet_update_line() == "")
    finally:
        F.latest_release, F.APP_VERSION, F.defaults = saved


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
    test_recents()
    test_app_help()
    test_launch_environment()
    test_reorder()
    test_add_dialog()
    test_chords()
    test_single_instance()
    test_help()
    test_panels()
    test_icon_refresh()
    test_menus()
    test_quiet_update()
    test_render()
    print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
    sys.exit(1 if FAILED else 0)
