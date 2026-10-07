"""py2app build for Flache.app - v1.0.0

    ./venv/bin/python make_icon.py      (icon/ must be built first)
    ./venv/bin/python setup.py py2app

LSUIElement makes this a background app: no Dock icon and no menu bar of
its own, only the menu bar F and the floating panel.
"""

import os
import re
from pathlib import Path

from setuptools import setup

APP = ["flache.py"]
# The menu bar mark ships as a PNG so the app does not depend on the
# "Olde English" font being installed on the machine running it.
# Flache-README.txt is made from README.md by build.sh; it is the Help that
# other launchers (and Flache itself) can open from this app's icon.
DATA_FILES = [("", ["icon/Flache_glyph.png", "Flache-README.txt"])]


def app_version():
    """The single source of truth: APP_VERSION in flache.py."""
    source = Path(__file__).with_name("flache.py").read_text()
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if not match:
        raise SystemExit("setup.py: APP_VERSION not found in flache.py")
    return match.group(1)


VERSION = app_version()

OPTIONS = {
    "argv_emulation": False,
    # Pillow is a build-time dependency of make_icon.py only.
    "excludes": ["PIL", "Pillow", "tkinter", "test", "unittest"],
    "plist": {
        "CFBundleName": "Flache",
        "CFBundleDisplayName": "Flache",
        "CFBundleIdentifier": "com.timmccoy.flache",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": True,
        "NSHumanReadableCopyright":
            "Copyright © 2026 Tim McCoy. All rights reserved.",
        "CFBundleGetInfoString":
            "Flache — a floating dock for the applications you choose.",
    },
}
# The icon is the author's artwork; until it exists the app wears the
# generic one rather than a placeholder.
if os.path.exists("icon/Flache.icns"):
    OPTIONS["iconfile"] = "icon/Flache.icns"

setup(
    name="Flache",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
