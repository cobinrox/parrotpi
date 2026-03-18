#!/bin/bash

# Activate virtual environment
source venv/bin/activate
clear

# read the envfile and start
export $(grep -v '^#' parrotpi_small.env | xargs)
python3 -m app.server
