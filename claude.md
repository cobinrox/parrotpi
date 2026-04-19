# ParrotPi — Raspberry Pi Animatronic Controller

This is a python3 flask web server for a raspberry pi-controlled anamatronic toy parrot.  It serves a web page which 
sends REST calls to the server such as move beak open/close, increase/
decrease volume, playback a phrase (previously recorded wav file), and
provide a push-to-talk socketio microphone near-realtime stream to
playback through the parrot.  When the parrot noises are played,
the beak servo opens and closes while playing.  It also has a start
up wav file that it plays upon start up to make sure that the sound card
(MAX-98357A) was initialized properly and is working ok.

## Features
- Every several seconds the web pages asks the server for a "busy" status which tells the web page if someone else is using the parrot.  The web page will disable its buttons if it is busy.
- There is a volume and pitch control on the web page that allows the user to change the volume and pitch of the parrot voice.
- There is an emergency STOP button on the web page that can be used if the state of the server and page gets out of whack.
- There is also a Restart button on the web page that allows a user to restart the server itself-- again for emergencies.
- There is a Request/Allow Mic Access button on the web page that requests access to the microphone (either on a PC or phone).  Once the user acknowledges/allows access, then the allow state is set to true and the Hold to Talk button enables.
- When the Hold to Talk button is pressed, it will stream the users voice over socketio to the server which will play back the voice in near-real time to the speaker of the pi.  It will also apply a pitch and volume based on those slider values on the web page.
- There are several pre-recorded WAV files that the user of the web page can use to play back phrases and the "Replay" button plays back the last recorded phrase when a user had clicked the Hold to Talk button.
- There are also a few beak open/close buttons that tell the server to open/close the parrot's beak
- There is also an Admin dialog that allows you to set a basic network mode for the pi: either broadcasting as a private wifi network/w SSID parrotpi (this is what you would use for deployment/party scenario) or for connecting to a known home wifi network (this is what you would probably normally use during development).  The network modes should be defined in the network management client folder as parrot-private and parrot-dev configuration files, resp.  When running parrot-private on the parrotpi SSID, you can ssh into the pi vi ssh u@192.168.4.1.  When running parrot-dev on a home network, you can ssh into the pi as ssh u@xx.yy.zz.aa, based on the DHCP ip assigned to the pi at boot up by the home network.
- Again, remember, though, that the buttons are enabled when the parrot server has returned a not-busy poll.


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
    static/
      audio/
       various WAV files
    templates/
       index.html
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
