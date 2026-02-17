class SimInput:
    def __init__(self, pin, pull_up=True):
        self.pin = pin
        self.pull_up = pull_up
        self.state = False
        print(f"[SIM] Input on pin {pin} initialized (pull_up={pull_up})")

    def is_pressed(self):
        return self.state

    def wait_for_press(self):
        print(f"[SIM] Waiting for press on pin {self.pin} (simulated)")

    def wait_for_release(self):
        print(f"[SIM] Waiting for release on pin {self.pin} (simulated)")

    def set_state(self, pressed: bool):
        self.state = pressed
        print(f"[SIM] Input on pin {self.pin} set to {'PRESSED' if pressed else 'RELEASED'}")