import os
import eventlet
eventlet.monkey_patch(thread=False)
import time
import threading
import subprocess
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
import logging
import queue
from time import perf_counter
# Recording buffer for diagnostics
mic_record_buffer = None
# Fix Socket.IO packet flood from audio streaming
from engineio.payload import Payload
Payload.max_decode_packets = 100  # Handles 40+ mic chunks/sec safely

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s - %(message)s")

mic_active = False
mic_stream = None
# Replaced bytearray jitter buffer with a thread-safe queue
mic_queue = None
mic_queued_bytes = 0
mic_queue_lock = threading.Lock()
mic_writer_thread = None
mic_writer_stop = None
last_chunk_time = None
client_sample_rate = None
mic_stream_rate = None



# 48kHz stereo output for mic playback
MIC_RATE = 48000
MIC_CHANNELS = 2
# Align block size to client ScriptProcessor buffer (1024 frames)
MIC_BLOCK = 1024
# Derived constants
FRAME_BYTES = 4 * MIC_CHANNELS
# Allow up to ~10 blocks queued before dropping
MAX_QUEUE_BYTES = MIC_BLOCK * FRAME_BYTES * 10
# Software gain multiplier applied to outgoing audio (chip has no hardware volume control)
# A value >1.0 boosts the signal (may clip), <1.0 attenuates.
# The client UI defaults to 8x, so use that as the initial value for a louder startup.
MAX_MIC_GAIN = 10.0
DEFAULT_MIC_GAIN = 8.0
VOLUME_STEPS = 5  # Number of steps /volUp and /volDown will use (coarser control)

# Pitch shift “parrot effect”: percent faster than real-time (e.g., 8% faster -> 1.08x)
PARROT_MIN_PCT = 8
PARROT_MAX_PCT = 20
parrot_pct = PARROT_MIN_PCT

mic_gain = DEFAULT_MIC_GAIN


def get_parrot_factor():
    """Return the current playback rate multiplier (1.0 = normal speed)."""
    return 1.0 + (parrot_pct / 100.0)

# Debug: when True, bypass queue and write incoming chunks immediately (for troubleshooting)
DEBUG_IMMEDIATE_WRITE = True

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
    logging.info(f"Waiting for audio device {device_index}...")

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            devices = sd.query_devices()
            if 0 <= device_index < len(devices):
                logging.info(f"Device {device_index} ready: {devices[device_index]['name']}")
                return True
        except Exception as e:
            logging.info(f"Error querying devices: {e}")

        logging.info("Device not ready, retrying...")
        time.sleep(interval)

    logging.info(f"Timed out waiting for device {device_index}")
    return False


def choose_output_device():
    devices = sd.query_devices()

    if not devices:
        logging.info("No audio devices found at all.")
        return None

    # Prefer I2S DAC by name
    for idx, dev in enumerate(devices):
        name = dev["name"].lower()
        if (
            "snd_rpi_hifiberry" in name or
            "max98357" in name or
            "i2s" in name
        ) and dev["max_output_channels"] >= 2:
            logging.info(f"Using I2S device {idx}: {dev['name']}")
            return idx

    # Fallback: any stereo output
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] >= 2:
            logging.info(f"Using fallback device {idx}: {dev['name']}")
            return idx

    logging.info("No usable audio output devices found.")
    return None
def startup_test_squawk():
    """
    Plays squawk3.wav once at server startup to verify audio device health.
    Runs in a background thread so it doesn't block Flask.
    """
    time.sleep(6)  # allow systemd + I2S to settle

    test_path = os.path.join("app", "static", "audio", "squawk3.wav")

    logging.info("\n=== STARTUP AUDIO TEST ===")
    # Ensure device is available (give it some time after boot)
    for attempt in range(1, 21):
        device_index = choose_output_device()
        if device_index is not None:
            break
        logging.info(f"Startup audio test: no device yet (attempt {attempt}/20), waiting...")
        time.sleep(1.0)

    if device_index is None:
        logging.info("No audio output device found after retrying; skipping startup test.")
        logging.info("=== END STARTUP TEST ===\n")
        return

    logging.info(f"Testing audio playback with: {test_path}")
    try:
        play_with_beak(test_path)
        logging.info("Startup audio test completed.")
    except Exception as e:
        logging.info(f"Startup audio test FAILED: {e}")
    logging.info("=== END STARTUP TEST ===\n")

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

    def _log_lsof_snd_usage():
        """Log which processes (if any) are holding /dev/snd/*."""
        try:
            res = subprocess.run(["lsof", "/dev/snd/*"], capture_output=True, text=True)
            out = (res.stdout or res.stderr or "").strip()
            if out:
                logging.info(f"lsof /dev/snd/* output:\n{out}")
                return True
            logging.info("lsof: no processes are using /dev/snd/*")
            return False
        except Exception as e:
            logging.info(f"Failed to run lsof /dev/snd/*: {e}")
            return True

    def _parrot_factor():
        return 1.0 + (parrot_pct / 100.0)

    try:
        logging.info(f"Loading WAV: {wav_path}")
        audio, samplerate = sf.read(wav_path, dtype='float32')

        device_index = choose_output_device()
        if device_index is None:
            logging.info("No audio device available. Aborting playback.")
            return

        sd.default.device = (None, device_index)

        # Apply software volume control (chip has no hardware volume control)
        if mic_gain != 1.0:
            audio = np.clip(audio * mic_gain, -1.0, 1.0)

        # Apply parrot pitch shift by resampling audio (keeps output sample rate valid)
        if parrot_pct != 0:
            factor = _parrot_factor()
            target_len = int(round(len(audio) / factor))
            if target_len > 1 and len(audio) > 1:
                orig_x = np.arange(len(audio))
                target_x = np.linspace(0, len(audio) - 1, target_len)
                if audio.ndim == 1:
                    audio = np.interp(target_x, orig_x, audio).astype(np.float32)
                else:
                    # Resample per channel
                    channels = [
                        np.interp(target_x, orig_x, audio[:, c])
                        for c in range(audio.shape[1])
                    ]
                    audio = np.vstack(channels).T.astype(np.float32)

        # Try playback, and if the device is unavailable, verify with lsof before retrying.
        for attempt in range(1, 3):
            try:
                logging.info(f"Playing audio on device {device_index} (parrot {parrot_pct}% -> {get_parrot_factor():.3f}x) ... (attempt {attempt}/2)")

                sd.play(audio, samplerate, device=device_index)

                # Only start beak motion if playback started
                stop_event = threading.Event()
                thread = threading.Thread(target=beak_motion, args=(stop_event,))
                thread.start()

                sd.wait()
                sd.stop()
                break

            except sd.PortAudioError as e:
                logging.info(f"Startup playback failed: {e}")
                if "Device unavailable" in str(e):
                    busy = _log_lsof_snd_usage()
                    if not busy and attempt < 2:
                        logging.info("No one is using /dev/snd; retrying playback...")
                        time.sleep(0.25)
                        continue
                    logging.info("Device unavailable during startup, skipping test squawk.")
                else:
                    logging.info("Unexpected PortAudio error during startup.")
                break

    except Exception as e:
        logging.info(f"Error during play_with_beak: {e}")
    finally:
        # Always stop the beak thread if it was started
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join()

        servo.detach()
        logging.info("Playback complete.")
# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.route('/volume')
def get_volume():
    """Return current volume as JSON for client bar"""
    # Map our gain range [0..MAX_MIC_GAIN] to 0..100% for the UI
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})  # 0-100%

@app.route('/volUp', methods=['POST'])
def volume_up():
    """Increase volume one step (coarser steps than 10%)."""
    global mic_gain
    step = MAX_MIC_GAIN / VOLUME_STEPS
    mic_gain = min(MAX_MIC_GAIN, mic_gain + step)
    logging.info(f"Volume up to {mic_gain / MAX_MIC_GAIN:.1%} ({mic_gain:.2f}x)")
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})

@app.route('/volDown', methods=['POST'])
def volume_down():
    """Decrease volume one step (coarser steps than 10%)."""
    global mic_gain
    step = MAX_MIC_GAIN / VOLUME_STEPS
    mic_gain = max(0.0, mic_gain - step)
    logging.info(f"Volume down to {mic_gain / MAX_MIC_GAIN:.1%} ({mic_gain:.2f}x)")
    return jsonify({'volume': int(mic_gain / MAX_MIC_GAIN * 100)})

@app.route('/volume/<int:percent>', methods=['POST'])
def set_volume(percent):
    """Direct set volume 0-100"""
    global mic_gain
    mic_gain = max(0.0, min(MAX_MIC_GAIN, (percent / 100.0) * MAX_MIC_GAIN))
    logging.info(f"Volume set to {mic_gain / MAX_MIC_GAIN:.1%} ({mic_gain:.2f}x)")
    return jsonify({'volume': percent})

@app.route('/parrot')
def get_parrot():
    """Return current parrot pitch percent"""
    return jsonify({'parrot': parrot_pct})

@app.route('/parrot/<int:percent>', methods=['POST'])
def set_parrot(percent):
    """Set parrot pitch percent (8-20)"""
    global parrot_pct
    parrot_pct = max(PARROT_MIN_PCT, min(PARROT_MAX_PCT, percent))
    logging.info(f"Parrot pitch set to {parrot_pct}% (factor {get_parrot_factor():.3f}x)")
    return jsonify({'parrot': parrot_pct})

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
    logging.info(f"SAY received phrase: {phrase}")

    # Map phrases → WAV files
    phrase_map = {
        "Does He Talk": "doesthebirdtalk.wav",
        "Squawk3": "squawk3.wav",
        "F#$@!": "curse.wav",
        "Hi": "hi.wav",
        "test": "test.wav"
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
        mic_gain = max(0.0, min(MAX_MIC_GAIN, mic_gain))
        logging.info(f"Mic gain set to {mic_gain:.2f}x ({mic_gain / MAX_MIC_GAIN:.1%})")
    except Exception as e:
        logging.info(f"Invalid mic_gain value: {value} ({e})")
@socketio.on('mic_start')
def handle_mic_start(data=None):
    global mic_active, mic_stream, mic_buffer

    logging.info("mic_start received")

    # Log client sample rate if provided
    global client_sample_rate
    try:
        if data and isinstance(data, dict) and 'sampleRate' in data:
            client_sample_rate = float(data.get('sampleRate'))
            logging.info(f"Client sampleRate: {client_sample_rate}")
        else:
            client_sample_rate = None
    except Exception as e:
        logging.info(f"Error parsing client sampleRate: {e}")

    # Stop any leftover playback
    sd.stop()

    # Reset state
    mic_active = False
    # initialize the queue and bookkeeping
    global mic_queue, mic_queued_bytes, mic_writer_thread, mic_writer_stop, last_chunk_time
    mic_queue = queue.Queue()
    with mic_queue_lock:
        mic_queued_bytes = 0
    mic_writer_stop = threading.Event()
    last_chunk_time = None
    # start fresh record buffer
    global mic_record_buffer
    mic_record_buffer = []

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
        logging.info("Cannot start mic: no output device.")
        return

    try:
        # Use the device default samplerate (may be 44100) to avoid driver resampling artifacts.
        device_info = sd.query_devices(device_index)
        stream_rate = int(device_info.get('default_samplerate', MIC_RATE))
        mic_stream = sd.OutputStream(
            samplerate=stream_rate,
            channels=MIC_CHANNELS,
            dtype='float32',   # <-- float32 end-to-end
            device=device_index,
            blocksize=MIC_BLOCK
        )
        mic_stream.start()

        # remember base stream rate (for resampling client audio if needed)
        global mic_stream_rate
        mic_stream_rate = stream_rate

        logging.info(f"Stream samplerate={mic_stream.samplerate} (base {stream_rate}), latency={mic_stream.latency}")
        logging.info(f"Device info: {device_info}")

        # Start writer thread that consumes mic_queue and writes aligned blocks
        def mic_writer(stop_event):
            global mic_queued_bytes
            local_buf = bytearray()
            FRAME_BYTES = 4 * MIC_CHANNELS
            BLOCK_BYTES = MIC_BLOCK * FRAME_BYTES
            while not stop_event.is_set() or not mic_queue.empty():
                try:
                    chunk = mic_queue.get(timeout=0.1)
                except queue.Empty:
                    # if no data, loop again and allow stop_event checks
                    continue

                # chunk is raw bytes
                local_buf.extend(chunk)
                with mic_queue_lock:
                    mic_queued_bytes -= len(chunk)

                # write full blocks
                while len(local_buf) >= BLOCK_BYTES:
                    block = local_buf[:BLOCK_BYTES]
                    del local_buf[:BLOCK_BYTES]
                    try:
                        block_np = np.frombuffer(block, dtype=np.float32).reshape(-1, MIC_CHANNELS)

                        # Apply software volume control (chip has no hardware volume control)
                        if mic_gain != 1.0:
                            block_np = np.clip(block_np * mic_gain, -1.0, 1.0)

                        t0 = perf_counter()
                        mic_stream.write(block_np)
                        t1 = perf_counter()
                        took = t1 - t0
                        if took > (MIC_BLOCK / MIC_RATE) * 2:
                            logging.info(f"mic_writer write slow: {took:.4f}s (block {BLOCK_BYTES} bytes)")
                    except Exception as e:
                        logging.info(f"mic_writer write error: {e}")

            # flush any remaining partial data (pad with zeros)
            if len(local_buf) > 0:
                # pad to full block
                pad_needed = BLOCK_BYTES - len(local_buf)
                if pad_needed > 0:
                    local_buf.extend(b"\x00" * pad_needed)
                try:
                    block_np = np.frombuffer(local_buf, dtype=np.float32).reshape(-1, MIC_CHANNELS)
                    mic_stream.write(block_np)
                except Exception as e:
                    logging.info(f"mic_writer final write error: {e}")

        mic_writer_thread = threading.Thread(target=mic_writer, args=(mic_writer_stop,), daemon=True)
        mic_writer_thread.start()

        mic_active = True
        logging.info("Mic stream started and writer thread running.")
    except Exception as e:
        logging.info(f"Failed to start mic_stream: {e}")
        mic_stream = None
        mic_active = False

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    global mic_active, mic_stream, mic_buffer, mic_gain, mic_queue, mic_queued_bytes, last_chunk_time

    if not mic_active or mic_stream is None or not mic_stream.active:
        logging.info("Mic chunk received but mic is not active or stream not ready.")
        return

    try:
        # arrival timing diagnostics
        now = perf_counter()
        if last_chunk_time is None:
            delta = 0.0
        else:
            delta = now - last_chunk_time
        last_chunk_time = now

        # Convert raw binary → float32 mono (explicit little-endian)
        try:
            arr = np.frombuffer(data, dtype='<f4')
        except Exception:
            arr = np.frombuffer(data, dtype=np.float32)

        # Ensure native dtype and contiguous
        arr = arr.astype(np.float32, copy=False)

        # Quick stats for diagnostics
        try:
            a0 = float(arr[0]) if arr.size > 0 else 0.0
            a_mean = float(np.mean(arr[:min(len(arr), 64)]))
            a_min = float(np.min(arr[:min(len(arr), 64)]))
            a_max = float(np.max(arr[:min(len(arr), 64)]))
            logging.info(f"mic_chunk stats: first={a0:.4f}, mean64={a_mean:.4f}, min64={a_min:.4f}, max64={a_max:.4f}")
        except Exception:
            pass

        # If client and stream sample rates differ, resample (simple linear interpolation)
        if client_sample_rate and mic_stream_rate and client_sample_rate != mic_stream_rate:
            target_len = int(round(len(arr) * (mic_stream_rate / client_sample_rate)))
            if target_len != len(arr) and len(arr) > 1:
                orig_x = np.arange(len(arr))
                target_x = np.linspace(0, len(arr) - 1, target_len)
                arr = np.interp(target_x, orig_x, arr).astype(np.float32)

        # Apply parrot pitch (speed up) by resampling. This makes live mic sound higher.
        if parrot_pct != 0:
            factor = get_parrot_factor()
            target_len = int(round(len(arr) / factor))
            if target_len > 1 and len(arr) > 1:
                orig_x = np.arange(len(arr))
                target_x = np.linspace(0, len(arr) - 1, target_len)
                arr = np.interp(target_x, orig_x, arr).astype(np.float32)

        # Apply gain + prevent clipping
        arr = np.clip(arr * mic_gain, -1.0, 1.0)

        # Duplicate mono → stereo float32
        stereo = np.column_stack((arr, arr)).astype(np.float32)

        chunk_bytes = stereo.tobytes()

        # Immediate debug write path
        if DEBUG_IMMEDIATE_WRITE and mic_stream is not None and mic_stream.active:
            try:
                total_frames = stereo.shape[0]
                written_frames = 0
                BLOCK = MIC_BLOCK
                while written_frames < total_frames:
                    end = min(written_frames + BLOCK, total_frames)
                    slice_np = stereo[written_frames:end]
                    # pad last block if needed
                    if slice_np.shape[0] < BLOCK:
                        pad = np.zeros((BLOCK - slice_np.shape[0], MIC_CHANNELS), dtype=np.float32)
                        slice_np = np.vstack((slice_np, pad))

                    t0 = perf_counter()
                    mic_stream.write(slice_np)
                    t1 = perf_counter()
                    took = t1 - t0
                    if took > (MIC_BLOCK / MIC_RATE) * 2:
                        logging.info(f"DEBUG write slow: {took:.4f}s for {slice_np.shape[0]} frames")
                    written_frames = end
                logging.info(f"DEBUG immediate write: wrote {total_frames} frames")
            except Exception as e:
                logging.info(f"DEBUG immediate write error: {e}")
        else:
            # enqueue for writer thread (with queue cap)
            if mic_queue is not None:
                with mic_queue_lock:
                    projected = mic_queued_bytes + len(chunk_bytes)
                if projected > MAX_QUEUE_BYTES:
                    logging.info(f"Dropping mic_chunk: queue full ({mic_queued_bytes} bytes) > {MAX_QUEUE_BYTES}")
                else:
                    mic_queue.put(chunk_bytes)
                    with mic_queue_lock:
                        mic_queued_bytes += len(chunk_bytes)

        # append to record buffer for post-test inspection
        try:
            if mic_record_buffer is not None:
                mic_record_buffer.append(chunk_bytes)
        except Exception:
            pass
        # log diagnostics
        logging.info(f"mic_chunk received: {len(data)} bytes, stereo {len(chunk_bytes)} bytes, delta {delta:.3f}s, queued {mic_queued_bytes} bytes, debug_immediate={DEBUG_IMMEDIATE_WRITE}")

    except Exception as e:
        logging.info(f"mic_chunk error: {e}")
@socketio.on('mic_stop')
def handle_mic_stop():
    global mic_active, mic_stream, mic_buffer, mic_record_buffer

    if not mic_active:
        logging.info("mic_stop received but mic is not active.")
        return

    logging.info("mic_stop received")
    # report queued bytes
    global mic_queue, mic_queued_bytes, mic_writer_stop, mic_writer_thread
    with mic_queue_lock:
        queued = mic_queued_bytes
    logging.info(f"Mic queued bytes at stop time: {queued}")

    mic_active = False

    # signal writer to stop and join
    if mic_writer_stop is not None:
        mic_writer_stop.set()
    if mic_writer_thread is not None:
        mic_writer_thread.join(timeout=1.0)

    # clear queue
    mic_queue = None
    with mic_queue_lock:
        mic_queued_bytes = 0

    # write recorded received audio to a WAV for offline inspection
    try:
        if mic_record_buffer:
            audio_dir = os.path.join(app.static_folder, "audio")
            os.makedirs(audio_dir, exist_ok=True)
            out_path = os.path.join(audio_dir, "test.wav")
            logging.info(f"Writing recorded mic to {out_path}")
            all_bytes = b"".join(mic_record_buffer)
            arr = np.frombuffer(all_bytes, dtype=np.float32).reshape(-1, MIC_CHANNELS)

            # Apply parrot pitch to the saved recording as well
            if parrot_pct != 0:
                factor = get_parrot_factor()
                target_len = int(round(len(arr) / factor))
                if target_len > 1 and len(arr) > 1:
                    orig_x = np.arange(len(arr))
                    target_x = np.linspace(0, len(arr) - 1, target_len)
                    if arr.ndim == 1:
                        arr = np.interp(target_x, orig_x, arr).astype(np.float32)
                    else:
                        channels = [
                            np.interp(target_x, orig_x, arr[:, c])
                            for c in range(arr.shape[1])
                        ]
                        arr = np.vstack(channels).T.astype(np.float32)

            # choose rate reported by client if available
            rate = int(client_sample_rate) if client_sample_rate else MIC_RATE
            sf.write(out_path, arr, rate, format='WAV', subtype='FLOAT')
    except Exception as e:
        logging.info(f"Failed to write mic_record.wav: {e}")
    finally:
        mic_record_buffer = None
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
