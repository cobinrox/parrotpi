import eventlet
eventlet.monkey_patch()
import subprocess
import numpy as np
import sounddevice as sd
import time

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO, emit


from .controller import Servo # import either sim or real hw servo based on config
from .controller import Audio # import either sim or real hw audio based on config
from .config import SERVO_PINS

import logging
import time
import numpy as np
import sounddevice as sd

#decoder = av.CodecContext.create("opus", "r")

ffmpeg = subprocess.Popen(
    [
        "ffmpeg",
        "-loglevel", "quiet",
        "-i", "pipe:0",
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", "1",
        "-ar", "48000",
        "pipe:1"
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)

audio_stream = sd.OutputStream(samplerate=48000, channels=1)
audio_stream.start()

smoothed_amp = 0.0
last_update = time.time()




# ---------------------------------------------------------
# socketio setup for receiving mic audio chunks (not fully implemented yet)
# ---------------------------------------------------------



# ---------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.info("Starting server.py")

# ---------------------------------------------------------
# Flask Setup
# ---------------------------------------------------------
app = Flask(__name__)
CORS(app)
swagger = Swagger(app)
socketio = SocketIO(app, cors_allowed_origins="*")
smoothed_amp = 0.0
last_update = time.time()

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global smoothed_amp, last_update

    audio_bytes = data['audio']

    try:
        # Feed WebM/Opus chunk to FFmpeg
        ffmpeg.stdin.write(audio_bytes)

        # Read decoded PCM (float32)
        pcm = ffmpeg.stdout.read(len(audio_bytes) * 4)
        if not pcm:
            return

        pcm = np.frombuffer(pcm, dtype=np.float32)

        # Play audio
        audio_stream.write(pcm)

        # Compute amplitude
        amplitude = np.abs(pcm).mean()
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
        logging.error(f"Decode error: {e}")
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
audio = Audio()  # Initialize audio system (real or simulated)


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    """
    Heartbeat check
    ---
    responses:
      200:
        description: OK
    """
    logging.info("Received ping request")
    return jsonify({"status": "ok"})

# -----------------------------
# Say phrase
# -----------------------------
@app.route("/say", methods=["POST"])
def servo_say():
    data = request.get_json(silent=True) or {}
    phrase = data.get("phrase")
    duration = audio.get_wav_duration(audio._resolve_path("piano2.wav"))
    logging.info(f"Received SAY request for phrase: [%s], duration [%s]", phrase, duration.toString())

    audioThread = audio.play("piano2.wav")  # Start audio in separate thread
    logging.info("Started audio thread, now controlling beak while audio plays")
    logging.info(f"checking current_play_obj at start of loop: {audio.current_play_obj}")
    # Wait until current_play_obj is set by the audio thread (with a timeout)
    for _ in range(20):
        if audio.current_play_obj:
            logging.info(f"Audio thread ready: {audio.current_play_obj.is_playing()}")
            break
        time.sleep(0.01)

    logging.info(f"current_play_obj after wait: {audio.current_play_obj}")



    while audio.current_play_obj and audio.current_play_obj.is_playing():
        logging.info("Audio is still playing, opening beak")
        servos['beak'].open()
        time.sleep(0.1)
        logging.info("Closing beak")
        servos['beak'].close()
        time.sleep(0.1)
    logging.info("Audio finished, ensuring beak is closed")
    servos['beak'].close()
    return jsonify({ "action": "say", "phrase": phrase})


# -----------------------------
# Basic open/close
# -----------------------------
@app.route("/servo/<name>/open", methods=["POST"])
def servo_open(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    # Read optional phrase from JSON body (may be empty or null)
    #data = request.get_json(silent=True) or {}
    #phrase = data.get("phrase")

    #if phrase:
    #    logging.info(f"Route: /servo/{name}/open -> phrase: {phrase}")
   # else:
    #    logging.info(f"Route: /servo/{name}/open -> no phrase provided")

    servos[name].open()
    return jsonify({"servo": name, "action": "open"})


@app.route("/servo/<name>/close", methods=["POST"])
def servo_close(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/close")
    servos[name].close()
    return jsonify({"servo": name, "action": "close"})


# -----------------------------
# New: mid/neutral
# -----------------------------
@app.route("/servo/<name>/mid", methods=["POST"])
def servo_mid(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/mid")
    servos[name].mid()
    return jsonify({"servo": name, "action": "mid"})


# -----------------------------
# New: set(value)
# -----------------------------
@app.route("/servo/<name>/set", methods=["POST"])
def servo_set(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    data = request.get_json(silent=True) or {}
    value = data.get("value")

    if value is None:
        return jsonify({"error": "Missing 'value' in JSON body"}), 400

    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "'value' must be a float"}), 400

    if not -1.0 <= value <= 1.0:
        return jsonify({"error": "'value' must be between -1.0 and 1.0"}), 400

    logging.info(f"Route: /servo/{name}/set -> {value}")
    servos[name].set(value)
    return jsonify({"servo": name, "action": "set", "value": value})


# -----------------------------
# New: relax()
# -----------------------------
@app.route("/servo/<name>/relax", methods=["POST"])
def servo_relax(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/relax")
    servos[name].relax()
    return jsonify({"servo": name, "action": "relax"})


# ---------------------------------------------------------
# Start Function
# ---------------------------------------------------------
def start():
    logging.info("Starting Flask server...")
    #app.run(host="0.0.0.0", port=5000, threaded=True)
    print("async_mode =", socketio.async_mode)
    socketio.run(app,host="0.0.0.0", port=5000)


if __name__ == "__main__":
    logging.info("Running server.py directly")
    start()