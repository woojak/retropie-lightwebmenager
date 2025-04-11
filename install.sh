#!/bin/bash
# install.sh - Fully Automatic Installation Script for the web_panel project

# This script installs the web_panel and related files, sets up the temporary folder,
# clones or updates the repository, adjusts permissions for all files in the project,
# and configures the systemd service (web_panel.service) to auto-start on boot.
# All project files are expected to reside in /home/pi/retropie_lwgmenager.

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Run with: sudo ./install.sh" >&2
    exit 1
fi

echo "Updating package lists..."
sudo apt-get update

echo "Installing required packages: git, python3, python3-pip, and whiptail..."
sudo apt-get install -y git python3 python3-pip whiptail

# Create temporary directory and set permissions
TEMP_DIR="/home/pi/tmp"
echo "Creating temporary directory at $TEMP_DIR..."
sudo mkdir -p "$TEMP_DIR"
sudo chmod 1777 "$TEMP_DIR"

# Define repository URL and installation directory
REPO_URL="https://github.com/woojak/retropie_lwgmenager.git"
INSTALL_DIR="/home/pi/retropie_lwgmenager"

# Clone the repository if the installation directory does not exist;
# otherwise, update the repository.
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists. Pulling latest changes..."
    cd "$INSTALL_DIR" && sudo git pull
else
    echo "Cloning repository from $REPO_URL into $INSTALL_DIR..."
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Set permissions for all files in the project folder
echo "Setting permissions for all files in $INSTALL_DIR..."
sudo chmod -R 755 "$INSTALL_DIR"

# Verify that the required files exist
if [ ! -f "$INSTALL_DIR/web_panel.py" ] || [ ! -f "$INSTALL_DIR/web_panel.service" ]; then
    echo "Error: Required files (web_panel.py or web_panel.service) are missing in $INSTALL_DIR"
    exit 1
fi

# Copy the web_panel.service file to /etc/systemd/system/
echo "Copying web_panel.service to /etc/systemd/system/ ..."
sudo cp "$INSTALL_DIR/web_panel.service" /etc/systemd/system/

# Reload the systemd daemon to register the new service
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable and start the service
echo "Enabling web_panel service to start on boot..."
sudo systemctl enable web_panel.service
echo "Starting web_panel service..."
sudo systemctl start web_panel.service

echo "Installation complete!"
echo "The web panel service is now running and set to start on boot."
