# parrotpi
Raspi Control for Parrot for BFAC, v0.7

## TLDR;
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
optionally edit config.py (e.g. set simulation mode)
python3 server.py
```
## Pin Setup
```
BEAK SERVO (see below for pin out map)
 Brown → Pin 6 (GND)
 Orange → Pin 2 or 4 (5V)
 Yellow → Pin 11 (GPIO 17)
```
## Original Set Up Notes (not formatted)
```
A) Build Pi Memory Card
0) Insert memory card, hint if using USB port/adapter, don't use a USB hub
a)   using Vanja OTG/USB Multi-Function Card Reader/Writer
1) download raspberrypi.com/software raspi imager
2) choose 32b Legacy Bookworm, NEXT
3) choose memory card for storage, NEXT
4) Customization:
   hostname: parrotpi
   capital city: Washington, DC
   Time zone: UTC
   Keyboard: us
   Username: u
   Password: p
   Network: secure network
   SSID: centrurylink...
   Password: home wifi password (5jh...)
   NEXT
   SSH Authentication
   Enable SSH: on
   Authentication: Password authentication
5) Choose WRITE Option

B) Start up Pi/w Memory Card
0) Insert card into pi
1) Plug in Pi to USB 2.0 Power
2) Turn on USB 2.0 ON switch

C) Initial connect to Pi/from PC
0) On PC, start terminal
1) Run: ping parrotpi.local
2) Run: ssh u@parrotpi.local

D) Add packages over SSH terminal
0) sudo apt update
   sudo apt install python3-flask (for web server)
1) sudo apt install sox libsox-fmt-all (for voice effx)
2) sudo apt install ffmpeg
3) sudo apt install git
4) sudo apt install hostapd dnsmasq (for wifi access pt)

E) Set up github project, personal token
0) Create repo on github
1) Set up github token
a)   click profile, settings, developer settings, Personal access tokens
b)   Choose basic, name it parrotpi
c)   Choose repo rights, generate: 
d) copy github project's https code address, and token
2) On pi, make dir for projects, e.g. mkdir projects
3) Change to projects dir
4) Run: git clone https://github.com/cobinrox/parrotpi.git
5) Run: cd parrotpi
6) Run: git config --global user.name "cobinrox"
7) Run: git config --global user.email "mescgroup@yahoo.com"
8) Make initial change then run git add ., git commit -m "initial", git push
a) provide username cobinrox, password token value
b) Run: git config --global credential.helper store

F) Set up Remote SSH on VSCode on Your PC
1) Start VSCode, go to Extensions tab, search for Remote SSH by Microsoft, Install
2) Ctrl+Shift+P, type Remote-SSH: Connect to Host, then Add Host, then enter ssh command used
a) ssh u@parrotpi.local, confirm .ssh/config file
b) on the far left edge at the very bottom of VSCode, click the >< green button and follow prompts

G) Save off Pi Image
1) On the Pi, run: sudo shutdown now
2) Remove memory card, insert into PC
3) Run Win32 Disk Imager
a)   enter an image name including the base memory size, e.g. parrotpi_32G_backup.img
b)   you should be able to restore the image to the same size of memory card or larger
c)   saves img file to downloads folder by default

H) Should have done this before step G, but install python pkgs
1) sudo apt install python3-venv
2) cd to the parrotpi directory
3) python3 -m venv venv
4) source venv/bin/activate
pip install flask gpiozero RPi.GPIO
pip install simpleaudio
pip freeze > requirements.txt

I) Dev work in VSCode
a) Start VS Code
b) start SSH window, may ask for the parrotpi passwor
c) 

J) Servo has three wires
a) Brown Ground
b) Red 5v power
c) orange/yellow/white signal pwm

 Top of Board (away from you)
USB ports are on the RIGHT →
+ IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII ----------| USB
+ IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII ----------| USB
+                                                 | ENET
+                                                 |
+ PWR --------------------------------------------

 3   G   G   G   G   G   G   G   3   G   G   G   G   G   G   G   G   G   G   G
 V   2   3   4   D  17  27  22   V  10   9  11   D   0   5   6  13  19  26   D
(1) (3) (5) (7) (9)(11)(13)(15)(17)(19)(21)(23)(25)(27)(29)(31)(33)(35)(37)(39)


 5   5   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G   G
 V   V   D  14  15  18   D  23  24   D  25   8   7   1   D  12   D  16  20  21
(2) (4) (6) (8)(10)(12)(14)(16)(18)(20)(22)(24)(26)(28)(30)(32)(34)(36)(38)(40)



```
   
   
   
   


