#!/bin/sh
# Sign, notarize and staple the KOE macOS app.
#
#   scripts/sign.sh check     what can this machine do right now?
#   scripts/sign.sh build     build .app and DMG
#   scripts/sign.sh sign      sign + notarize + staple (needs a certificate)
#   scripts/sign.sh verify    verify an existing build
#   scripts/sign.sh all       build, then sign if possible
#
# Signing needs a "Developer ID Application" certificate. This machine does not
# have one (only "iPhone Distribution", which cannot sign macOS apps), so
# `sign` explains exactly what is missing and exits 1 rather than failing
# cryptically halfway through.
#
# Notarization needs an App Store Connect API key at
# ~/.appstoreconnect/api_key.json (issuer_id / key_id) plus the matching
# private key in ~/private_keys/AuthKey_<key_id>.p8.

set -eu

APP_NAME="KOE"
BUNDLE_ID="live.koe.oss"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAURI_DIR="$ROOT/app/src-tauri"
BUNDLE_DIR="$TAURI_DIR/target/release/bundle"
DIST="$ROOT/dist"

DEV_ID_CERT="Developer ID Application"
DEV_ID_INSTALLER="Developer ID Installer"

log()  { printf '%s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- detection
find_identity() {
    # $1 = substring to look for. Prints the identity hash, or nothing.
    security find-identity -v -p codesigning 2>/dev/null \
        | grep -F "$1" \
        | head -1 \
        | sed -E 's/.*^[[:space:]]*[0-9]+\) ([0-9A-F]+) .*/\1/' \
        | tr -d ' '
}

has_asc_key() {
    [ -f "$HOME/.appstoreconnect/api_key.json" ] || return 1
    key_id=$(python3 -c "import json;print(json.load(open('$HOME/.appstoreconnect/api_key.json')).get('key_id',''))" 2>/dev/null || echo "")
    [ -n "$key_id" ] && [ -f "$HOME/private_keys/AuthKey_$key_id.p8" ]
}

cmd_check() {
    log "=== machine capability ==="
    log "xcode cli tools : $(xcode-select -p 2>/dev/null || echo MISSING)"

    dev=$(find_identity "$DEV_ID_CERT")
    if [ -n "$dev" ]; then
        name=$(security find-identity -v -p codesigning | grep -F "$dev" | sed -E 's/.*"(.*)".*/\1/')
        log "Developer ID    : FOUND  $name ($dev)"
        dev_ok=1
    else
        log "Developer ID    : MISSING  <- cannot distribute outside this Mac"
        dev_ok=0
    fi

    if has_asc_key; then
        log "notary key      : FOUND"
        notary_ok=1
    else
        log "notary key      : MISSING (~/.appstoreconnect/api_key.json + ~/private_keys/AuthKey_<id>.p8)"
        notary_ok=0
    fi

    log ""
    log "identities present:"
    security find-identity -v -p codesigning 2>/dev/null | sed 's/^/  /'

    if [ "$dev_ok" = 1 ] && [ "$notary_ok" = 1 ]; then
        log ""
        log "READY: scripts/sign.sh all"
        return 0
    fi
    log ""
    log "NOT READY to distribute. Build and local run still work:"
    log "  scripts/sign.sh build"
    return 1
}

# ------------------------------------------------------------------- build
cmd_build() {
    log "=== build ==="
    command -v cargo >/dev/null || fail "cargo not found"
    cargo tauri --version >/dev/null 2>&1 \
        || fail "cargo-tauri not found. Install: cargo install tauri-cli --version '^2'"

    (cd "$TAURI_DIR" && cargo tauri build --bundles app)

    # cargo tauri build does not copy frontendDist into the bundle when there
    # is no devServer, so the app launched with no UI at all. Copy it here.
    RES="$BUNDLE_DIR/macos/$APP_NAME.app/Contents/Resources"
    mkdir -p "$RES"
    cp -R "$ROOT/app/ui/." "$RES/"

    # cargo tauri build wipes Contents/Resources, so the venv has to be
    # created after it, not before.
    if [ -x "$ROOT/scripts/setup-python.sh" ]; then
        if ! "$ROOT/scripts/setup-python.sh" 2>&1 | grep -v "WARNING: Cache"; then
            log "warning: python venv not created"
        fi
    fi

    mkdir -p "$DIST"
    rm -f "$DIST/$APP_NAME.dmg"
    hdiutil create -volname "$APP_NAME" \
        -srcfolder "$BUNDLE_DIR/macos/$APP_NAME.app" \
        -ov -format UDZO "$DIST/$APP_NAME.dmg" >/dev/null
    log "built  $BUNDLE_DIR/macos/$APP_NAME.app"
    log "built  $DIST/$APP_NAME.dmg"
}

# -------------------------------------------------------------------- sign
cmd_sign() {
    APP="$BUNDLE_DIR/macos/$APP_NAME.app"
    [ -d "$APP" ] || fail "no app bundle. Run: $0 build"

    identity=$(find_identity "$DEV_ID_CERT")
    [ -n "$identity" ] || fail \
"no Developer ID Application certificate.

Present identities:
$(security find-identity -v -p codesigning | sed 's/^/  /')

To get one:
  1. https://developer.apple.com/account/resources/certificates/add
  2. Choose 'Developer ID Application' (NOT 'Mac App Distribution')
  3. Upload a CSR, download the .cer, open it in Keychain Access
Then re-run: $0 sign"

    log "=== signing with $identity ==="

    # Sign nested items first (dylibs, helpers), then the bundle itself.
    find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.framework" \) -print0 \
        | while IFS= read -r -d '' f; do
            codesign --force --options runtime --timestamp \
                --sign "$identity" "$f" 2>/dev/null || true
          done

    codesign --force --deep --options runtime --timestamp \
        --sign "$identity" --identifier "$BUNDLE_ID" "$APP"

    log "signature:"
    codesign -dv "$APP" 2>&1 | sed 's/^/  /' | head -8

    # ---------------------------------------------------------- notarize
    if ! has_asc_key; then
        log ""
        log "signed, but NOT notarized (no ASC key)."
        log "The app will still be blocked on other machines."
        return 0
    fi

    log "=== notarizing ==="
    ASC="$HOME/.appstoreconnect/api_key.json"
    issuer=$(python3 -c "import json;print(json.load(open('$ASC'))['issuer_id'])")
    key_id=$(python3 -c "import json;print(json.load(open('$ASC'))['key_id'])")
    key_p8="$HOME/private_keys/AuthKey_$key_id.p8"

    zip_path="$DIST/$APP_NAME-notarize.zip"
    mkdir -p "$DIST"
    rm -f "$zip_path"
    ditto -c -k --keepParent "$APP" "$zip_path"

    xcrun notarytool submit "$zip_path" \
        --key "$key_p8" --key-id "$key_id" --issuer "$issuer" \
        --wait --timeout 30m

    log "=== stapling ==="
    xcrun stapler staple "$APP"

    # Rebuild the DMG so it contains the stapled app.
    rm -f "$DIST/$APP_NAME.dmg"
    hdiutil create -volname "$APP_NAME" -srcfolder "$APP" \
        -ov -format UDZO "$DIST/$APP_NAME.dmg" >/dev/null

    log ""
    log "DONE: $DIST/$APP_NAME.dmg"
}

# ------------------------------------------------------------------ verify
cmd_verify() {
    APP="$BUNDLE_DIR/macos/$APP_NAME.app"
    [ -d "$APP" ] || fail "no app bundle at $APP"

    log "=== $APP ==="
    if codesign -dv "$APP" 2>/dev/null; then
        log "signature: PRESENT"
        codesign -dv "$APP" 2>&1 | grep -E "Identifier|TeamIdentifier|Authority" | sed 's/^/  /'
    else
        log "signature: ABSENT (unsigned)"
    fi

    log ""
    log "gatekeeper assessment:"
    spctl -a -vv "$APP" 2>&1 | sed 's/^/  /' | head -5 || true

    log ""
    log "notary staple:"
    xcrun stapler validate "$APP" 2>&1 | sed 's/^/  /' | head -3 || true

    if [ -f "$DIST/$APP_NAME.dmg" ]; then
        log ""
        log "dmg: $DIST/$APP_NAME.dmg ($(du -h "$DIST/$APP_NAME.dmg" | cut -f1))"
    fi
}

case "${1:-check}" in
    check)  cmd_check ;;
    build)  cmd_build ;;
    sign)   cmd_sign ;;
    verify) cmd_verify ;;
    all)    cmd_build && cmd_sign && cmd_verify ;;
    *)      fail "usage: $0 {check|build|sign|verify|all}" ;;
esac
