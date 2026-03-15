from flask import Flask, render_template_string, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import RPi.GPIO as GPIO
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import time
import os
import queue
import sys
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'parrotpi-secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# GPIO Setup
SERVO_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

# Audio Setup
AUDIO_DEVICE = 0  # HifiBerry DAC (hw:0,0)
SAMPLE_RATE = 44100
VOLUME = 0.7
PARROT_SPEED = 1.0

audio_queue = queue.Queue()
audio_stream = None
mic_active = False
beak_moving = False

# Beak positions (duty cycle for servo)
BEAK_POSITIONS = {
    'closed': 2.5,    # 0 degrees
    'mid': 7.5,       # 90 degrees  
    'open': 12.5      # 180 degrees
}

# Audio files in static/audio/
AUDIO_DIR = Path('static/audio')
PHRASES = {
    'Hi': 'hi.wav',
    'Does He Talk': 'does_he_talk.wav',
    'F#$@!!': 'f_wow.wav',
    'Squawk3': 'squawk3.wav',
    'test': 'test.wav'
}

def servo_set_position(position):
    """Move servo to specific position"""
    duty = BEAK_POSITIONS.get(position, 7.5)
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.15)
    servo_pwm.ChangeDutyCycle(0)

def animate_beak():
    """Animate beak open/close during audio playback"""
    global beak_moving
    beak_moving = True
    try:
        while audio_stream and audio_stream.active:
            servo_set_position('open')
            time.sleep(0.1)
            servo_set_position('closed')
            time.sleep(0.1)
    except:
        pass
    finally:
        servo_set_position('closed')
        beak_moving = False

def audio_callback(outdata, frames, time_info, status):
    """Persistent audio callback - handles both WAV and mic"""
    global audio_queue
    
    if status:
        print(f"Audio status: {status}")
    
    # Get audio data from queue (non-blocking)
    try:
        data = audio_queue.get_nowait()
        # Apply volume and parrot speed
        data = data * VOLUME * PARROT_SPEED
        outdata[:] = data[:frames]
        audio_queue.task_done()
    except queue.Empty:
        outdata.fill(0)

def init_audio():
    """Initialize persistent audio stream"""
    global audio_stream
    
    try:
        # Test device first
        devices = sd.query_devices()
        print("Available devices:", devices)
        
        # Use HifiBerry DAC specifically
        sd.default.device = AUDIO_DEVICE
        
        # Start persistent stream
        audio_stream = sd.OutputStream(
            device=AUDIO_DEVICE,
            channels=2,
            samplerate=SAMPLE_RATE,
            callback=audio_callback,
            blocksize=1024
        )
        audio_stream.start()
        print("Audio stream started successfully")
        return True
    except Exception as e:
        print(f"Audio init failed: {e}")
        return False

def play_wav(filename, speed=1.0):
    """Play WAV file with parrot speed effect"""
    global audio_queue, PARROT_SPEED
    
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        print(f"WAV file not found: {filepath}")
        return
    
    try:
        # Load WAV
        data, fs = sf.read(str(filepath))
        
        # Resample for parrot speed effect
        if speed != 1.0:
            # Faster parrot = higher pitch (resample)
            target_length = int(len(data) / abs(speed))
            time_axis = np.linspace(0, len(data)/fs, target_length)
            orig_time = np.linspace(0, 1, len(data))
            data = np.interp(time_axis, orig_time, data)
        
        # Convert to stereo float32
        if len(data.shape) == 1:
            data = np.stack([data, data], axis=1)
        data = data.astype(np.float32)
        
        # Queue audio chunks
        chunk_size = 1024
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, ((0, chunk_size-len(chunk)), (0,0)))
            audio_queue.put(chunk)
        
        # Start beak animation if not already moving
        if not beak_moving:
            threading.Thread(target=animate_beak, daemon=True).start()
            
    except Exception as e:
        print(f"Play WAV error: {e}")

@socketio.on('mic_start')
def handle_mic_start(data):
    """Switch to mic input"""
    global mic_active
    print("mic_start received")
    mic_active = True
    emit('server_pcm', [], namespace='/')  # Keep stream alive

@socketio.on('mic_chunk')
def handle_mic_chunk(data):
    """Process mic audio chunk"""
    if mic_active:
        # Convert ArrayBuffer to numpy
        audio_data = np.frombuffer(data, dtype=np.float32)
        # Stereo
        if len(audio_data.shape) == 1:
            audio_data = np.stack([audio_data, audio_data], axis=1)
        audio_queue.put(audio_data)

@socketio.on('mic_stop')
def handle_mic_stop():
    """Switch away from mic"""
    global mic_active
    print("mic_stop received")
    mic_active = False

@app.route('/')
def index():
    """Serve main page"""
    with open('templates/index.html', 'r') as f:
        html = f.read()
    return render_template_string(html)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/say', methods=['POST'])
def say():
    """Play phrase"""
    data = request.json
    phrase = data.get('phrase', 'Squawk3')
    filename = PHRASES.get(phrase, 'squawk3.wav')
    print(f"Playing phrase: {phrase} -> {filename}")
    
    # Play with current parrot speed
    play_wav(filename, PARROT_SPEED)
    return jsonify({'status': 'playing', 'phrase': phrase})

@app.route('/servo/beak/<action>', methods=['POST'])
def servo_beak(action):
    """Control beak servo"""
    if action in BEAK_POSITIONS:
        servo_set_position(action)
        return jsonify({'status': 'ok', 'position': action})
    return jsonify({'error': 'invalid position'}), 400

@app.route('/servo/head/<action>', methods=['POST'])
def servo_head(action):
    """Head servo (not implemented - placeholder)"""
    return jsonify({'status': 'ok', 'action': f'head_{action}'})

@app.route('/volUp', methods=['POST'])
def vol_up():
    global VOLUME
    VOLUME = min(1.0, VOLUME + 0.1)
    return jsonify({'volume': int(VOLUME * 100)})

@app.route('/volDown', methods=['POST'])
def vol_down():
    global VOLUME
    VOLUME = max(0.0, VOLUME - 0.1)
    return jsonify({'volume': int(VOLUME * 100)})

@app.route('/volume')
def get_volume():
    return jsonify({'volume': int(VOLUME * 100)})

@app.route('/parrot')
def get_parrot():
    return jsonify({'parrot': int((PARROT_SPEED - 1) * 100)})

@app.route('/parrot/<int:pct>', methods=['POST'])
def set_parrot(pct):
    """Set parrot speed effect (8-20% faster -> 1.08-1.20x speed)"""
    global PARROT_SPEED
    PARROT_SPEED = 1.0 + (pct / 100.0)
    PARROT_SPEED = max(0.8, min(2.0, PARROT_SPEED))  # Clamp 0.8x-2.0x
    return jsonify({'parrot': int((PARROT_SPEED - 1) * 100)})

def startup_test():
    """Test audio + servo on startup"""
    print("Running startup test...")
    time.sleep(1)
    play_wav('squawk3.wav')
    time.sleep(3)

if __name__ == '__main__':
    # Create directories
    os.makedirs(AUDIO_DIR, exist_ok=True)
    
    # Initialize audio
    if not init_audio():
        print("CRITICAL: Audio initialization failed!")
        sys.exit(1)
    
    # Startup test
    threading.Thread(target=startup_test, daemon=True).start()
    
    print("ParrotPi server starting on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
