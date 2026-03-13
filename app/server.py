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
mic_buffer = []

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
    """
    Attempts to use device 0 (I2S). If unavailable, falls back to the
    first device that supports output (usually headphones).
    Returns the chosen device index.
    """
    # Try I2S device 0 first
    if wait_for_device(0):
        print("Using I2S device 0")
        return 0

    print("Falling back to headphone/other output device...")

    # Search for any device with max_output_channels > 0
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] > 0:
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
    print(f"Testing audio playback with: {test_path}")

    try:
        sd._terminate()
        sd._initialize()
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
    print(f"Loading WAV: {wav_path}")

    audio, samplerate = sf.read(wav_path, dtype='float32')

    # Reinitialize PortAudio inside this thread
    sd._terminate()
    sd._initialize()

    # Pick the best available audio device
    device_index = choose_output_device()
    if device_index is None:
        print("No audio device available. Aborting playback.")
        return

    # Force device selection for this thread
    sd.default.device = (None, device_index)

    # Start beak animation
    stop_event = threading.Event()
    thread = threading.Thread(target=beak_motion, args=(stop_event,))
    thread.start()

    # Play audio
    print(f"Playing audio on device {device_index}...")
    sd.play(audio, samplerate, device=device_index)
    sd.wait()

    # Stop beak animation
    stop_event.set()
    thread.join()

    # Detach servo to prevent jitter
    servo.detach()

    print("Playback complete.")
# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
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
    mic_active = True
    mic_buffer = []

    # Reinitialize PortAudio for this thread
    sd._terminate()
    sd._initialize()

    # Pick correct device (I2S or fallback)
    device_index = choose_output_device()
    sd.default.device = (None, device_index)

    # Open a continuous output stream
    mic_stream = sd.OutputStream(
        samplerate=48000, #MIC_RATE,
        channels=2, #MIC_CHANNELS,
        dtype='float32',
        device=device_index,
        blocksize=1024 #MIC_BLOCK
    )
    mic_stream.start()

    # Start beak animation
    servo.max()
    time.sleep(0.1)


@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active, mic_stream

    if not mic_active or mic_stream is None:
        return

    try:
        # Convert raw binary → float32 mono
        arr = np.frombuffer(data, dtype=np.float32)

        # Apply gain
        arr = arr * mic_gain

        # Prevent clipping
        arr = np.clip(arr, -1.0, 1.0)

        # Convert mono → stereo
        stereo = np.column_stack((arr, arr))

        # Drop partial blocks
        if stereo.shape[0] != 1024:
            return

        mic_stream.write(stereo)

    except Exception as e:
        print("mic_chunk error:", e)
@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active, mic_stream

    print("mic_stop received")
    mic_active = False

    try:
        if mic_stream:
            mic_stream.stop()
            mic_stream.close()
    except:
        pass

    mic_stream = None

    # Close beak and detach
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
