import logging
from gpiozero import Servo
from time import sleep

class RealServo:
    def __init__(self, pin):
        self.servo = Servo(pin)
        logging.info(f"Servo on pin {pin} initialized")

    def open(self):
        logging.info("Servo -> OPEN (max)")
        self.servo.max()

    def close(self):
        logging.info("Servo -> CLOSE (min)")
        self.servo.min()

    def mid(self):
        logging.info("Servo -> MID (0.0)")
        self.servo.mid()

    def set(self, value):
        logging.info(f"Servo -> SET {value}")
        self.servo.value = value

    def relax(self):
        logging.info("Servo -> RELAX (detach)")
        self.servo.detach()