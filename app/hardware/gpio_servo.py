import logging
from gpiozero import Servo
from time import sleep


class RealServo:
    def __init__(
        self,
        pin,
        min_pulse_width: float = 0.0006,
        max_pulse_width: float = 0.0024,
        initial_pos: float = 0.0,
        detach_after_init: bool = True,
        detach_delay: float = 0.1,
    ):
        """Wrap gpiozero.Servo with safer startup behavior.

        - Sets a defined initial position to avoid undefined PWM at boot.
        - Optionally detaches the servo after a short delay to stop continuous pulses.
        - Allows tuning `min_pulse_width`/`max_pulse_width` for servo-specific ranges.
        """
        try:
            self.servo = Servo(
                pin, min_pulse_width=min_pulse_width, max_pulse_width=max_pulse_width
            )
            logging.info(
                f"Servo on pin {pin} initialized (min_pw={min_pulse_width}, max_pw={max_pulse_width})"
            )
        except Exception as e:
            logging.exception(f"Failed to initialize servo on pin {pin}: {e}")
            raise

        # Store detach behaviour for later moves
        self._detach_after_move = detach_after_init
        self._detach_delay = detach_delay

        # Set a safe initial position so the servo isn't driven to an undefined state.
        try:
            # Use the public setter for consistency with other methods
            # Use the internal perform helper to keep behavior consistent
            self._perform(lambda: setattr(self.servo, "value", initial_pos), detach=detach_after_init)
            logging.info(f"Servo on pin {pin} set to initial position {initial_pos}")
        except Exception:
            logging.exception("Failed to set initial servo position")

    def _perform(self, fn, detach: bool | None = None):
        """Run `fn()` then optionally detach after a short delay.

        - `fn` should be a no-argument callable that performs the servo action.
        - If `detach` is None, use the instance default set at init.
        """
        try:
            fn()
        except Exception:
            logging.exception("Servo action failed")
            return

        if detach is None:
            detach = self._detach_after_move

        if detach:
            sleep(self._detach_delay)
            try:
                self.servo.detach()
            except Exception:
                logging.exception("Failed to detach servo after action")

    def close(self):
        logging.info("Servo -> CLOSE(max)")
        self._perform(self.servo.max)

    def open(self):
        logging.info("Servo -> OPEN(min)")
        self._perform(self.servo.min)

    def mid(self):
        logging.info("Servo -> MID (0.0)")
        self._perform(self.servo.mid)

    def set(self, value):
        logging.info(f"Servo -> SET {value}")
        # Use a closure so _perform can call it uniformly
        self._perform(lambda: setattr(self.servo, "value", value))

    def relax(self):
        logging.info("Servo -> RELAX (detach)")
        try:
            self.servo.detach()
        except Exception:
            logging.exception("Failed to detach servo in relax()")
