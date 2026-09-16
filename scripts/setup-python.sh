#!/bin/sh
# Create a venv inside the app bundle and install koe_oss into it.
#
# The app needs a python that can import koe_oss. A plain system python cannot,
# so the app looks for <bundle>/Contents/Resources/venv. This script creates it.
#
#   scripts/setup-python.sh            # build the venv into the app bundle
#   scripts/setup-python.sh --check    # report what the app would find

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/app/src-tauri/target/release/bundle/macos/KOE.app"
VENV="$APP/Contents/Resources/venv"

if [ "${1:-}" = "--check" ]; then
    if [ -x "$VENV/bin/python" ]; then
        echo "venv: $VENV"
        if "$VENV/bin/python" -c "import koe_oss" 2>/dev/null; then
            echo "koe_oss: importable"
            exit 0
        fi
        echo "koe_oss: MISSING in venv"
        exit 1
    fi
    echo "venv: absent at $VENV"
    echo "run: scripts/setup-python.sh"
    exit 1
fi

[ -d "$APP" ] || { echo "no app bundle at $APP; run: scripts/sign.sh build"; exit 1; }

PY=""
for cand in python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "no python3 found"; exit 1; }
echo "using $PY ($($PY -V 2>&1))"

mkdir -p "$APP/Contents/Resources"
rm -rf "$VENV"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip --quiet
"$VENV/bin/python" -m pip install --quiet "$ROOT"

# Transcription (mlx-whisper) is installed by default: it is small next to the
# TTS stack and the app advertises speech-to-text.
echo "installing mlx-whisper"
"$VENV/bin/python" -m pip install --quiet mlx-whisper

# mlx-whisper declares torch but never imports it (verified: 'torch' not in
# sys.modules after import). It is 583MB of the bundle for nothing, so remove
# it. If a future version imports it, transcription will fail loudly with an
# ImportError rather than silently degrading.
"$VENV/bin/python" -m pip uninstall -y -q torch 2>/dev/null || true

# Synthesis is the point of the app, so mlx-audio is installed by default.
# It used to be behind KOE_WITH_MLX=1, which sign.sh never set — the shipped
# app could transcribe but not speak.
echo "installing mlx-audio (slow)"
"$VENV/bin/python" -m pip install --quiet mlx-audio

echo "installing soundfile"
"$VENV/bin/python" -m pip install --quiet soundfile

"$VENV/bin/python" -c "import koe_oss; print('koe_oss OK:', koe_oss.__file__)"
echo "venv ready: $VENV"
