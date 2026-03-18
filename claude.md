# ParrotPi — Raspberry Pi Animatronic Controller

ParrotPi is a Python‑based animatronic control system designed for the Raspberry Pi.  
It drives servos and GPIO‑connected components, exposes a lightweight web API, and provides a simple UI for triggering movements and behaviors. The project emphasizes clarity, modularity, and hardware abstraction so it can be easily understood, modified, and extended.

---

## Project Overview

ParrotPi turns a Raspberry Pi into a small animatronic controller capable of:

- Driving multiple servos (beak, head, wings, etc.)
- Running behaviors and animations via REST endpoints
- Providing a web‑based control interface
- Running automatically at boot as a systemd service
- Logging activity to `/var/log/parrotpi` with log rotation
- Running in **simulation mode** on non‑Pi hardware

The system is intentionally simple and hackable, making it ideal for robotics, puppetry, cosplay animatronics, and educational builds.

---

##  Architecture Summary (15‑Point Overview)

### 1. **Purpose** 
Control animatronic components via servos and GPIO, with a web API for remote triggering.
### 2. **Hardware Platform** — 
Raspberry Pi using its GPIO pins for PWM and digital I/O.
### 3. **Language** — 
Entirely written in Python 3.
### 4. **GPIO Library** — 
Uses `gpiozero` as the high‑level GPIO abstraction layer, with `RPi.GPIO` as the backend driver for real hardware control.


### 6. **Pin Mapping** — 
A central dictionary (`SERVO_PINS`) maps servo names (e.g.,`beak` ,`head` ) to GPIO pin numbers.
This allows easy re‑wiring without changing logic.  The original pin usage is:
```
## Pin Setup
```
BEAK SERVO (see below for pin out map)
 Brown - Pin 6 (GND)
 Orange - Pin 2 or 4 (5V)
 Yellow - Pin 11 (GPIO 17)
```

### 8. **Web Server** — Flask app (`server.py`) exposes REST endpoints for servo control and behaviors.
A lightweight Flask web server () exposes REST endpoints for:
• 	moving servos
• 	triggering behaviors
• 	reading inputs
• 	running animations
The web UI communicates with these endpoints via AJAX/Fetch.

### 9. **Directory Structure** —
```
parrotpi/
  app/
    server.py
    gpio_inputs.py
    servo_controller.py
    sim_servo.py
    real_servo.py
    config.py
  venv/
  static/
  templates/
  install_as_service.sh
``` 

### 11. **Logging** — 
When run as a service, writes to `/var/log/parrotpi/server.log` with logrotate support.

### 12. **Systemd Integration** — 
A custom script (`install_as_service.sh`) installs the project as a systemd service so it:
• 	starts automatically at boot
• 	waits for Wi‑Fi/network
• 	restarts on crash
• 	logs to the correct directory

### 13. **Virtual Environment** — 
Uses a local Python venv inside the project directory.
The systemd service explicitly uses this interpreter.

### 14. **Dependencies** — Flask, gpiozero, RPi.GPIO, plus standard Python libraries.
Core Python dependencies include:
- Flask — web server
- gpiozero — GPIO abstraction
- RPi.GPIO — hardware backend
- logrotate (system-level) — log management
- gunicorn (optional) — production WSGI server

### 15. **Design Philosophy** — Clear, modular, hardware‑abstracted, easy to set up and extend.

### 16. Initial Set Up Notes
See the README.md file for setting up raspberry pi

## Raspberry Pi GPIO Notes
```
Top of Board (away from you)
USB ports are on the right side of board

 5   5   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G
 V   V   D  14  15  18   D  23  24   D  25   8   7   1   D  12   D  16  20  21
(2) (4) (6) (8)(10)(12)(14)(16)(18)(20)(22)(24)(26)(28)(30)(32)(34)(36)(38)(40)


 3   G   G   G   G   G   G   G   3   G   G   G   G   G   G   G   G   G   G   G
 V   2   3   4   D  17  27  22   V  10   9  11   D   0   5   6  13  19  26   D
(1) (3) (5) (7) (9)(11)(13)(15)(17)(19)(21)(23)(25)(27)(29)(31)(33)(35)(37)(39)

Raspberry Pi Model B+ (40-pin) GPIO Functional Summary

POWER PINS                  I2C                      UART
Pin 1  - 3.3V               Pin 3  - GPIO2  SDA     Pin 8  - GPIO14 TXD
Pin 17 - 3.3V               Pin 5  - GPIO3  SCL     Pin 10 - GPIO15 RXD
Pin 2  - 5V
Pin 4  - 5V
Pin 6  - GND
Pin 9  - GND
Pin 14 - GND
Pin 20 - GND
Pin 25 - GND
Pin 30 - GND
Pin 34 - GND
Pin 39 - GND


SPI                         HARDWARE PWM             HAT EEPROM
Pin 19 - GPIO10 MOSI       Pin 12 - GPIO18 PWM0     Pin 27 - GPIO0
Pin 21 - GPIO9  MISO       Pin 32 - GPIO12 PWM0     Pin 28 - GPIO1
Pin 23 - GPIO11 SCLK       Pin 33 - GPIO13 PWM1
Pin 24 - GPIO8  CE0        Pin 35 - GPIO19 PWM1
Pin 26 - GPIO7  CE1


GENERAL PURPOSE GPIO
Pin 7  - GPIO4              Pin 29 - GPIO5
Pin 11 - GPIO17             Pin 31 - GPIO6
Pin 13 - GPIO27             Pin 36 - GPIO16
Pin 15 - GPIO22             Pin 37 - GPIO26
Pin 16 - GPIO23             Pin 38 - GPIO20
Pin 18 - GPIO24             Pin 40 - GPIO21
Pin 22 - GPIO25


ELECTRICAL NOTES
3.3V logic only
Not 5V tolerant
~16mA per pin recommended
~50mA total across GPIO

```
