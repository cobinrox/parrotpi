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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Audio constants
MAX_MIC_GAIN = 5.0
VOLUME_STEPS = 10
PARROT_MIN_PCT = 8
PARROT_MAX_PCT = 20

# FIXED PATHS
BASE_DIR = Path(__file__).parent  # /home/u/projects/parrotpi/app
AUDIO_DIR = BASE_DIR / 'static' / 'audio'
TEMPLATES_DIR = BASE_DIR / 'templates'
logging.info(f"Audio: {AUDIO_DIR.absolute()}")
logging.info(f"Templates: {TEMPLATES_DIR.absolute()}")
logging.info(f"WAVs: {[f.name for f in AUDIO_DIR.glob('*.wav')]}")

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
    logging.info("Serving index.html from app/templates/")
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
        "mombeatsme": "mombeatsme.wav",
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
                logging.info(f"HifiBerry: {i} - {dev['name']}")
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
    logging.info("Beak START")
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
                if silence_count > 10:
                    break
    finally:
        servo_pwm.ChangeDutyCycle(0)
        time.sleep(0.1)
        servo_set_position('closed')
        beak_moving = False
        logging.info("Beak STOPPED")

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
        logging.info(f"Audio stream on device {device_id}")
        sd.default.device = device_id
        audio_stream = sd.OutputStream(
            device=device_id,
            channels=2,
            samplerate=SAMPLE_RATE,
            callback=audio_callback,
            blocksize=1024
        )
        audio_stream.start()
        logging.info("Audio ready!")
        return True
    except Exception as e:
        logging.info(f"Audio failed: {e}")
        return False

def play_wav(filename):
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        logging.info(f"Missing: {filepath}")
        return

    try:
        # Always get 2D array: shape (frames, channels)
        data, fs = sf.read(str(filepath), always_2d=True)  # (N, C)

        # LOG DURATION HERE
        duration = len(data) / fs
        logging.info(f"Playing: {filename}  Duration: {duration:.2f}s ({len(data)} frames @ {fs}Hz)")


        # Parrot speed factor
        parrot_factor = 1.0 + (parrot_pct / 100.0)

        if parrot_factor != 1.0:
            # Resample each channel independently
            n_frames, n_channels = data.shape
            target_length = int(n_frames / parrot_factor)

            # Time axes as 1D
            orig_t = np.linspace(0.0, 1.0, n_frames, endpoint=False)
            new_t = np.linspace(0.0, 1.0, target_length, endpoint=False)

            new_data = np.zeros((target_length, n_channels), dtype=np.float32)
            for ch in range(n_channels):
                new_data[:, ch] = np.interp(new_t, orig_t, data[:, ch])

            data = new_data
        else:
            # Just ensure float32 and 2D
            data = data.astype(np.float32)

        # Ensure stereo output (duplicate mono if needed)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)  # (N, 2)

        # Queue in chunks
        chunk_size = 1024
        total_frames = data.shape[0]
        for i in range(0, total_frames, chunk_size):
            chunk = data[i:i + chunk_size]

            # Pad last chunk if short
            if chunk.shape[0] < chunk_size:
                pad_rows = chunk_size - chunk.shape[0]
                chunk = np.pad(chunk, ((0, pad_rows), (0, 0)))

            audio_queue.put(chunk)

        if not beak_moving:
            threading.Thread(target=animate_beak, daemon=True).start()

    except Exception as e:
        logging.info(f"Play error in play_wav({filename}): {e}")


# ===== SOCKET.IO =====
@socketio.on('mic_start')
def handle_mic_start(data):
    global mic_active
    mic_active = True
    logging.info("Mic ON")
    if not beak_moving:
        threading.Thread(target=animate_beak, daemon=True).start()

# @socketio.on('mic_chunk')
# def handle_mic_chunk(data):
#     if mic_active:
#         try:
#             audio_data = np.frombuffer(data, dtype=np.float32)
#             if len(audio_data) > 0:
#                 if len(audio_data.shape) == 1:
#                     audio_data = np.stack([audio_data, audio_data], axis=1)
#                 if len(audio_data) > 1024:
#                     audio_data = audio_data[:1024]
#                 else:
#                     audio_data = np.pad(audio_data, ((0, 1024-len(audio_data)), (0,0)))
#                 audio_queue.put(audio_data)
#         except:
#             pass
@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    if mic_active:
        try:
            # Convert buffer → numpy
            audio_data = np.frombuffer(data, dtype=np.float32)
            if len(audio_data) == 0:
                return

            # **PARROT PITCH RESAMPLING** (same as play_wav)
            parrot_factor = 1.0 + (parrot_pct / 100.0)
            
            if parrot_factor != 1.0 and len(audio_data) > 128:  # Skip tiny chunks
                # Resample this chunk (faster = higher pitch)
                orig_len = len(audio_data)
                target_len = int(orig_len / parrot_factor)
                
                orig_t = np.linspace(0.0, 1.0, orig_len, endpoint=False)
                new_t = np.linspace(0.0, 1.0, target_len, endpoint=False)
                
                # Handle mono input (browser sends mono)
                if len(audio_data.shape) == 1:
                    # Resample mono → duplicate to stereo
                    resampled_mono = np.interp(new_t, orig_t, audio_data)
                    audio_data = np.stack([resampled_mono, resampled_mono], axis=1)
                else:
                    # Stereo: resample each channel
                    audio_data = audio_data.reshape(-1, 2)
                    resampled_l = np.interp(new_t, orig_t[:len(audio_data)], audio_data[:, 0])
                    resampled_r = np.interp(new_t, orig_t[:len(audio_data)], audio_data[:, 1])
                    audio_data = np.stack([resampled_l, resampled_r], axis=1)
            
            # Ensure stereo if no resampling
            elif len(audio_data.shape) == 1:
                audio_data = np.stack([audio_data, audio_data], axis=1)

            # Pad/truncate to exact 1024 frames
            if len(audio_data) > 1024:
                audio_data = audio_data[:1024]
            else:
                pad_frames = 1024 - len(audio_data)
                audio_data = np.pad(audio_data, ((0, pad_frames), (0, 0)))

            # Queue for playback
            audio_queue.put(audio_data)

        except Exception as e:
            print(f"Mic chunk error: {e}")

@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active
    mic_active = False
    logging.info("Mic OFF")

def startup_test():
    time.sleep(2)
    logging.info("Startup...")
    play_wav('squawk3.wav')

if __name__ == '__main__':
    os.makedirs(AUDIO_DIR, exist_ok=True)
    
    try:
        logging.info("Waiting 10 seconds before attempting audio...")
        time.sleep(10)
        logging.info("...now attempting audio")
        if not init_audio():
            logging.info("Audio failed!")
            sys.exit(1)
        
        # Your startup test here
        startup_test()
        
        logging.info("ParrotPi ready! http://0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        logging.info("\nShutting down...")
    except Exception as e:
        logging.info(f"Unexpected error: {e}")
    finally:
        # CRITICAL: RELEASE AUDIO CHIP
        logging.info("Releasing audio device...")
        try:
            # Stop and close sounddevice stream
            if 'audio_stream' in globals() and audio_stream:
                audio_stream.stop()
                audio_stream.close()
                logging.info("sounddevice stream closed")
            
            # Kill any stuck ALSA processes
            os.system("sudo fuser -k /dev/snd/* 2>/dev/null")
            logging.info("ALSA processes killed")
            
            # Force ALSA reload
            os.system("sudo alsa force-reload 2>/dev/null")
            logging.info("ALSA reloaded")
            
            # GPIO cleanup
            servo_pwm.stop()
            GPIO.cleanup()
            logging.info("GPIO cleaned")
            
        except Exception as e:
            logging.info(f"Cleanup warning: {e}")
        
        logging.info("Audio chip fully released - ready for next start!")
