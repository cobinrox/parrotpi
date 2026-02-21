# parrotpi
Raspi Control for Parrot for BFAC Setup Notes v0.8

## TLDR;
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
optionally edit config.py (e.g. set simulation mode)
python3 server.py
For tech information, see claude.md file
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
5) sudo apt install python3-venv (for python env)
6) sudo apt install libopenblas0 libopenblas-dev
sudo apt install libportaudio2 libportaudiocpp0 portaudio19-dev

E) Set up github project, personal token
0) Create repo on github
1) Set up github token
a)   click profile, settings, developer settings, Personal access tokens
b)   Choose basic, name it parrotpi
c)   Choose repo rights, generate AND SAVE IT
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
c) dumb, but make another change and push, then another change and push, now your token should be good

F) Set virtual environment
1) cd to the parrotpi directory
2) `./1_venv_create.sh`
3) IMPORTANT NOTE SYNTAX! `source 2_venv_activate.sh`
3) `./3_venv_req_install.sh`

G) Test GPIO pins
1) Connect an LED + lead on gpio 17 (pin 11)
2) Connect the LED's - lead on Ground
3) In parrotpi dir, change to scripts
4) Run: python gpio_17.py
5) LED should blink on and off

H) Set up to have parrot server start up on boot
0) (IMPORTANT NOTE: Must have the venv activated!)
1) In parrotpi dir, run: sudo install_as_service_RUN_AS_SUDO.sh

H) Set up Remote SSH on VSCode on Your PC
1) Start VSCode, go to Extensions tab, search for Remote SSH by Microsoft, Install
2) Ctrl+Shift+P, type Remote-SSH: Connect to Host, then Add Host, then enter ssh command used
a) ssh u@parrotpi.local, confirm .ssh/config file
b) on the far left edge at the very bottom of VSCode, click the >< green button and follow prompts

I) Save off Pi Image
1) On the Pi, run: sudo shutdown now
2) Remove memory card, insert into PC
3) Run Win32 Disk Imager
a)   enter an image name including the base memory size, e.g. parrotpi_32G_backup.img
b)   you should be able to restore the image to the same size of memory card or larger
c)   saves img file to downloads folder by default


```
   
   
   
   


