#!/bin/zsh
# Notarize Flache.app and wrap it in a distributable DMG — v1.0.0
#
# Run ./build.sh first; this takes dist/Flache.app as it finds it.
#
# Notarization uses the PixProNotary keychain profile, shared with the other
# apps, so no password lives here or gets typed. If the profile is ever lost:
#   xcrun notarytool store-credentials "PixProNotary" \
#       --apple-id <appleid> --team-id RUDN8D7ZN9
#
# Both the app and the DMG are notarized and stapled: the app because that
# is what gets dragged out of the DMG, the DMG because that is what gets
# downloaded.
#
# This does NOT tag, push, make the GitHub release or push the tap.
set -e
cd "${0:A:h}"

SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"
PROFILE="PixProNotary"
APP="dist/Flache.app"
VOLNAME="Flache"

# Flache can run under a LaunchAgent whose KeepAlive treats a pkill as a
# crash, so the agent is unloaded around the install. Both are idempotent.
FLACHE_AGENT="$HOME/Library/LaunchAgents/com.timmccoy.flache.plist"
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

[[ -d "$APP" ]] || { echo "error: $APP not found — run ./build.sh first" >&2; exit 1; }

VERSION=$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")
DMG="dist/Flache-${VERSION}.dmg"

xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1 \
    || { echo "error: no notary profile '$PROFILE' in keychain" >&2; exit 1; }

echo "==> notarizing the app (Flache $VERSION)"
rm -f dist/Flache_notarize.zip
ditto -c -k --keepParent "$APP" dist/Flache_notarize.zip
xcrun notarytool submit dist/Flache_notarize.zip --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"

echo "==> building the disk image"
rm -rf dist/dmg "$DMG"
mkdir -p dist/dmg
cp -R "$APP" dist/dmg/
ln -s /Applications dist/dmg/Applications
cat > "dist/dmg/READ ME FIRST.txt" <<READMEEOF
Flache $VERSION

INSTALLING
    Drag Flache onto the Applications folder beside it.

UPDATING - QUIT THE OLD ONE FIRST
    If Flache is already installed and running, quit it before you copy:

        menu bar F  ->  Quit Flache

    With "Open Flache at login" on, a login agent restarts Flache if it
    stops unexpectedly, so FORCE QUITTING is not enough - the old copy comes
    straight back. Quitting from the menu is enough.

    To check which version is running afterwards:
        menu bar F  ->  About Flache

USING IT
    Control-Option-Command-F shows and hides Flache. Right-click it to add
    applications. Flache needs no special permissions.

HOMEBREW
    brew install --cask spurious-cox/tap/flache

https://github.com/spurious-cox/flache
(c) 2026 Tim McCoy
READMEEOF
# hdiutil can return "Resource busy" on a folder written seconds earlier;
# it clears on its own, so retry.
for attempt in 1 2 3 4 5; do
    if hdiutil create -volname "$VOLNAME" -srcfolder dist/dmg -ov \
            -format UDZO "$DMG" >/dev/null 2>dist/hdiutil.err; then
        break
    fi
    echo "    hdiutil attempt $attempt failed: $(tr -d '\n' < dist/hdiutil.err)"
    if [[ $attempt == 5 ]]; then
        echo "error: could not build the disk image" >&2
        exit 1
    fi
    sleep 5
done
rm -rf dist/dmg dist/hdiutil.err

echo "==> signing and notarizing the disk image"
codesign --force --timestamp --sign "$SIGN_ID" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"

echo "==> installing the stapled app to /Applications"
agent_stop
rm -rf /Applications/Flache.app
cp -R "$APP" /Applications/
xattr -dr com.apple.quarantine /Applications/Flache.app 2>/dev/null || true
agent_start

echo "==> updating the Homebrew cask"
TAP="$(brew --repository 2>/dev/null)/Library/Taps/spurious-cox/homebrew-tap"
CASK="$TAP/Casks/flache.rb"
if [[ -f "$CASK" ]]; then
    SHA=$(shasum -a 256 "$DMG" | cut -d" " -f1)
    # Only the two lines that change per release.
    /usr/bin/sed -i "" \
        -e "s/^  version \".*\"/  version \"$VERSION\"/" \
        -e "s/^  sha256 \".*\"/  sha256 \"$SHA\"/" "$CASK"
    echo "    $CASK -> $VERSION"
    echo "    sha256 $SHA"
    if brew style --cask "$CASK" >/dev/null 2>&1; then
        echo "    style: ok — commit and push the tap to publish it"
    else
        echo "    style: FAILED — check $CASK by hand" >&2
    fi
else
    echo "    no cask at $CASK — skipped"
fi

echo "==> results"
echo "    dmg:      $DMG  ($(du -h "$DMG" | cut -f1))"
echo "    stapled:  app $(xcrun stapler validate "$APP" >/dev/null 2>&1 && echo YES || echo no), dmg $(xcrun stapler validate "$DMG" >/dev/null 2>&1 && echo YES || echo no)"
spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 | sed 's/^/    gatekeeper: /'
echo "    running instances: $(pgrep -x Flache | wc -l | tr -d ' ')"
