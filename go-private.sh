#!/bin/bash
# Switch parrotpi to private AP mode
# Run as: nohup sudo ~/go-private.sh &

systemctl stop dnsmasq
nmcli connection up parrotpi-private
sleep 5
systemctl start dnsmasq
echo "Done - parrotpi AP should be active"
