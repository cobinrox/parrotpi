import os
import simpleaudio as sa
import wave 
import threading
from ..config import AUDIO_DIR
import logging

# ---------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

class RealAudio:
    def __init__(self):
        print("RealAudio initialized")
        # Holds the simpleaudio.PlayObject for the currently playing sound.
        # This lets other threads check playback status (via is_playing())
        self.current_play_obj = None  


    def _resolve_path(self, filename: str) -> str:
        # If caller passed an absolute path or the file exists as given, use it.
        if os.path.isabs(filename) or os.path.exists(filename):
            return filename

        # Otherwise resolve relative to the configured audio directory
        return os.path.join(AUDIO_DIR, filename)

    def get_wav_duration(self, path):
        with wave.open(path, 'rb') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / float(rate)
            return duration

    # play audio in a separate thread so it doesn't block the server. 
    # Caller can check self.current_play_obj to see if it's still playing.            
    def play(self, filename):
        thread = threading.Thread(target=self._play_blocking, args=(filename,))
        thread.daemon = True
        logging.info(f"Starting audio thread for {filename}")
        thread.start()
        logging.info("Audio thread started, returning to caller immediately")
        return thread   # optional: lets you track the thread if needed

    def _play_blocking(self, filename):
        path = self._resolve_path(filename)
        duration = self.get_wav_duration(path)
        print(f"Playing audio: {path} (duration: {duration:.2f}s)")

        #try:
            
            # wave = sa.WaveObject.from_wave_file(path)
            # play_obj = wave.play()
            # #play_obj = wave.play(device=0)

            # # store the playback object so other code can check status
            # logging.info("Setting current_play_obj")
            # self.current_play_obj = play_obj

            # play_obj.wait_done()
            # print("Audio finished")
            # self.current_play_obj = None
        try:
            # Use aplay with explicit device (matches startup tone)
            import subprocess
            result = subprocess.run([
                "aplay", "-D", "plughw:0,0", path
            ]) #, capture_output=True, timeout=duration + 1.0)
            
            if result.returncode == 0:
                print("Audio finished")
            else:
                print(f"aplay failed: {result.stderr.decode()}")
        
            self.current_play_obj = None  # No real object, just clear it            
        except Exception as e:
            print(f"Audio playback error: {e}")
            self.current_play_obj = None
        
            



    # def play(self, filename):
    #     path = self._resolve_path(filename)
    #     duration = self.get_wav_duration(path)
    #     print(f"Playing audio: {path} (duration: {duration:.2f}s
    #     try:
    #         wave = sa.WaveObject.from_wave_file(path)
    #         play_obj = wave.play()
    #         print(f"Playing audio: {path}")
    #         play_obj.wait_done()
    #     except Exception as e:
    #         print(f"Audio playback error: {e}")