#!/usr/bin/env python3
"""
Play a WAV file using the project's `RealAudio` class.

Usage:
  ./scripts/test_audio.py [path/to/file.wav]

If no argument is given the script will play the first .wav found in
the configured `AUDIO_DIR` from `app.config`.
"""
import sys
import os
import glob
from ..config import AUDIO_DIR

#from app.config import AUDIO_DIR
from app.hardware.gpio_audio import RealAudio


def find_default_wav():
    pattern = os.path.join(AUDIO_DIR, "*.wav")
    files = glob.glob(pattern)
    return files[0] if files else None


def resolve_path(arg: str) -> str:
    # absolute path or direct existing path
    if os.path.isabs(arg) and os.path.exists(arg):
        return arg
    if os.path.exists(arg):
        return arg
    # otherwise try relative to AUDIO_DIR
    candidate = os.path.join(AUDIO_DIR, arg)
    if os.path.exists(candidate):
        return candidate
    return arg  # let RealAudio raise if it doesn't exist


def main(argv):
    if len(argv) >= 2:
        path = resolve_path(argv[1])
    else:
        path = find_default_wav()

    if not path:
        print(f"No WAV file specified and none found in {AUDIO_DIR}")
        sys.exit(1)

    print(f"Playing audio file: {path}")
    try:
        RealAudio().play(path)
    except Exception as e:
        print(f"Playback failed: {e}")
        sys.exit(2)

    print("Playback finished")


if __name__ == "__main__":
    main(sys.argv)
