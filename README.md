# Flache 1.2.2

A floating dock for the applications you choose, for macOS.

Flache (pronounced "flash") is a small panel of application icons that floats
above every window on every Space. Click an icon to open its application. One
key sequence shows or hides the whole panel from anywhere.

### [⬇︎ Download the latest release](https://github.com/spurious-cox/flache/releases/latest)

Notarized and stapled by Apple — open the DMG and drag Flache to
Applications. Or with Homebrew:

    brew install --cask spurious-cox/tap/flache

**Updating: quit Flache first** (menu bar F → Quit Flache). Force-quitting
counts as a crash, and the login agent will bring the old copy straight back.

![Flache as a strip](docs/screenshot.png)

    ⌃⌥⌘F        show or hide Flache

## Using it

* **Click** an icon to open the application, or bring it forward if it is
  already running. Flache never takes the focus from the app you are in.
* **Right-click** for Help, Delete, New… and the three arrangements: Grid,
  Column and Strip.
* **New…** adds applications after the icon you right-clicked. Applications
  already in Flache are grayed out. You can also drag applications from the
  Finder onto Flache.
* **Drag an icon** to move it. The icons part and a blue bar shows where it
  will land. Let go off Flache and nothing changes.
* **Drag a grip** (the dotted bars at both ends) to move Flache. Each
  arrangement remembers where you left it.
* An icon drawn **faded** is an application Flache can no longer find.

The Old English F in the menu bar holds About Flache, Preferences…, Help…,
Show/Hide Flache and Quit.

## Preferences

* **Show / hide** — record any key sequence with at least one of ⌃ ⌥ ⌘.
* **Arrangement** — strip, column or grid.
* **Icon size** — small, medium or large.
* **Open Flache at login** — starts Flache when you log in and restarts it
  if it ever stops unexpectedly, so the key sequence always works. Quit
  from the menu bar and it stays quit until you next log in. Only one copy
  ever runs, so adding Flache to Login Items as well is harmless.

Flache needs no permissions: no Accessibility, no Input Monitoring.

## Building

    ./venv/bin/python test_flache.py      headless checks + test_render*.png
    ./build.sh                            build, sign and install to /Applications
    ./build.sh --no-install               build and sign into dist/ only
    ./release.sh                          notarize + staple app and DMG, update the cask

The version lives in one place — `APP_VERSION` in `flache.py`. Replacing
`flache.png` and running `./build.sh` rebuilds both app icons.

## Files

    flache.py            the whole app
    test_flache.py       headless checks and the panel renders
    make_icon.py         menu bar glyph and icon/Flache.icns from flache.png
    flache.png           the icon artwork
    setup.py             py2app bundle
    build.sh             build, sign, install
    release.sh           notarize and staple app + DMG
    flache.entitlements  hardened-runtime entitlements

© 2026 Tim McCoy.

## Problems or suggestions

Open an issue: https://github.com/spurious-cox/flache/issues
