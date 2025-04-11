#!/bin/bash
# gui_web_panel.sh
# This script provides a text-based graphical interface (using whiptail)
# for managing the web panel. It allows modification of credentials, app settings,
# service control, and also lets you run the uninstall.sh and install.sh scripts.
# The web_panel.py file is assumed to be located in /home/pi/retropie-lightwebmenager

# Define paths
BASE_DIR="/home/pi/retropie-lightwebmenager"
WEB_PANEL="$BASE_DIR/web_panel.py"
SERVICE_NAME="web_panel.service"
UNINSTALL_SCRIPT="$BASE_DIR/uninstall.sh"
INSTALL_SCRIPT="$BASE_DIR/install.sh"

# Function: Modify Credentials (Login and Password)
modify_credentials(){
    NEW_LOGIN=$(whiptail --inputbox "Enter new login:" 8 60 "$(grep '\"login\"' "$WEB_PANEL" | head -n1 | cut -d'"' -f4)" 3>&1 1>&2 2>&3)
    NEW_PASSWORD=$(whiptail --inputbox "Enter new password:" 8 60 "$(grep '\"password\"' "$WEB_PANEL" | head -n1 | cut -d'"' -f4)" 3>&1 1>&2 2>&3)
    if [ -n "$NEW_LOGIN" ]; then
        sed -i 's/"login": "[^"]*"/"login": "'"$NEW_LOGIN"'"/' "$WEB_PANEL"
    fi
    if [ -n "$NEW_PASSWORD" ]; then
        sed -i 's/"password": "[^"]*"/"password": "'"$NEW_PASSWORD"'"/' "$WEB_PANEL"
    fi
    whiptail --msgbox "Credentials updated." 8 40
}

# Function: Modify App Settings (Secret Key, Port, Refresh Interval)
modify_app_settings(){
    NEW_SECRET_KEY=$(whiptail --inputbox "Enter new secret key:" 8 60 "$(grep '\"secret_key\"' "$WEB_PANEL" | head -n1 | cut -d'"' -f4)" 3>&1 1>&2 2>&3)
    NEW_PORT=$(whiptail --inputbox "Enter new port:" 8 60 "$(grep '\"port\"' "$WEB_PANEL" | head -n1 | cut -d: -f2 | sed 's/[ ,]//g')" 3>&1 1>&2 2>&3)
    NEW_REFRESH=$(whiptail --inputbox "Enter new monitoring refresh interval (seconds, min 0.5):" 8 60 "$(grep '\"monitor_refresh\"' "$WEB_PANEL" | head -n1 | cut -d: -f2 | sed 's/[ ,]//g')" 3>&1 1>&2 2>&3)
    if [ -n "$NEW_SECRET_KEY" ]; then
        sed -i 's/"secret_key": "[^"]*"/"secret_key": "'"$NEW_SECRET_KEY"'"/' "$WEB_PANEL"
    fi
    if [[ "$NEW_PORT" =~ ^[0-9]+$ ]]; then
        sed -i 's/"port": [0-9]\+/"port": '"$NEW_PORT"'/' "$WEB_PANEL"
    fi
    if [ -n "$NEW_REFRESH" ]; then
        sed -i 's/"monitor_refresh": [0-9.]\+/"monitor_refresh": '"$NEW_REFRESH"'/' "$WEB_PANEL"
    fi
    whiptail --msgbox "App settings updated. (Port changes will take effect on restart.)" 8 50
}

# Function: Service Control Menu
service_control(){
    CHOICE=$(whiptail --title "Service Control" --menu "Choose an action:" 15 60 4 \
      "1" "Restart Service" \
      "2" "Enable Service" \
      "3" "Disable Service" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then
        return
    fi
    case $CHOICE in
        "1")
            systemctl restart $SERVICE_NAME
            whiptail --msgbox "Service restarted." 8 40
            ;;
        "2")
            systemctl enable $SERVICE_NAME
            whiptail --msgbox "Service enabled." 8 40
            ;;
        "3")
            systemctl disable $SERVICE_NAME
            whiptail --msgbox "Service disabled." 8 40
            ;;
    esac
}

# Function: Run Uninstall Script
run_uninstall(){
    if [ -f "$UNINSTALL_SCRIPT" ]; then
        bash "$UNINSTALL_SCRIPT"
    else
        whiptail --msgbox "Uninstall script not found." 8 40
    fi
}

# Function: Run Install Script
run_install(){
    if [ -f "$INSTALL_SCRIPT" ]; then
        bash "$INSTALL_SCRIPT"
    else
        whiptail --msgbox "Install script not found." 8 40
    fi
}

# Main Menu Loop
while true; do
    OPTION=$(whiptail --title "Web Panel Manager" --menu "Select an option:" 20 80 7 \
        "1" "Modify Credentials (Login/Password)" \
        "2" "Modify App Settings (Secret Key, Port, Refresh Interval)" \
        "3" "Service Control (Restart/Enable/Disable)" \
        "4" "Run Uninstall Script" \
        "5" "Run Install Script" \
        "6" "Exit" 3>&1 1>&2 2>&3)
    RETVAL=$?
    if [ $RETVAL -ne 0 ]; then
        exit 0
    fi
    case $OPTION in
        "1")
            modify_credentials
            ;;
        "2")
            modify_app_settings
            ;;
        "3")
            service_control
            ;;
        "4")
            run_uninstall
            ;;
        "5")
            run_install
            ;;
        "6")
            exit 0
            ;;
    esac
done
