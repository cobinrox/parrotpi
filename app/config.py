# ------------------------------------------------------------
# GLOBAL CONFIGURATION FOR PARROT PROJECT
# ------------------------------------------------------------

# Toggle between real hardware and simulation mode
# True  = use simulated hardware (safe on PC or when testing)
# False = use real GPIO hardware on Raspberry Pi
SIMULATION_MODE = False

# GPIO pin assignments for servos
# These names must match the names you use in server.py routes
SERVO_PINS = {
    "beak": 17,
    "head": 18,
    # Add more servos here later (wings, eyelids, etc.)
}

# Optional: servo tuning parameters
# These can be used by both real and simulated drivers
SERVO_SETTINGS = {
    "beak": {
        "open_angle": 1.0,     # max position
        "close_angle": -1.0,   # min position
    },
    "head": {
        "left_angle": -1.0,
        "right_angle": 1.0,
        "center_angle": 0.0,
    }
}

import os

# Future expansion:
# AUDIO_DEVICE = "default"
# CAMERA_ENABLED = False
# LED_PINS = { "eye_left": 22, "eye_right": 23 }

# Directory where .wav audio files live. Default is app/static/audio next to this file.
# Use an absolute path here for system-wide locations (e.g. /var/lib/parrotpi/audio)
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "static", "audio")