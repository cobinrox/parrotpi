sudo systemctl stop caddy
sudo rm -rf /var/lib/caddy/.local
sudo rm -rf /var/lib/caddy/.config


sudo rm -rf /var/lib/caddy/.local/share/caddy/pki
sudo systemctl start caddy

sudo journalctl -u caddy -n 30 --no-pager

openssl s_client -connect localhost:443 -servername parrotpi

