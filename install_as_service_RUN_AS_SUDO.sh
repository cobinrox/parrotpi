#!/bin/bash

# install this as a systemd service so that it will start automatically
# on start up of the pi (and after the wifi has been established)
# also logs to /var/log/parrotpi/servr.log which auto rotates
SERVICE_NAME="parrotpi"

USER_NAME="$(whoami)"
PROJECT_DIR="$(pwd)"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python3"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
LOG_DIR="/var/log/parrotpi"
LOG_FILE="$LOG_DIR/server.log"

echo "Installing ParrotPi as a system service..."
echo "Project directory: $PROJECT_DIR"
echo "Python interpreter: $PYTHON_BIN"
echo "Log file: $LOG_FILE"

# Create log directory
sudo mkdir -p $LOG_DIR
sudo chown $USER_NAME:$USER_NAME $LOG_DIR

# Create the systemd service file
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=ParrotPi Server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_BIN -m app.server
Restart=always
RestartSec=2

# Logging
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

# Ensure logs don't grow forever
# systemd will rotate automatically when using journal,
# but since we are writing to a file, we use logrotate.
EOF

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling service to start on boot..."
sudo systemctl enable $SERVICE_NAME

echo "Starting service now..."
sudo systemctl start $SERVICE_NAME

# Install logrotate rule
LOGROTATE_FILE="/etc/logrotate.d/parrotpi"
sudo bash -c "cat > $LOGROTATE_FILE" <<EOF
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

echo "ParrotPi service installed and running."