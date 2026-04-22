#!/bin/bash

# stops if running as a service
SERVICE_NAME="parrotpi"

echo "Stopping ParrotPi service..."
sudo systemctl stop $SERVICE_NAME

echo "Disabling ParrotPi service so it won't start on boot..."
sudo systemctl disable $SERVICE_NAME

echo "ParrotPi service stopped and disabled."