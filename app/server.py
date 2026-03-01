import os
import eventlet
eventlet.monkey_patch()

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

logging.basicConfig(level=logging.INFO)

print("DEVICES:", sd.query_devices())
print("DEFAULT DEVICE:", sd.default.device)

# ---------------------------------------------------------
# Global State
# ---------------------------------------------------------
mic_active = False
playback_queue = queue.Queue(maxsize=200)

# ---------------------------------------------------------
# Audio Output Stream (callback-based)
# ---------------------------------------------------------
def audio_callback(outdata, frames, time_info, status):
    """Sounddevice pulls audio at the correct pace."""
    try:
        chunk = playback_queue.get_nowait()
    except queue.Empty:
        # No audio ready → output silence (prevents ALSA underrun)
        outdata[:] = b'\x00' * (frames * 2)
        return

    # Pad if chunk is short
    needed = frames * 2
    if len(chunk) < needed:
        chunk = chunk + b'\x00' * (needed - len(chunk))

    outdata[:] = chunk


audio_stream = sd.RawOutputStream(
    samplerate=48000,
    channels=1,
    dtype="int16",
    blocksize=1024,
    callback=audio_callback
)

audio_stream.start()

# ---------------------------------------------------------
# Debug: Play a test tone at startup
# ---------------------------------------------------------
def play_test_tone():
    import math
    sr = audio_stream.samplerate
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    tone = 0.2 * np.sin(2 * math.pi * 440 * t)
    int16_tone = np.int16(tone * 32767).tobytes()

    # Split into 1024‑frame chunks (2048 bytes)
    chunk_size = 1024 * 2  # frames * bytes_per_frame
    for i in range(0, len(int16_tone), chunk_size):
        chunk = int16_tone[i:i+chunk_size]
        playback_queue.put(chunk)

play_test_tone()

# ---------------------------------------------------------
# Utility: Float32 → Int16
# ---------------------------------------------------------
def float32_to_int16(float32_bytes):
    arr = np.frombuffer(float32_bytes, dtype=np.float32)
    int16 = np.int16(arr * 32767)
    return int16.tobytes()

# ---------------------------------------------------------
# Flask + Socket.IO Setup
# ---------------------------------------------------------
app = Flask(__name__)
CORS(app)
swagger = Swagger(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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
    global mic_active
    logging.info("Received mic_stop from client")
    mic_active = False

    # Clear queue
    while not playback_queue.empty():
        try: playback_queue.get_nowait()
        except queue.Empty: break


@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active
    if not mic_active:
        return

    try:
        audio_bytes = data["audio"]
        print("len(audio_bytes) =", len(audio_bytes))

        float32_array = np.frombuffer(audio_bytes, dtype=np.float32)
        print("mic_chunk min/max:", float32_array.min(), float32_array.max())

        pcm_bytes = float32_to_int16(audio_bytes)

        try:
            playback_queue.put_nowait(pcm_bytes)
        except queue.Full:
            # Drop if behind
            pass

    except Exception:
        logging.error("ERROR in mic_chunk handler", exc_info=True)

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

def start():
    logging.info("Starting Flask server...")
    logging.info("Bring up browser to https://parrotpi")
    logging.info("We are running Caddy which allows us https and port 443/80")
    socketio.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    start()