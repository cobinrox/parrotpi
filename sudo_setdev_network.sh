# set network to connect to home network for dev work and sshing 
# see /etc/NetworkManager/system-connections/*.nmconnection
# use sudo nmcli connection reload if you change the cfg file
#!/bin/bash
echo "Switching to dev mode..."
sudo systemctl stop dnsmasq
sudo nmcli connection up parrotpi-dev
sudo systemctl start dnsmasq
echo "Done - connected to home network"
