#!/bin/bash
# Switch parrotpi to private AP mode
# Run as: nohup sudo ~/go-private.sh &
# NOTE: you WILL lose SSH when wlan0 switches networks — that's expected.
# After ~15 seconds, rejoin the "parrotpi" SSID on your client and ssh u@192.168.4.1

set -e

echo "Bringing up parrotpi-private AP..."
nmcli connection up parrotpi-private

echo "Done — parrotpi AP should be active at 192.168.4.1"
