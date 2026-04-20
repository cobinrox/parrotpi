# after 5 mins, reset network to dev mode
(sleep 300 && sudo nmcli connection up parrotpi-dev) &
