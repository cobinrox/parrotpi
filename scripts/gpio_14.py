from gpiozero import LED
import time

# ---------------------------------------------------------
# CONFIGURATION — EDIT THESE TWO VALUES
# ---------------------------------------------------------
PIN = 17              # GPIO pin number
DURATION = 5 * 60     # seconds (5 minutes)
BLINK_INTERVAL = 0.5  # seconds on/off
# ---------------------------------------------------------

def blink(pin, duration, interval):
    led = LED(pin)
    print(f"Blinking GPIO {pin} for {duration} seconds...")

    end_time = time.time() + duration

    while time.time() < end_time:
        led.on()
        time.sleep(interval)
        led.off()
        time.sleep(interval)

    led.off()
    print(f"Done. GPIO {pin} is now OFF.")

if __name__ == "__main__":
    blink(PIN, DURATION, BLINK_INTERVAL)