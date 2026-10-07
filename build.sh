#!/bin/zsh
# Build, sign and install Flache.app — v1.0.1
#
# Signing follows the same rules the other apps here learned the hard way:
#
#   * `codesign --deep` is NOT enough for a py2app bundle. It skips the .so
#     files under Resources/lib and the extension-less Mach-O at
#     Contents/MacOS/python, and notarization rejects exactly those. `file`
#     is the only reliable test for what is a Mach-O; filenames are not.
#   * `--options runtime` (hardened runtime) is mandatory for notarization
#     and is not on by default.
#   * The identity is selected by SHA-1 HASH, not by name: expired
#     certificates with similar names are still in the keychain and signing
#     by name can pick a dead one.
#   * --timestamp is not optional; a timestamped signature stays valid after
#     the certificate expires.
#
#   ./build.sh              build and sign into dist/
#   ./build.sh --install    also install to /Applications
set -e
cd "${0:A:h}"

SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"

# Flache can run under a LaunchAgent, and KeepAlive treats a pkill as a
# crash — launchd would relaunch the OLD binary in the middle of the copy.
# Unload it around the install and load it again afterwards.
FLACHE_AGENT="$HOME/Library/LaunchAgents/com.timmccoy.flache.plist"
# Both are idempotent and never fail the script: `launchctl bootout` returns
# non-zero for a service it cannot find, which `set -e` would treat as fatal.
agent_stop() {
    if [[ -f "$FLACHE_AGENT" ]]; then
        launchctl bootout "gui/$(id -u)/com.timmccoy.flache" 2>/dev/null || true
    fi
    pkill -x Flache 2>/dev/null || true
    sleep 1
    return 0
}
agent_start() {
    if [[ -f "$FLACHE_AGENT" ]]; then
        launchctl bootstrap "gui/$(id -u)" "$FLACHE_AGENT" 2>/dev/null || true
    fi
    return 0
}

if ! security find-identity -p codesigning | grep -q "$SIGN_ID"; then
    echo "error: signing identity $SIGN_ID not in keychain — see header of this script" >&2
    exit 1
fi

echo "==> stopping any running instance (and its LaunchAgent)"
agent_stop

echo "==> building the icon"
./venv/bin/python make_icon.py

echo "==> building"
rm -rf build dist
# The Help other launchers open from this app's icon: Flache-README.txt in
# Resources, made from README.md so there is one source.
/usr/bin/python3 "$HOME/My_Applications/_signing/pixpro_readme_txt.py" README.md Flache-README.txt
./venv/bin/python setup.py py2app >/dev/null

# macOS 26+ draws an app that has only an .icns shrunk onto a plain plate.
# The Icon Composer document compiles into Assets.car, which macOS 26+ uses
# instead; the .icns from setup.py is still what macOS 13-25 show.
# Only once the artwork exists; until then the app wears the generic icon.
# The Icon Composer document is remade from flache.png whenever the artwork
# is newer, so replacing flache.png is all it takes to change both icons.
if [[ -f flache.png && ( ! -d icon/AppIcon.icon || flache.png -nt icon/AppIcon.icon ) ]]; then
    ~/bin/glass_icon --make flache.png icon/AppIcon.icon
fi
if [[ -d icon/AppIcon.icon ]]; then
    ~/bin/glass_icon dist/Flache.app icon/AppIcon.icon
fi

echo "==> signing inner binaries with the hardened runtime"
find dist/Flache.app -type f -print0 2>/dev/null | while IFS= read -r -d $'\0' f; do
    if file -b "$f" 2>/dev/null | grep -q 'Mach-O'; then
        codesign --force --timestamp --options runtime --sign "$SIGN_ID" "$f" 2>/dev/null || true
    fi
done

echo "==> sealing nested frameworks, then the app"
find dist/Flache.app -name '*.framework' -print0 2>/dev/null \
    | xargs -0 -n1 -I{} codesign --force --timestamp --options runtime --sign "$SIGN_ID" {} 2>/dev/null || true
codesign --force --timestamp --options runtime \
    --entitlements flache.entitlements --sign "$SIGN_ID" dist/Flache.app
codesign --verify --deep --strict dist/Flache.app

# Installing is the DEFAULT. It used to need --install, and the failure
# that caused is silent: the build succeeds, /Applications keeps the old
# version, and everything downstream looks like it worked. Pass --no-install
# to build without touching /Applications.
if [[ "$1" != "--no-install" ]]; then
    echo "==> installing to /Applications"
    rm -rf /Applications/Flache.app
    cp -R dist/Flache.app /Applications/
    xattr -dr com.apple.quarantine /Applications/Flache.app 2>/dev/null || true
    agent_start
    codesign -dv /Applications/Flache.app 2>&1 | grep -E "Identifier=|Authority="
    plutil -extract CFBundleShortVersionString raw /Applications/Flache.app/Contents/Info.plist
fi

echo "==> running instances: $(pgrep -x Flache | wc -l | tr -d ' ')"
