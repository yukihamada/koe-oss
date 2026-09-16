#!/bin/sh
# Install KOE.app to /Applications and clear the quarantine flag.
#
# The build is ad-hoc signed (no Developer ID certificate on this machine), so
# Gatekeeper blocks it with "app is damaged". That block is not the signature
# itself — it is the com.apple.quarantine attribute macOS attaches to anything
# downloaded. Removing it lets the app launch.
#
#   curl -fsSL <url-to-this-script> | sh
# or
#   sh install.sh

set -eu

APP="KOE.app"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

# If we were piped via curl there is no dirname to use; fall back to the DMG.
if [ ! -d "$SRC_DIR/$APP" ]; then
    VOL=$(hdiutil attach "$SRC_DIR"/*.dmg -nobrowse -plist 2>/dev/null \
          | grep -A1 mount-point | grep string \
          | sed -E 's/.*<string>(.*)<\/string>.*/\1/')
    [ -n "$VOL" ] || { echo "could not mount DMG"; exit 1; }
    SRC_DIR="$VOL"
fi

[ -d "$SRC_DIR/$APP" ] || { echo "$APP not found in $SRC_DIR"; exit 1; }

echo "installing $APP to /Applications"
rm -rf "/Applications/$APP"
ditto "$SRC_DIR/$APP" "/Applications/$APP"

echo "clearing quarantine"
xattr -dr com.apple.quarantine "/Applications/$APP" 2>/dev/null || true

echo "verifying"
if codesign -dv "/Applications/$APP" 2>/dev/null | grep -q "TeamIdentifier=not set"; then
    echo
    echo "NOTE: this build is ad-hoc signed (no Developer ID certificate was"
    echo "available). It will run on this Mac. To distribute it to others"
    echo "without this warning, sign it with a Developer ID certificate:"
    echo "  ./scripts/sign.sh sign"
fi

echo "done: /Applications/$APP"
