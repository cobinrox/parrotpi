import time
import threading
import sounddevice as sd
import soundfile as sf
from gpiozero import Servo

# ---------------------------------------------------------
# Try to use I2S device 0, fallback to headphones
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


# ---------------------------------------------------------
# Servo setup
# ---------------------------------------------------------
servo = Servo(17)
print("Servo initialized on GPIO17")

# ---------------------------------------------------------
# Load WAV file
# ---------------------------------------------------------
wav_path = "/home/u/projects/parrotpi/app/static/audio/squawk3.wav"
audio, samplerate = sf.read(wav_path, dtype='float32')

print("Loaded WAV:", wav_path)
print("Sample rate:", samplerate)
print("Shape:", audio.shape)

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


# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------

# Pick the best available audio device
device_index = choose_output_device()
if device_index is None:
    print("No audio device available. Exiting.")
    exit(1)

# Start beak animation
stop_event = threading.Event()
thread = threading.Thread(target=beak_motion, args=(stop_event,))
thread.start()

# Play audio using the chosen device
print(f"Playing audio on device {device_index}...")
sd.play(audio, samplerate, device=device_index)
sd.wait()

# Stop beak animation
stop_event.set()
thread.join()

print("Done.")