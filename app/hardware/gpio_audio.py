import simpleaudio as sa

class RealAudio:
    def __init__(self):
        print("RealAudio initialized")

    def play(self, filename):
        try:
            wave = sa.WaveObject.from_wave_file(filename)
            play_obj = wave.play()
            print(f"Playing audio: {filename}")
            play_obj.wait_done()
        except Exception as e:
            print(f"Audio playback error: {e}")