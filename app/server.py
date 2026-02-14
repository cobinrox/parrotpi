from flask import Flask, jsonify, request
from .controller import Servo
from .config import SERVO_PINS

app = Flask(__name__)

# Create servo objects (real or simulated depending on config)
servos = {
    name: Servo(pin)
    for name, pin in SERVO_PINS.items()
}

# POST /servo/beak/open
# POST /servo/beak/close
# POST /servo/head/open
# POST /servo/head/close


@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})

@app.route("/servo/<name>/open", methods=["POST"])
def servo_open(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    servos[name].open()
    return jsonify({"servo": name, "action": "open"})

@app.route("/servo/<name>/close", methods=["POST"])
def servo_close(name):
    if name not in servos:
        return jsonify({"error": f"Unknown servo '{name}'"}), 404

    servos[name].close()
    return jsonify({"servo": name, "action": "close"})

def start():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    start()    