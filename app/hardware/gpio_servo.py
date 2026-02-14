from gpiozero import Servo
from time import sleep

class RealServo:
    def __init__(self, pin):
        self.servo = Servo(pin)
        print(f"Servo on pin {pin} initialized")

    def open(self):
        self.servo.max()

    def close(self):
        self.servo.min()