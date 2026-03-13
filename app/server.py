import os
import subprocess
from pathlib import Path

import eventlet
eventlet.monkey_patch()

import math
import numpy as np
import sounddevice as sd

import time
import traceback
import threading
import logging
import numpy as np

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO, emit
from flask import current_app
from .controller import Servo
from .controller import Audio
from .config import SERVO_PINS

logging.basicConfig(level=logging.INFO)

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
mic_buffer = b""

def wait_for_audio_devices(timeout=10, interval=0.5):
    """
    Wait until sounddevice reports at least one audio device.
    Returns True if devices appear, False if timeout expires.
    """
    print("Waiting for audio devices...")

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            devices = sd.query_devices()
            if devices:
                print("Audio devices detected:")
                print(devices)
                return True
        except Exception as e:
            print(f"Error querying devices: {e}")

        print("No devices yet, retrying...")
        time.sleep(interval)

    print("Timed out waiting for audio devices.")
    return False

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
audio = Audio()

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


# Global flag to track current audio
current_audio_active = False
audio_lock = threading.Lock()

@app.route("/say", methods=["POST"])
def servo_say():
    global current_audio_active, bird
    data = request.get_json(silent=True) or {}
    phrase = data.get("phrase", "")
    logging.info("SAY [" + phrase + "]")
    if phrase == "Does He Talk":
        phrase = f"doesthebirdtalk"
    else:
        if phrase == "F#$@!!":
            phrase = "curse"
        else:
            phrase = "squawk3"
    # Prevent overlapping aplay calls
    with audio_lock:
        if current_audio_active:
            logging.info("Audio busy, rejecting SAY")
            return jsonify({"status": "busy"}), 202
        current_audio_active = True

    # Quick beak twitch to show immediate response
    print("     beak open",flush=True)
    #servos['beak'].open ()
    time.sleep(0.05)
    print("     beak close",flush=True)
    #servos['beak'].close()
    def audio_and_beak():
        global current_audio_active,bird
        logging.info("Starting audio_and_beak thread...")
        audioProcess = None
        try:
            audio_path = audio._resolve_path(phrase.lower() + ".wav")
            duration = audio.get_wav_duration(audio_path)
            logging.info(f"Prepping: [{audio_path}] (duration: [{duration:.2f}]s)")
            
            logging.info("Opening audioProcess")

            audioProcess = subprocess.Popen([
                'aplay', "-D", "plughw:0,0", "-c", "2",audio_path
              ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            #subprocess.run(["aplay", "-D", "plughw:0,0", "-c", "2", audio_path])

            # Animate beak during playback
            start_time = time.time()
            end_time = None
            while time.time() - start_time < duration + 0.3:
                print("     beak open", flush=True)
                #servos['beak'].open ()
                time.sleep(0.15)
                print("     beak close", flush=True)
                #servos['beak'].close ()
                time.sleep(0.12)
                end_time = time.time()
            actual_duration = end_time - start_time if end_time else 0
            logging.info(f"Beak loop took {actual_duration:.2f}s")                
            # Wait a tiny bit for ALSA to fully release the device
            if audioProcess is not None:
                logging.info("audioProcess was NOT yet done, waiting")
                audioProcess.wait(timeout=1)    
            # Clean up audioProcess
            try:
                logging.info("Terminate audioProcess thread")
                audioProcess.terminate()
                audioProcess.wait(timeout=1)
            except:
                audioProcess.kill()
                
        except Exception as e:
            logging.error(f"Audio/beak error: {e}")
        finally:
            if audioProcess is not None and audioProcess.poll() is None:
                try:
                    logging.info("Terminate audioProcess")
                    audioProcess.terminate()
                    audioProcess.wait(timeout=1)
                except Exception:
                    audioProcess.kill()

            logging.info("End audioProcess thread")
            with audio_lock:
                current_audio_active = False
    # Start async thread
    thread = threading.Thread(target=audio_and_beak, daemon=True)
    thread.start()
    logging.info(f"Returning for SAY [{phrase}]")
    return jsonify({"status": "playing", "phrase": phrase}), 202                
    


# Optional: Add endpoint to check status
@app.route("/audio-status")
def audio_status():
    with audio_lock:
        return jsonify({"is_playing": current_audio_active})


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
    wait_for_audio_devices()
    hifiberry_idx = find_hifiberry_device()
    if hifiberry_idx is not None:
        device_name = hifiberry_idx
    else:
        # As a fallback, use a known-good hardware index (0 on your system)
        # instead of the string 'default'
        print("No HifiBerry DAC found by name; falling back to card index 0")
        device_name = 0
    print("Playing start up tone")
    #subprocess.run(["aplay", "-D", "plughw:0,0", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])
    #subprocess.run(["aplay", "-D", "dmix0", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])
    subprocess.run(["aplay", "-D", "plughw:0,0", "-c", "2", "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"])

    logging.info("Starting Flask server...")
    logging.info("Bring up browser to https://parrotpi")
    logging.info("We are running Caddy which allows us https and port 443/80")
    socketio.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    start()
