#!/usr/bin/env bash
# Play a WAV file using the project's RealAudio player.
# Usage: ./scripts/play_audio.sh [path/to/file.wav]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AUDIO_DIR="$ROOT_DIR/app/static/audio"

if [ $# -ge 1 ]; then
  FILE="$1"
  # If relative path, make it relative to project root
  if [ ! -e "$FILE" ]; then
    FILE="$ROOT_DIR/$FILE"
  fi
else
  # pick the first .wav in the audio dir
  FILE=""
  for f in "$AUDIO_DIR"/*.wav; do
    [ -e "$f" ] || continue
    FILE="$f"
    break
  done
  if [ -z "$FILE" ]; then
    echo "No audio file provided and no .wav found in $AUDIO_DIR"
    echo "Place a .wav in $AUDIO_DIR or pass a path as the first argument." >&2
    exit 1
  fi
fi

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

export AUDIO_FILE="$FILE"
export PYTHONPATH="$ROOT_DIR"
python3 - <<'PY'
import os
from app.hardware.gpio_audio import RealAudio
fn = os.environ.get('AUDIO_FILE')
if not fn:
    raise SystemExit('AUDIO_FILE not set')
RealAudio().play(fn)
PY
