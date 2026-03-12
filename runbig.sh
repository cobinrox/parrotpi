#!/bin/bash

# Activate virtual environment
source venv/bin/activate
clear

# read the envfile and start
export $(grep -v '^#' parrotpi_big.env | xargs) #&& python3 -m app.server

# Force ALSA / avoid Pulse for this run
export PULSE_SERVER=
export SDL_AUDIODRIVER=alsa
export PA_ALSA_PLUGHW=1

# NEW: Force simpleaudio to use card 0
export ALSA_PCM_DEVICE=hw:0,0
export DEFAULT_PCM_CARD=0

# Start the server, no env file (old way)
python3 -m app.server
