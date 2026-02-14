from gpiozero import Button

class RealInput:
    def __init__(self, pin, pull_up=True):
        self.pin = pin
        self.button = Button(pin, pull_up=pull_up)
        print(f"Input on pin {pin} initialized")

    def is_pressed(self):
        return self.button.is_pressed

    def wait_for_press(self):
        self.button.wait_for_press()

    def wait_for_release(self):
        self.button.wait_for_release()