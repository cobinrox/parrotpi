import logging
import time

class SimServo:
    def __init__(self, pin):
        self.pin = pin
        self.position = 0.0
        self.last_action = None
        logging.info(f"[SIM] Servo on pin {pin} initialized")

        # Simulated detach behavior
        self._detach_after_move = True
        self._detach_delay = 0.01

    def _perform(self, fn, detach: bool | None = None):
        try:
            fn()
        except Exception:
            logging.exception("[SIM] Servo action failed")
            return

        if detach is None:
            detach = self._detach_after_move

        if detach:
            time.sleep(self._detach_delay)
            logging.info(f"[SIM] Servo {self.pin} detached (simulated)")

    def open(self):
        def _do():
            self.position = 1.0
            self.last_action = time.time()

        self._perform(_do)
        logging.info(f"[SIM] Servo {self.pin} -> OPEN (1.0)")

    def close(self):
        def _do():
            self.position = -1.0
            self.last_action = time.time()

        self._perform(_do)
        logging.info(f"[SIM] Servo {self.pin} -> CLOSE (-1.0)")

    def mid(self):
        def _do():
            self.position = 0.0
            self.last_action = time.time()

        self._perform(_do)
        logging.info(f"[SIM] Servo {self.pin} -> MID (0.0)")

    def set(self, value):
        def _do():
            self.position = value
            self.last_action = time.time()

        self._perform(_do)
        logging.info(f"[SIM] Servo {self.pin} -> SET {value}")

    def relax(self):
        logging.info(f"[SIM] Servo {self.pin} -> RELAX (detached)")