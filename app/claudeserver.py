"""
ParrotPi - server.py
Relevant section: mic streaming via SocketIO -> real-time playback on Pi

Dependencies:
    pip install flask flask-socketio pyaudio numpy

On the Pi, make sure ALSA / the audio output is configured correctly.
If you're using a USB speaker or HDMI, set the default output device accordingly.
"""

from flask import Flask
from flask_socketio import SocketIO
import pyaudio
import threading
import numpy as np

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Audio config ──────────────────────────────────────────────────────────────
# These MUST match whatever the browser is capturing on the client side.
# The Web Audio API typically sends 32-bit floats; adjust if you convert
# to PCM int16 on the client before sending (see client note below).
SAMPLE_RATE   = 16000   # Hz  – match your client resample rate
CHANNELS      = 1       # mono
CHUNK_SIZE    = 1024    # frames per PyAudio write (tune if you hear glitches)
FORMAT        = pyaudio.paFloat32   # change to paInt16 if client sends int16

# ── PyAudio stream (opened once, kept alive during a mic session) ─────────────
_pa           = pyaudio.PyAudio()
_out_stream   = None
_stream_lock  = threading.Lock()


def _open_output_stream():
    return _pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        output=True,
        frames_per_buffer=CHUNK_SIZE,
    )


# ── SocketIO event handlers ───────────────────────────────────────────────────

@socketio.on("mic_start")
def handle_mic_start(data=None):
    """Client pressed the talk button – open the output stream."""
    global _out_stream
    with _stream_lock:
        if _out_stream is None or not _out_stream.is_active():
            _out_stream = _open_output_stream()
    print("[parrotpi] mic_start: output stream opened")


@socketio.on("mic_chunk")
def handle_mic_chunk(data):
    """
    Fired ~every 100 ms by the client with raw PCM audio.

    Expected payload (dict):
        {
          "audio": <list of floats>  OR  <bytes of int16 PCM>
        }

    If the client sends a JSON array of floats (easiest from Web Audio API),
    we convert to a numpy float32 array then write to PyAudio.
    """
    global _out_stream

    if _out_stream is None:
        # Safety net: stream wasn't opened yet
        with _stream_lock:
            _out_stream = _open_output_stream()

    raw = data.get("audio")
    if raw is None:
        return

    try:
        # ── Case 1: JSON array of floats from the browser ─────────────────
        if isinstance(raw, (list, tuple)):
            samples = np.array(raw, dtype=np.float32)

        # ── Case 2: binary blob (bytes) – treat as int16 PCM ─────────────
        elif isinstance(raw, (bytes, bytearray)):
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        else:
            print(f"[parrotpi] mic_chunk: unexpected data type {type(raw)}")
            return

        # Optional: simple volume boost (parrot effect – make it louder)
        samples = np.clip(samples * 1.5, -1.0, 1.0)

        with _stream_lock:
            if _out_stream and _out_stream.is_active():
                _out_stream.write(samples.tobytes(), exception_on_underflow=False)

    except Exception as e:
        print(f"[parrotpi] mic_chunk error: {e}")


@socketio.on("mic_stop")
def handle_mic_stop(data=None):
    """Client released the talk button – close the output stream cleanly."""
    global _out_stream
    with _stream_lock:
        if _out_stream is not None:
            try:
                _out_stream.stop_stream()
                _out_stream.close()
            except Exception as e:
                print(f"[parrotpi] mic_stop close error: {e}")
            finally:
                _out_stream = None
    print("[parrotpi] mic_stop: output stream closed")


@socketio.on("disconnect")
def handle_disconnect():
    """Clean up if the client disconnects mid-stream."""
    handle_mic_stop()


# ── Existing routes / servo / wav playback would live here ───────────────────
# @app.route("/move/<direction>") ...
# @app.route("/play/<clip>") ...

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)