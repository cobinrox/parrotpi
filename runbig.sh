#!/bin/bash

# Activate virtual environment
source venv/bin/activate
clear

# read the envfile and start
export $(grep -v '^#' parrotpi_big.env | xargs) && python3 -m app.server

# Start the server, no env file (old way)
#python3 -m app.server
