import os
import simpleaudio as sa

from ..config import AUDIO_DIR


class RealAudio:
    def __init__(self):
        print("RealAudio initialized")

    def _resolve_path(self, filename: str) -> str:
        # If caller passed an absolute path or the file exists as given, use it.
        if os.path.isabs(filename) or os.path.exists(filename):
            return filename

        # Otherwise resolve relative to the configured audio directory
        return os.path.join(AUDIO_DIR, filename)

    def play(self, filename):
        path = self._resolve_path(filename)
        try:
            wave = sa.WaveObject.from_wave_file(path)
            play_obj = wave.play()
            print(f"Playing audio: {path}")
            play_obj.wait_done()
        except Exception as e:
            print(f"Audio playback error: {e}")