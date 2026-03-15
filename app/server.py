from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import RPi.GPIO as GPIO
import warnings
import logging
warnings.filterwarnings("ignore", category=RuntimeWarning)

import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import time
import os
import queue
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)

# Audio constants
MAX_MIC_GAIN = 5.0
VOLUME_STEPS = 10
PARROT_MIN_PCT = 8
PARROT_MAX_PCT = 20

# FIXED PATHS
BASE_DIR = Path(__file__).parent  # /home/u/projects/parrotpi/app
AUDIO_DIR = BASE_DIR / 'static' / 'audio'
TEMPLATES_DIR = BASE_DIR / 'templates'
print(f"🎵 Audio: {AUDIO_DIR.absolute()}")
print(f"📄 Templates: {TEMPLATES_DIR.absolute()}")
print(f"🎵 WAVs: {[f.name for f in AUDIO_DIR.glob('*.wav')]}")

# FIXED: Explicit template_folder!
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.config['SECRET_KEY'] = 'parrotpi-secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# GPIO Setup
GPIO.setwarnings(False)
SERVO_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

# Globals
SAMPLE_RATE = 44100
mic_gain = 1.0
parrot_pct = 8

audio_queue = queue.Queue()
audio_stream = None
mic_active = False
beak_moving = False

# Beak servo positions
BEAK_POSITIONS = {
    'closed': 2.5,
    'mid': 7.5,  
    'open': 12.5
}

# ===== YOUR EXACT ROUTES =====
@app.route("/")
def index():
    print("📄 Serving index.html from app/templates/")
    return render_template("index.html")

@app.route('/volume')
def get_volume():
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})

@app.route('/volUp', methods=['POST'])
def volume_up():
    global mic_gain
    step = MAX_MIC_GAIN / VOLUME_STEPS
    mic_gain = min(MAX_MIC_GAIN, mic_gain + step)
    logging.info(f"Volume up to {mic_gain / MAX_MIC_GAIN:.1%}")
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})

@app.route('/volDown', methods=['POST'])
def volume_down():
    global mic_gain
    step = MAX_MIC_GAIN / VOLUME_STEPS
    mic_gain = max(0.0, mic_gain - step)
    logging.info(f"Volume down to {mic_gain / MAX_MIC_GAIN:.1%}")
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})

@app.route('/volume/<int:percent>', methods=['POST'])
def set_volume(percent):
    global mic_gain
    mic_gain = max(0.0, min(MAX_MIC_GAIN, (percent / 100.0) * MAX_MIC_GAIN))
    return jsonify({'volume': percent})

@app.route('/parrot')
def get_parrot():
    return jsonify({'parrot': parrot_pct})

@app.route('/parrot/<int:percent>', methods=['POST'])
def set_parrot(percent):
    global parrot_pct
    parrot_pct = max(PARROT_MIN_PCT, min(PARROT_MAX_PCT, percent))
    logging.info(f"Parrot pitch set to {parrot_pct}%")
    return jsonify({'parrot': parrot_pct})

@app.route("/servo/beak/open", methods=["POST"])
def beak_open():
    servo_set_position('open')
    return jsonify({"status": "beak opened"})

@app.route("/servo/beak/close", methods=["POST"])
def beak_close():
    servo_set_position('closed')
    return jsonify({"status": "beak closed"})

@app.route("/say", methods=["POST"])
def say():
    data = request.get_json()
    phrase = data.get("phrase", "").strip()
    logging.info(f"SAY: {phrase}")

    phrase_map = {
        "Does He Talk": "doesthebirdtalk.wav",
        "Squawk3": "squawk3.wav",
        "F#$@!!": "curse.wav",
        "Hi": "piano2.wav",
        "test": "test.wav"
    }

    filename = phrase_map.get(phrase, "squawk3.wav")
    play_wav(filename)
    return jsonify({"status": "played", "file": filename})

# ===== AUDIO ENGINE =====
def find_audio_device():
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if "hifiberry" in dev['name'].lower() or "pcm5102a" in dev['name'].lower():
                print(f"✅ HifiBerry: {i} - {dev['name']}")
                return i
        return 0
    except:
        return 0

def servo_set_position(position):
    duty = BEAK_POSITIONS.get(position, 7.5)
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.15)
    servo_pwm.ChangeDutyCycle(0)

def animate_beak():
    global beak_moving, audio_stream, mic_active
    beak_moving = True
    print("🦜 Beak START")
    try:
        silence_count = 0
        while audio_stream and audio_stream.active:
            if mic_active or not audio_queue.empty():
                silence_count = 0
                servo_set_position('open')
                time.sleep(0.08)
                servo_set_position('closed')
                time.sleep(0.08)
            else:
                silence_count += 1
                time.sleep(0.1)
                if silence_count > 50:
                    break
    finally:
        servo_pwm.ChangeDutyCycle(0)
        time.sleep(0.1)
        servo_set_position('closed')
        beak_moving = False
        print("🦜 Beak STOPPED")

def audio_callback(outdata, frames, time_info, status):
    try:
        data = audio_queue.get_nowait()
        parrot_factor = 1.0 + (parrot_pct / 100.0)
        data = np.clip(data * mic_gain * parrot_factor * 2.0, -1.0, 1.0)
        outdata[:] = data[:frames]
        audio_queue.task_done()
    except queue.Empty:
        outdata.fill(0)

def init_audio():
    global audio_stream
    device_id = find_audio_device()
    try:
        print(f"🎵 Audio stream on device {device_id}")
        sd.default.device = device_id
        audio_stream = sd.OutputStream(
            device=device_id,
            channels=2,
            samplerate=SAMPLE_RATE,
            callback=audio_callback,
            blocksize=1024
        )
        audio_stream.start()
        print("✅ Audio ready!")
        return True
    except Exception as e:
        print(f"❌ Audio failed: {e}")
        return False

def play_wav(filename):
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        print(f"❌ Missing: {filepath}")
        return
    try:
        print(f"🎵 Playing: {filename}")
        data, fs = sf.read(str(filepath))
        parrot_factor = 1.0 + (parrot_pct / 100.0)
        if parrot_factor != 1.0:
            target_length = int(len(data) / parrot_factor)
            time_axis = np.linspace(0, len(data)/fs, target_length)
            orig_time = np.linspace(0, 1, len(data))
            data = np.interp(time_axis, orig_time, data)
        if len(data.shape) == 1:
            data = np.stack([data, data], axis=1)
        data = data.astype(np.float32)
        chunk_size = 1024
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, ((0, chunk_size-len(chunk)), (0,0)))
            audio_queue.put(chunk)
        if not beak_moving:
            threading.Thread(target=animate_beak, daemon=True).start()
    except Exception as e:
        print(f"❌ Play error: {e}")

# ===== SOCKET.IO =====
@socketio.on('mic_start')
def handle_mic_start(data):
    global mic_active
    mic_active = True
    print("🎤 Mic ON")
    if not beak_moving:
        threading.Thread(target=animate_beak, daemon=True).start()

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    if mic_active:
        try:
            audio_data = np.frombuffer(data, dtype=np.float32)
            if len(audio_data) > 0:
                if len(audio_data.shape) == 1:
                    audio_data = np.stack([audio_data, audio_data], axis=1)
                if len(audio_data) > 1024:
                    audio_data = audio_data[:1024]
                else:
                    audio_data = np.pad(audio_data, ((0, 1024-len(audio_data)), (0,0)))
                audio_queue.put(audio_data)
        except:
            pass

@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active
    mic_active = False
    print("🔇 Mic OFF")

def startup_test():
    time.sleep(2)
    print("🦜 Startup...")
    play_wav('squawk3.wav')

if __name__ == '__main__':
    os.makedirs(AUDIO_DIR, exist_ok=True)
    if not init_audio():
        print("❌ Audio init failed!")
        sys.exit(1)
    threading.Thread(target=startup_test, daemon=True).start()
    print("🌐 ParrotPi ready! http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
