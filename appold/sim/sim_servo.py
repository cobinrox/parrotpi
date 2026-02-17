class SimServo:
    def __init__(self, pin):
        self.pin = pin
        self.position = "closed"
        print(f"[SIM] Servo on pin {pin} initialized")

    def open(self):
        self.position = "open"
        print(f"[SIM] Servo on pin {self.pin} -> OPEN")

    def close(self):
        self.position = "closed"
        print(f"[SIM] Servo on pin {self.pin} -> CLOSE")