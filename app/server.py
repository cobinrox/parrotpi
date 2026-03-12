import os
import subprocess
from pathlib import Path

import eventlet
eventlet.monkey_patch()

import math
import numpy as np
import sounddevice as sd
print("Sound devices:")
print(sd.query_devices())

#print ("EXITING NOW!")
#import sys
#sys.exit()

import time
import traceback
import threading
import queue
import logging

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO, emit
from flask import current_app
from .controller import Servo
from .controller import Audio
from .config import SERVO_PINS

logging.basicConfig(level=logging.INFO)

print("DEVICES:", sd.query_devices(),flush=True)
print("DEFAULT DEVICE:", sd.default.device)

# ---------------------------------------------------------
# Global State
# ---------------------------------------------------------
bird=os.getenv("BIRD", "big") 
print("Starting with bird=", bird)
print("You can set bird to big or small in local parrotpi.env")
print("or, for a service, in /etc/parrotpi.env")
print("Or just override in the source right here if you want:")
#bird=small
mic_active = False
#playback_queue = queue.Queue(maxsize=10)

def audio_callback(outdata, frames, time, status):
    global playback_queue
    print(f"Audio callback: frames = {frames} status = {status}",flush=True)
    out = np.frombuffer(outdata, dtype=np.int16)
    try:
        chunk = playback_queue.get_nowait()
        data = np.frombuffer(chunk, dtype=np.int16)
        print("Callback got data:", len(data), "samples", "min =", data.min(), "max =", data.max(),flush=True)
        if len(data) < frames:
            padded = np.zeros(frames, dtype=np.int16)
            padded[:len(data)] = data
            out[:] = padded
        else:
            out[:] = data[:frames]
    except queue.Empty:
        out[:] = 0

def find_hifiberry_device():
    """
    Detect the HifiBerry DAC automatically.
    Returns device index if found, else None.
    """
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        name = dev["name"].lower()
        if ("hifiberry" in name or "snd_rpi_hifiberry" in name) and dev["max_output_channels"] > 0:
            print(f"Found HifiBerry DAC at device index {idx}: {dev['name']}")
            return idx
    return None

# Prefer HifiBerry directly; skip Pulse unless you really need it
hifiberry_idx = find_hifiberry_device()
if hifiberry_idx is not None:
    device_name = hifiberry_idx
else:
    # As a fallback, use a known-good hardware index (0 on your system)
    # instead of the string 'default'
    print("No HifiBerry DAC found by name; falling back to card index 0")
    device_name = 0
    # If you prefer to fail fast instead of guessing:
    # raise RuntimeError("No HifiBerry DAC found and no fallback configured")

# try:
#     audio_stream = sd.RawOutputStream(
#         samplerate=48000,
#         channels=1,
#         dtype="int16",
#         blocksize=1024,
#         device=device_name,
#         callback=audio_callback,
#     )
#     audio_stream.start()
# except Exception as e:
#     print(f"Failed to open audio stream on {device_name}: {e}")
#     raise
# def play_test_tone(frequency=440.0, duration=0.25, amplitude=0.2):
#     # Replace startup tone with aplay too:
#     subprocess.run(["aplay", "-D", "plughw:0,0", "/home/pi/projects/parrotpi/app/static/audio/squawk3.wav"])

#     # global playback_queue
#     # print(f"Playing test tone at {frequency} Hz for {duration} seconds",flush=True)
#     # sr = audio_stream.samplerate
#     # t = np.linspace(0, duration, int(sr * duration), endpoint=False)
#     # tone = amplitude * np.sin(2 * math.pi * frequency * t)
#     # int16_tone = np.int16(tone * 32767).tobytes()

#     # # Split into 1024-frame chunks for the callback
#     # chunk_size = 1024 * 2  # frames * bytes per frame
#     # for i in range(0, len(int16_tone), chunk_size):
#     #     playback_queue.put(int16_tone[i:i + chunk_size])
#     # print("Test tone queued for playback",flush=True)

# # Play the startup tone
# play_test_tone()
print("Playing start up tone")
#subprocess.run(["aplay", "-D", "plughw:0,0", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])
#subprocess.run(["aplay", "-D", "dmix0", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])
subprocess.run(["aplay", "-D", "plughw:0,0", "-c", "2", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])
print("Startup done - now start mic stream")

# NOW start mic stream (AFTER aplay finishes)
import queue
import numpy as np
import sounddevice as sd

#playback_queue = queue.Queue(maxsize=10)
mic_buffer = b""
mic_active = False
# ---------------------------------------------------------
# Utility: Float32 → Int16
# ---------------------------------------------------------
def float32_to_int16(float32_bytes):
    arr = np.frombuffer(float32_bytes, dtype=np.float32)
    int16 = np.int16(arr * 32767)
    return int16.tobytes()

def float32_to_int16_stereo(float32_bytes):
    """Convert browser mic float32 mono → stereo int16 for MAX98357A"""
    # 4096 float32 bytes = 1024 mono samples
    float32_mono = np.frombuffer(float32_bytes, dtype=np.float32)
    # Convert to int16 mono [-32768, 32767]
    int16_mono = np.int16(float32_mono * 32767.0).astype(np.int16)
    # Duplicate to stereo (L=R for mono mic)
    stereo = np.column_stack([int16_mono, int16_mono])  # (1024, 2)
    return stereo.tobytes()  # 4096 bytes (1024 frames * 2ch * 2bytes)
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

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active, mic_buffer
    if not mic_active:
        return

    try:
        audio_bytes = data["audio"]
        pcm_bytes = float32_to_int16_stereo(audio_bytes)
        
        # Buffer 3 chunks (~60ms), then play
        mic_buffer += pcm_bytes
        if len(mic_buffer) >= 3 * 4096:  # 3 chunks = ~60ms
            # Pipe to aplay (non-blocking)
            p = subprocess.Popen([
                "aplay", "-D", "plughw:0,0", "-f", "S16_LE", "-r", "48000", "-c", "2"
            ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.stdin.write(mic_buffer)
            p.stdin.close()
            mic_buffer = b""  # Clear buffer
    except:
        pass

@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active, mic_buffer
    mic_active = False
    mic_buffer = b""  # Clear leftover
#mic_stream.start()
#print("Mic stream ready",flush=True)
# ---------------------------------------------------------
# Servo Initialization
# ---------------------------------------------------------
# def create_servo(name, pin):
#     logging.info(f"Initializing servo '{name}' on GPIO pin {pin}")
#     return Servo(pin)

# servos = {
#     name: create_servo(name, pin)
#     for name, pin in SERVO_PINS.items()
# }
#playback_queue = queue.Queue(maxsize=10)
#mic_stream = sd.RawOutputStream(...)  # background, silent
#mic_stream.start()
#print("Mic stream ready")
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
    #global mic_stream
    #mic_stream.stop()
    global bird
    data = request.get_json(silent=True) or {}
    phrase = data.get("phrase")

    duration = audio.get_wav_duration(audio._resolve_path("piano2.wav"))
    logging.info(f"Received SAY request for phrase: [{phrase}], duration [{duration}]")
    if phrase == "Does He Talk":
        title = "doesthebirdtalk.wav"
    else:
        if phrase == "F#$@!!":
           title = "curse.wav"
        else:
            title = phrase.lower() + ".wav"
    base_path = Path(current_app.root_path)
    audio_path = base_path / "static" / "audio" / title

    if audio_path.is_file():
        audioThread = audio.play(str(audio_path))
    else:
        current_app.logger.error(f"Missing audio file: {audio_path}")
        audioThread = audio.play("squawk3.wav")  # fallback to a default sound
    #audioThread = audio.play(title)
    logging.info("Started audio thread, now controlling beak while audio plays")

    for _ in range(20):
        if audio.current_play_obj:
            break
        time.sleep(0.01)

    while audio.current_play_obj and audio.current_play_obj.is_playing():
        if bird == 'big':
           #servos['beak'].open()
           time.sleep(0.1)
           #servos['beak'].close()
           time.sleep(0.1)
           #servos['beak'].open()
           time.sleep(0.1)
           #servos['beak'].close()
           time.sleep(0.1)
           #servos['beak'].open()
           time.sleep(0.1)
           #servos['beak'].close()
           time.sleep(0.1)
        else:
           #servos['beak'].open()
           time.sleep(0.1)
           #servos['beak'].close()
           time.sleep(0.1)

    if bird == 'big':
       #servos['beak'].close()
       time.sleep(0.1)
       #servos['beak'].close()
       time.sleep(0.1)
       #servos['beak'].close()
    else:
       #servos['beak'].close()
       time.sleep(0.1)
    #mic_stream.start()
    return jsonify({"action": "say", "phrase": phrase})

@app.route("/servo/<name>/open", methods=["POST"])
def servo_open(name):
    logging.info(f"Received request to open servo '{name}'")
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].open()
    return jsonify({"servo": name, "action": "open"})

@app.route("/servo/<name>/close", methods=["POST"])
def servo_close(name):
    logging.info(f"Received request to close servo '{name}'")
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].close()
    return jsonify({"servo": name, "action": "close"})

@app.route("/servo/<name>/mid", methods=["POST"])
def servo_mid(name):
    logging.info(f"Received request to mid servo '{name}'")
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404
    servos[name].mid()
    return jsonify({"servo": name, "action": "mid"})

@app.route("/servo/<name>/set", methods=["POST"])
def servo_set(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    data = request.get_json(silent=True) or {}
    logging.info(f"Received request to set servo '{name}' with data: {data}")
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
def amixer(cmd):
    subprocess.run(["amixer", "set", "Master", cmd], stdout=subprocess.PIPE)

def get_volume():
    return 0
    # Example amixer output line:
    #   Mono: Playback 74 [58%] [-16.50dB] [on]
    # out = subprocess.check_output(["amixer", "get", "Master"]).decode()
    # for line in out.splitlines():
    #     if "%" in line:
    #         # Extract the first [XX%]
    #         start = line.find("[") + 1
    #         end = line.find("%")
    #         return int(line[start:end])
    # return 0
@app.get("/volume")
def volume_get():
    return jsonify({"volume": get_volume()})    
@app.post("/volUp")
def volume_up():
    amixer("5%+")
    return jsonify({"volume": get_volume()})

@app.post("/volDown")
def volume_down():
    amixer("5%-")
    return jsonify({"volume": get_volume()})



def start():
    logging.info("Starting Flask server...")
    logging.info("Bring up browser to https://parrotpi")
    logging.info("We are running Caddy which allows us https and port 443/80")
    socketio.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    start()
