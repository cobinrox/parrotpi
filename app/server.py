import os
import eventlet
eventlet.monkey_patch(thread=False)
import time
import threading
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO, emit
from flask import current_app
import sounddevice as sd
import soundfile as sf
from gpiozero import Servo
import numpy as np
import sounddevice as sd


mic_active = False
mic_stream = None
mic_buffer = bytearray()

# 48kHz stereo output for mic playback
MIC_RATE = 48000
MIC_CHANNELS = 2
MIC_BLOCK = 1024
mic_gain = 8.0

app = Flask(__name__)
CORS(app)
swagger = Swagger(app)
#socketio = SocketIO(app, cors_allowed_origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", binary=True)

# ---------------------------------------------------------
# Servo setup
# ---------------------------------------------------------
servo = Servo(17)
servo.detach()


# ---------------------------------------------------------
# Audio device selection + fallback
# ---------------------------------------------------------
def wait_for_alsa(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if len(sd.query_devices()) > 0:
                return True
        except:
            pass
        time.sleep(0.25)
    return False


def wait_for_device(device_index, timeout=8, interval=0.5):
    """
    Waits for a specific output device index to appear.
    Returns True if ready, False if timed out.
    """
    print(f"Waiting for audio device {device_index}...")

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            devices = sd.query_devices()
            if 0 <= device_index < len(devices):
                print(f"Device {device_index} ready: {devices[device_index]['name']}")
                return True
        except Exception as e:
            print("Error querying devices:", e)

        print("Device not ready, retrying...")
        time.sleep(interval)

    print(f"Timed out waiting for device {device_index}")
    return False


def choose_output_device():
    devices = sd.query_devices()

    if not devices:
        print("No audio devices found at all.")
        return None

    # Prefer I2S DAC by name
    for idx, dev in enumerate(devices):
        name = dev["name"].lower()
        if (
            "snd_rpi_hifiberry" in name or
            "max98357" in name or
            "i2s" in name
        ) and dev["max_output_channels"] >= 2:
            print(f"Using I2S device {idx}: {dev['name']}")
            return idx

    # Fallback: any stereo output
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] >= 2:
            print(f"Using fallback device {idx}: {dev['name']}")
            return idx

    print("No usable audio output devices found.")
    return None
def startup_test_squawk():
    """
    Plays squawk3.wav once at server startup to verify audio device health.
    Runs in a background thread so it doesn't block Flask.
    """
    time.sleep(6)  # allow systemd + I2S to settle

    test_path = os.path.join("app", "static", "audio", "squawk3.wav")

    print("\n=== STARTUP AUDIO TEST ===")
    if not wait_for_alsa():
        print("ALSA not ready, skipping startup test.")
    else:
        print(f"Testing audio playback with: {test_path}")
        try:
            #sd._terminate()
            #sd._initialize()
            play_with_beak(test_path)
            print("Startup audio test completed.")
        except Exception as e:
            print("Startup audio test FAILED:", e)
        print("=== END STARTUP TEST ===\n")

# ---------------------------------------------------------
# Beak animation thread
# ---------------------------------------------------------
def beak_motion(stop_event):
    while not stop_event.is_set():
        servo.max()
        time.sleep(0.15)
        servo.min()
        time.sleep(0.15)
    servo.min()  # close beak when done
    time.sleep(0.1)
    servo.detach()

# ---------------------------------------------------------
# Helper: play WAV + animate beak
# ---------------------------------------------------------
def play_with_beak(wav_path):
    stop_event = None
    thread = None

    try:
        print(f"Loading WAV: {wav_path}")
        audio, samplerate = sf.read(wav_path, dtype='float32')

        device_index = choose_output_device()
        if device_index is None:
            print("No audio device available. Aborting playback.")
            return

        sd.default.device = (None, device_index)

        print(f"Playing audio on device {device_index}...")

        # Try to start audio first
        sd.play(audio, samplerate, device=device_index)

        # Only start beak motion if playback started
        stop_event = threading.Event()
        thread = threading.Thread(target=beak_motion, args=(stop_event,))
        thread.start()

        sd.wait()
        sd.stop()

    except sd.PortAudioError as e:
        print(f"Startup playback failed: {e}")
        if "Device unavailable" in str(e):
            print("Device busy during startup, skipping test squawk.")
        else:
            print("Unexpected PortAudio error during startup.")
    except Exception as e:
        print("Error during play_with_beak:", e)
    finally:
        # Always stop the beak thread if it was started
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join()

        servo.detach()
        print("Playback complete.")
# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

mic_gain = 0.7 
@app.route('/volume')
def get_volume():
    """Return current volume as JSON for client bar"""
    return jsonify({'volume': int(mic_gain * 100)})  # 0-100%

@app.route('/volUp', methods=['POST'])
def volume_up():
    """Increase volume by 10%"""
    global mic_gain
    mic_gain = min(1.0, mic_gain + 0.1)
    print(f"Volume up to {mic_gain:.1%}")
    return jsonify({'volume': int(mic_gain * 100)})

@app.route('/volDown', methods=['POST'])
def volume_down():
    """Decrease volume by 10%"""
    global mic_gain
    mic_gain = max(0.0, mic_gain - 0.1)
    print(f"Volume down to {mic_gain:.1%}")
    return jsonify({'volume': int(mic_gain * 100)})

@app.route('/volume/<int:percent>', methods=['POST'])
def set_volume(percent):
    """Direct set volume 0-100"""
    global mic_gain
    mic_gain = max(0.0, min(1.0, percent / 100.0))
    print(f"Volume set to {mic_gain:.1%}")
    return jsonify({'volume': percent})
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/servo/beak/open", methods=["POST"])
def beak_open():
    servo.max()
    time.sleep(0.15)  # brief delay to ensure servo moves before detaching
    servo.detach()
    return jsonify({"status": "beak opened"})


@app.route("/servo/beak/close", methods=["POST"])
def beak_close():
    servo.min()
    time.sleep(0.15)  # brief delay to ensure servo moves before detaching
    servo.detach()
    return jsonify({"status": "beak closed"})


@app.route("/say", methods=["POST"])
def say():
    data = request.get_json()
    phrase = data.get("phrase", "").strip()
    print(f"SAY received phrase: {phrase}")

    # Map phrases → WAV files
    phrase_map = {
        "Does He Talk": "doesthebirdtalk.wav",
        "Squawk3": "squawk3.wav",
        "F#$@!": "curse.wav",
        "Hi": "hi.wav"
    }

    filename = phrase_map.get(phrase, "squawk3.wav")

    wav_path = os.path.join("app", "static", "audio", filename)

    if not os.path.exists(wav_path):
        return jsonify({"error": f"WAV file not found: {filename}"}), 404

    # Play audio + animate beak
    play_with_beak(wav_path)

    return jsonify({"status": "played", "file": filename})
def float32_to_stereo(chunk):
    arr = np.array(chunk, dtype=np.float32)
    stereo = np.column_stack((arr, arr))
    return stereo    
def float32_to_stereo_float32(chunk):
    """Convert mono float32 → stereo float32."""
    arr = np.array(chunk, dtype=np.float32)
    stereo = np.column_stack((arr, arr))  # duplicate channel
    return stereo
# -- socket handlers
@socketio.on('mic_gain')
def handle_mic_gain(value):
    global mic_gain
    try:
        mic_gain = float(value)
        print(f"Mic gain set to {mic_gain}x")
    except:
        pass
@socketio.on('mic_start')
def handle_mic_start():
    global mic_active, mic_stream, mic_buffer

    print("mic_start received")

    # Stop any leftover playback
    sd.stop()

    # Reset state
    mic_active = False
    mic_buffer = bytearray()

    # Close previous stream
    if mic_stream is not None:
        try:
            if mic_stream.active:
                mic_stream.stop()
            mic_stream.close()
        except:
            pass
        mic_stream = None

    # Pick device
    device_index = choose_output_device()
    if device_index is None:
        print("Cannot start mic: no output device.")
        return

    try:
        mic_stream = sd.OutputStream(
            samplerate=44100,
            channels=2,
            dtype='float32',   # <-- float32 end-to-end
            device=device_index,
            blocksize=0
        )
        mic_stream.start()
        mic_active = True
        print("Mic stream started.")
    except Exception as e:
        print("Failed to start mic_stream:", e)
        mic_stream = None
        mic_active = False

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active, mic_stream, mic_buffer, mic_gain

    if not mic_active or mic_stream is None or not mic_stream.active:
        print("Mic chunk received but mic is not active or stream not ready.")
        return

    try:
        # Convert raw binary → float32 mono
        arr = np.frombuffer(data, dtype=np.float32)

        # Apply gain + prevent clipping
        arr = np.clip(arr * mic_gain, -1.0, 1.0)

        # Duplicate mono → stereo float32
        stereo = np.column_stack((arr, arr)).astype(np.float32)

        # Add to jitter buffer
        mic_buffer.extend(stereo.tobytes())

        # Write in 20ms blocks
        FRAME_BYTES = 4 * 2  # float32 * 2 channels
        BLOCK_SAMPLES = 960
        BLOCK_BYTES = BLOCK_SAMPLES * FRAME_BYTES

        while len(mic_buffer) >= BLOCK_BYTES:
            block = mic_buffer[:BLOCK_BYTES]
            del mic_buffer[:BLOCK_BYTES]

            block_np = np.frombuffer(block, dtype=np.float32).reshape(-1, 2)
            mic_stream.write(block_np)

    except Exception as e:
        print("mic_chunk error:", e)
@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active, mic_stream, mic_buffer

    if not mic_active:
        print("mic_stop received but mic is not active.")
        return

    print("mic_stop received")
    print(f"Mic buffer had {len(mic_buffer)} bytes at stop time.")

    mic_active = False
    mic_buffer = bytearray()

    if mic_stream is not None:
        try:
            if mic_stream.active:
                mic_stream.stop()
            mic_stream.close()
        except:
            pass
        mic_stream = None

    servo.min()
    time.sleep(0.1)
    servo.detach()

# ---------------------------------------------------------
# MAIN ENTRY
# ---------------------------------------------------------
if __name__ == "__main__":
    # Start background test squawk
    threading.Thread(target=startup_test_squawk, daemon=True).start()

    # Start Flask
    #app.run(host="0.0.0.0", port=5000)
    socketio.run(app, host="0.0.0.0", port=5000)
