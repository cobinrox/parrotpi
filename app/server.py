import os
import eventlet
eventlet.monkey_patch()

import subprocess
import numpy as np
import sounddevice as sd
import time
import traceback
import threading
import queue
import logging

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO, emit

from .controller import Servo
from .controller import Audio
from .config import SERVO_PINS

print("DEVICES:", sd.query_devices())
print("DEFAULT DEVICE:", sd.default.device)

# ---------------------------------------------------------
# Global State
# ---------------------------------------------------------
opus_queue = queue.Queue(maxsize=50)
pcm_queue = queue.Queue(maxsize=50)

mic_active = False
smoothed_amp = 0.0
last_update = time.time()


# ---------------------------------------------------------
# FFmpeg Setup (Opus → PCM Float32)
# ---------------------------------------------------------
logging.info("Starting FFmpeg subprocess for Opus decoding")

ffmpeg = subprocess.Popen(
    [
        "ffmpeg",
        "-loglevel", "info",
        "-fflags", "+genpts",
        "-f", "webm",
        "-i", "pipe:0",
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", "1",
        "-ar", "48000",
        "pipe:1"
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    bufsize=0
)


def ffmpeg_writer():
    while True:
        chunk = opus_queue.get()
        logging.info(f"3. Got Opus chunk of size {len(chunk)} bytes")
        try:
            ffmpeg.stdin.write(chunk)
            ffmpeg.stdin.flush()
        except Exception as e:
            logging.error(f"FFmpeg writer error: {e}")


def ffmpeg_reader():
    while True:
        try:
            pcm_bytes = ffmpeg.stdout.read(4096)
            if pcm_bytes:
                pcm_queue.put(pcm_bytes)
        except Exception as e:
            logging.error(f"FFmpeg reader error: {e}")


# ---------------------------------------------------------
# Audio Output (Headset) — Option A: int16 RawOutputStream
# ---------------------------------------------------------
audio_stream = sd.RawOutputStream(
    samplerate=48000,
    channels=1,
    dtype="int16",      # IMPORTANT: raw int16 bytes
    blocksize=1024
)
audio_stream.start()
def play_test_tone():
    import math
    sr = audio_stream.samplerate
    t = np.linspace(0, 1, int(sr), endpoint=False)
    tone = 0.2 * np.sin(2 * math.pi * 440 * t)  # 440 Hz
    int16_tone = np.int16(tone * 32767).tobytes()
    audio_stream.write(int16_tone)

play_test_tone()



# ---------------------------------------------------------
# Background Worker: Play PCM + Move Beak
# ---------------------------------------------------------
def audio_and_beak_worker():
    global smoothed_amp, last_update, mic_active

    while True:
        try:
            pcm_bytes = pcm_queue.get()

            # Convert PCM bytes → float32 for amplitude analysis
            pcm_float = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32767.0

            # Play audio (int16 bytes)
            audio_stream.write(pcm_bytes)

            # Compute amplitude
            amplitude = np.abs(pcm_float).mean()
            smoothed_amp = 0.8 * smoothed_amp + 0.2 * amplitude

            # Update beak at 20 Hz
            now = time.time()
            if now - last_update > 0.05:
                last_update = now
                if smoothed_amp > 0.02:
                    servos['beak'].open()
                else:
                    servos['beak'].close()

        except Exception as e:
            logging.error(f"Audio/beak worker error: {e}")


threading.Thread(target=audio_and_beak_worker, daemon=True).start()


# ---------------------------------------------------------
# Flask + SocketIO Setup
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)
swagger = Swagger(app)
socketio = SocketIO(app, cors_allowed_origins="*")

socketio.start_background_task(ffmpeg_writer)
socketio.start_background_task(ffmpeg_reader)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def float32_to_int16(float32_bytes):
    """Convert WebAudio float32 PCM → int16 PCM bytes."""
    float32_array = np.frombuffer(float32_bytes, dtype=np.float32)
    int16_array = np.int16(float32_array * 32767)
    return int16_array.tobytes()


# ---------------------------------------------------------
# Socket.IO Handlers
# ---------------------------------------------------------
@socketio.on('mic_start')
def handle_mic_start():
    global mic_active
    logging.info("1. Received mic_start from client")
    mic_active = True


@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active, smoothed_amp, last_update

    mic_active = False
    logging.info("Received mic_stop from client")

    # Clear queues
    while not opus_queue.empty():
        try: opus_queue.get_nowait()
        except queue.Empty: break

    while not pcm_queue.empty():
        try: pcm_queue.get_nowait()
        except queue.Empty: break

    smoothed_amp = 0.0
    last_update = time.time()
    servos['beak'].close()


@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active
    # # Fake a loud 440 Hz tone instead of using browser audio just for testing/
    # troubleshooting
    # import math
    # sr = 48000
    # t = np.linspace(0, 0.1, int(sr * 0.1), endpoint=False)  # 100 ms
    # tone = 0.5 * np.sin(2 * math.pi * 440 * t)
    # int16_array = np.int16(tone * 32767)
    # pcm_bytes = int16_array.tobytes()
    # audio_stream.write(pcm_bytes)
    # return

    try:
        if not mic_active:
            return

        audio_bytes = data["audio"]
        float32_array = np.frombuffer(audio_bytes, dtype=np.float32)
        print("mic_chunk min/max:", float32_array.min(), float32_array.max())

        pcm_bytes = float32_to_int16(audio_bytes)

        audio_stream.write(pcm_bytes)  # direct write, no queue

    except Exception:
        logging.error("ERROR in mic_chunk handler", exc_info=True)
    return


    # try:
    #     global mic_active

    #     if not mic_active:
    #         logging.warning("Received mic_chunk while mic inactive, ignoring")
    #         return

    #     audio_bytes = data["audio"]  # float32 PCM from browser

    #     # Convert float32 → int16
    #     pcm_bytes = float32_to_int16(audio_bytes)

    #     # Queue for playback + beak animation
    #     pcm_queue.put(pcm_bytes)

    #     logging.info(f"mic_chunk: queued {len(pcm_bytes)} bytes")

    # except Exception as e:
    #     logging.error("ERROR in mic_chunk handler", exc_info=True)


# ---------------------------------------------------------
# Servo Initialization
# ---------------------------------------------------------
def create_servo(name, pin):
    logging.info(f"Initializing servo '{name}' on GPIO pin {pin}")
    return Servo(pin)


servos = {
    name: create_servo(name, pin)
    for name, pin in SERVO_PINS.items()
}

audio = Audio()


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    logging.info("Received ping request")
    return jsonify({"status": "ok"})


@app.route("/say", methods=["POST"])
def servo_say():
    data = request.get_json(silent=True) or {}
    phrase = data.get("phrase")

    duration = audio.get_wav_duration(audio._resolve_path("piano2.wav"))
    logging.info(f"Received SAY request for phrase: [{phrase}], duration [{duration}]")

    audioThread = audio.play("piano2.wav")
    logging.info("Started audio thread, now controlling beak while audio plays")

    for _ in range(20):
        if audio.current_play_obj:
            break
        time.sleep(0.01)

    while audio.current_play_obj and audio.current_play_obj.is_playing():
        servos['beak'].open()
        time.sleep(0.1)
        servos['beak'].close()
        time.sleep(0.1)

    servos['beak'].close()
    return jsonify({"action": "say", "phrase": phrase})


@app.route("/servo/<name>/open", methods=["POST"])
def servo_open(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].open()
    return jsonify({"servo": name, "action": "open"})


@app.route("/servo/<name>/close", methods=["POST"])
def servo_close(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].close()
    return jsonify({"servo": name, "action": "close"})


@app.route("/servo/<name>/mid", methods=["POST"])
def servo_mid(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].mid()
    return jsonify({"servo": name, "action": "mid"})


@app.route("/servo/<name>/set", methods=["POST"])
def servo_set(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    data = request.get_json(silent=True) or {}
    value = data.get("value")

    try:
        value = float(value)
    except:
        return jsonify({"error": "'value' must be a float"}), 400

    if not -1.0 <= value <= 1.0:
        return jsonify({"error": "'value' must be between -1.0 and 1.0"}), 400

    servos[name].set(value)
    return jsonify({"servo": name, "action": "set", "value": value})


@app.route("/servo/<name>/relax", methods=["POST"])
def servo_relax(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].relax()
    return jsonify({"servo": name, "action": "relax"})


# ---------------------------------------------------------
# Start Function
# ---------------------------------------------------------
def start():
    logging.info("Starting Flask server...")
    logging.info("Bring up browser to https://parrotpi")
    logging.info("We are runing Caddy which allows us https and port 443/80")
    socketio.run(app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    start()
