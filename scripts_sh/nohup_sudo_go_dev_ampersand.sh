#!/bin/bash
# Switch parrotpi back to DEV mode (client on home wifi).
sudo nmcli connection up parrotpi-dev



# old version, doesn't work
# Run as: nohup sudo nohup_sudo_go_dev_ampersand.sh &
#
# NOTE: if you are SSH'd into the pi over the parrotpi AP (192.168.4.1)
# you WILL lose this SSH session the moment wlan0 switches networks.
# That is expected. After ~15 seconds:
#   1. rejoin your home wifi on your PC
#   2. reconnect via `ssh u@parrotpi.local`  (mDNS on the home LAN)
#      or `ssh u@<dhcp-ip>` if mDNS isn't available
 
# set -e
 
# echo "Tearing down parrotpi-private (if active)..."
# nmcli connection down parrotpi-private 2>/dev/null || true
 
# echo "Bringing up parrotpi-dev (home wifi)..."
# nmcli connection up parrotpi-dev
 
# echo "Done - connected to home network"
