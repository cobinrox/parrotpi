import time

def log(msg):
    print(f"[LOG] {msg}")

def timestamp():
    return int(time.time())

def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))