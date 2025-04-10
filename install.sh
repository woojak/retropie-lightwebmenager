#!/bin/bash
# install_web_panel.sh
# Fully automated installation script for web_panel.py

# Check for root privileges
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root. Use: sudo ./install_web_panel.sh" 
   exit 1
fi

echo "Updating package lists..."
apt-get update

echo "Installing required packages: git, python3, python3-pip..."
apt-get install -y git python3 python3-pip

# Define repository URL and installation directory
REPO_URL="https://github.com/woojak/retropie_lwgmenager.git"
INSTALL_DIR="/home/pi/retropie-lightwebmenager"

# Clone repository or update existing repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR exists. Pulling latest changes..."
    cd "$INSTALL_DIR" && git pull
else
    echo "Cloning repository into $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Verify that required files exist in the repository
if [ ! -f "$INSTALL_DIR/web_panel.py" ] || [ ! -f "$INSTALL_DIR/web_panel.service" ]; then
    echo "Error: Required files (web_panel.py or web_panel.service) are not found in $INSTALL_DIR"
    exit 1
fi

echo "Copying web_panel.service file to /etc/systemd/system/ ..."
cp "$INSTALL_DIR/web_panel.service" /etc/systemd/system/

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling web_panel service to start at boot..."
systemctl enable web_panel.service

echo "Starting web_panel service..."
systemctl start web_panel.service

echo "Installation complete. The Web Panel service is now running and enabled on boot."
