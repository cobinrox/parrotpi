from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flasgger import Swagger

from .controller import Servo
from .config import SERVO_PINS

import logging

# ---------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.info("Starting server.py")

# ---------------------------------------------------------
# Flask Setup
# ---------------------------------------------------------
app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

# ---------------------------------------------------------
# Servo Initialization
# ---------------------------------------------------------
def create_servo(name, pin):
    logging.info(f"Initializing servo '{name}' on GPIO pin {pin}")
    return Servo(pin)

servos = {
    name: create_servo(name, pin)
    for name, pin in SERVO_PINS.items()
}



# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    """
    Heartbeat check
    ---
    responses:
      200:
        description: OK
    """
    return jsonify({"status": "ok"})


# -----------------------------
# Basic open/close
# -----------------------------
@app.route("/servo/<name>/open", methods=["POST"])
def servo_open(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    # Read optional phrase from JSON body (may be empty or null)
    data = request.get_json(silent=True) or {}
    phrase = data.get("phrase")

    if phrase:
        logging.info(f"Route: /servo/{name}/open -> phrase: {phrase}")
    else:
        logging.info(f"Route: /servo/{name}/open -> no phrase provided")

    servos[name].open()
    return jsonify({"servo": name, "action": "open", "phrase": phrase})


@app.route("/servo/<name>/close", methods=["POST"])
def servo_close(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/close")
    servos[name].close()
    return jsonify({"servo": name, "action": "close"})


# -----------------------------
# New: mid/neutral
# -----------------------------
@app.route("/servo/<name>/mid", methods=["POST"])
def servo_mid(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/mid")
    servos[name].mid()
    return jsonify({"servo": name, "action": "mid"})


# -----------------------------
# New: set(value)
# -----------------------------
@app.route("/servo/<name>/set", methods=["POST"])
def servo_set(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    data = request.get_json(silent=True) or {}
    value = data.get("value")

    if value is None:
        return jsonify({"error": "Missing 'value' in JSON body"}), 400

    try:
        value = float(value)
    except ValueError:
        return jsonify({"error": "'value' must be a float"}), 400

    if not -1.0 <= value <= 1.0:
        return jsonify({"error": "'value' must be between -1.0 and 1.0"}), 400

    logging.info(f"Route: /servo/{name}/set -> {value}")
    servos[name].set(value)
    return jsonify({"servo": name, "action": "set", "value": value})


# -----------------------------
# New: relax()
# -----------------------------
@app.route("/servo/<name>/relax", methods=["POST"])
def servo_relax(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    logging.info(f"Route: /servo/{name}/relax")
    servos[name].relax()
    return jsonify({"servo": name, "action": "relax"})


# ---------------------------------------------------------
# Start Function
# ---------------------------------------------------------
def start():
    logging.info("Starting Flask server...")
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    logging.info("Running server.py directly")
    start()