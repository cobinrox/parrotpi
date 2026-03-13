#!/bin/bash

# Installs as service, set to restart on boot automatically.
# Must be run as sudo

# use these to control service
# sudo systemctl daemon-reload
# sudo systemctl enable parrotpi
# sudo systemctl restart parrotpi
# systemctl status parrotpi


# Fail immediately if anything breaks
set -e

SERVICE_NAME="parrotpi"

# Resolve script directory (not where user runs it from)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

USER_NAME="$(whoami)"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python3"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
LOG_DIR="/var/log/parrotpi"
LOG_FILE="$LOG_DIR/server.log"
LOGROTATE_FILE="/etc/logrotate.d/parrotpi"

echo "Installing ParrotPi as a system service..."
echo "Project directory: $PROJECT_DIR"
echo "Python interpreter: $PYTHON_BIN"
echo "Log file: $LOG_FILE"
echo "Env file: /etc/parrotpi.env"
cp parrotpi.env /etc/parrotpi.env

# ---- sanity checks ----
if [ ! -f "$PYTHON_BIN" ]; then
  echo "ERROR: Python interpreter not found at $PYTHON_BIN"
  echo "Did you create the virtual environment?"
  exit 1
fi

if [ ! -d "$PROJECT_DIR/app" ]; then
  echo "WARNING: app directory not found in project dir"
fi

# ---- create log directory + file ----
echo "Creating log directory..."
sudo mkdir -p "$LOG_DIR"
sudo touch "$LOG_FILE"
sudo chown "$USER_NAME:$USER_NAME" "$LOG_DIR" "$LOG_FILE"

# ---- create systemd service ----
echo "Creating systemd service..."

sudo bash -c "cat > '$SERVICE_FILE'" <<EOF
[Unit]
Description=ParrotPi Server
After=network-online.target sound.target
Wants=network-online.target sound.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 2
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_BIN -m app.server
Restart=always
RestartSec=2
EnvironmentFile=/etc/parrotpi.env

# Logging
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=multi-user.target
EOF

# ---- reload systemd ----
echo "Reloading systemd..."
sudo systemctl daemon-reload

# ---- enable service at boot ----
echo "Enabling service to start on boot..."
sudo systemctl enable "$SERVICE_NAME"

# ---- start service ----
echo "Starting service..."
sudo systemctl restart "$SERVICE_NAME"

# ---- install logrotate ----
echo "Configuring log rotation..."

sudo bash -c "cat > '$LOGROTATE_FILE'" <<EOF
$LOG_FILE {
    size 5M
    rotate 5
    compress
    missingok
    notifempty
    copytruncate
}
EOF

echo "Log rotation configured: max 5 files, 5MB each."

# ---- show status ----
echo
echo "===== SERVICE STATUS ====="
systemctl --no-pager status "$SERVICE_NAME" || true

echo
echo "ParrotPi service installed."
echo "View logs with:"
echo "  tail -f $LOG_FILE"
echo "or:"
echo "  journalctl -u $SERVICE_NAME -f"
