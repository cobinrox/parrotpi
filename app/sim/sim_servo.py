import logging
import time

class SimServo:
    def __init__(self, pin):
        self.pin = pin
        self.position = 0.0
        self.last_action = None
        logging.info(f"[SIM] Servo on pin {pin} initialized")

    def open(self):
        self.position = 1.0
        self.last_action = time.time()
        logging.info(f"[SIM] Servo {self.pin} -> OPEN (1.0)")

    def close(self):
        self.position = -1.0
        self.last_action = time.time()
        logging.info(f"[SIM] Servo {self.pin} -> CLOSE (-1.0)")

    def mid(self):
        self.position = 0.0
        self.last_action = time.time()
        logging.info(f"[SIM] Servo {self.pin} -> MID (0.0)")

    def set(self, value):
        self.position = value
        self.last_action = time.time()
        logging.info(f"[SIM] Servo {self.pin} -> SET {value}")

    def relax(self):
        logging.info(f"[SIM] Servo {self.pin} -> RELAX (detached)")