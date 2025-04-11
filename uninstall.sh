#!/bin/bash
# uninstall.sh
# This script uninstalls the RetroPie Light Web Game Manager by stopping/disabling the service,
# removing the web_panel.service file, and (optionally) deleting the repository folder.

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo $0" >&2
    exit 1
fi

SERVICE_NAME="web_panel.service"
REPO_DIR="/home/pi/retropie_lwgmenager"

echo "Stopping the $SERVICE_NAME service..."
systemctl stop $SERVICE_NAME

echo "Disabling the $SERVICE_NAME service from autostart..."
systemctl disable $SERVICE_NAME

echo "Removing the service file from /etc/systemd/system/..."
if [ -f "/etc/systemd/system/$SERVICE_NAME" ]; then
    rm -f "/etc/systemd/system/$SERVICE_NAME"
    systemctl daemon-reload
    echo "$SERVICE_NAME removed successfully."
else
    echo "Service file $SERVICE_NAME does not exist in /etc/systemd/system/."
fi

read -p "Do you want to delete the repository folder ($REPO_DIR)? (y/n): " REMOVE_REPO
if [[ "$REMOVE_REPO" == "y" || "$REMOVE_REPO" == "Y" ]]; then
    if [ -d "$REPO_DIR" ]; then
        rm -rf "$REPO_DIR"
        echo "Repository folder removed successfully."
    else
        echo "Repository folder $REPO_DIR does not exist."
    fi
else
    echo "Repository folder not removed."
fi

echo "Web Panel uninstallation is complete."
