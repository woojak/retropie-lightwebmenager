#!/bin/bash
# gui_web_panel.sh - SSH GUI for RetroPie Light Web Game Manager
# This script provides a clear, menu-driven interface (using whiptail)
# to update configuration (stored in config.cfg) and to enable, disable,
# restart, and stop the web panel service.
# All project files should be in the same folder (e.g., /home/pi/retropie_lwgmanager).

# Check if whiptail is installed
if ! command -v whiptail >/dev/null 2>&1; then
  echo "whiptail is not installed. Installing..."
  sudo apt-get update && sudo apt-get install -y whiptail
fi

# Path to configuration file
CONFIG_FILE="config.cfg"

# Load configuration into an associative array CONFIG
declare -A CONFIG
if [ -f "$CONFIG_FILE" ]; then
  while IFS='=' read -r key value; do
    if [[ ! "$key" =~ ^# ]] && [ -n "$key" ]; then
      CONFIG["$key"]="$value"
    fi
  done < "$CONFIG_FILE"
else
  echo "Config file not found. Creating default config."
  cat <<EOF > "$CONFIG_FILE"
login=admin
password=mawerik1
secret_key=your_secret_key
port=5000
monitor_refresh=0.5
EOF
  CONFIG["login"]="admin"
  CONFIG["password"]="mawerik1"
  CONFIG["secret_key"]="your_secret_key"
  CONFIG["port"]="5000"
  CONFIG["monitor_refresh"]="0.5"
fi

# Function to save the configuration back to config.cfg
save_config() {
  cat <<EOF > "$CONFIG_FILE"
login=${CONFIG[login]}
password=${CONFIG[password]}
secret_key=${CONFIG[secret_key]}
port=${CONFIG[port]}
monitor_refresh=${CONFIG[monitor_refresh]}
EOF
}

# Function: Configure Credentials Menu
configure_credentials() {
  while true; do
    CHOICE=$(whiptail --title "Configure Credentials" --menu "Current Credentials:\nLogin: ${CONFIG[login]}\nPassword: ${CONFIG[password]}" 15 60 3 \
      "1" "Change Login (Current: ${CONFIG[login]})" \
      "2" "Change Password (Current: ${CONFIG[password]})" \
      "3" "Back" 3>&1 1>&2 2>&3)
    case $CHOICE in
      "1")
        NEW_LOGIN=$(whiptail --inputbox "Enter new login:" 8 60 "${CONFIG[login]}" 3>&1 1>&2 2>&3)
        if [ -n "$NEW_LOGIN" ]; then
          CONFIG[login]="$NEW_LOGIN"
          save_config
          whiptail --msgbox "Login updated to: ${CONFIG[login]}" 8 40
        fi
        ;;
      "2")
        NEW_PASSWORD=$(whiptail --inputbox "Enter new password:" 8 60 "${CONFIG[password]}" 3>&1 1>&2 2>&3)
        if [ -n "$NEW_PASSWORD" ]; then
          CONFIG[password]="$NEW_PASSWORD"
          save_config
          whiptail --msgbox "Password updated to: ${CONFIG[password]}" 8 40
        fi
        ;;
      "3")
        break
        ;;
      *)
        break
        ;;
    esac
  done
}

# Function: Configure App Settings Menu
configure_app_settings() {
  while true; do
    CHOICE=$(whiptail --title "Configure App Settings" --menu "Current App Settings:\nSecret Key: ${CONFIG[secret_key]}\nPort: ${CONFIG[port]}\nMonitor Refresh: ${CONFIG[monitor_refresh]} sec" 18 60 4 \
      "1" "Change Secret Key (Current: ${CONFIG[secret_key]})" \
      "2" "Change Port (Current: ${CONFIG[port]})" \
      "3" "Change Monitor Refresh Interval (Current: ${CONFIG[monitor_refresh]} sec)" \
      "4" "Back" 3>&1 1>&2 2>&3)
    case $CHOICE in
      "1")
        NEW_SECRET=$(whiptail --inputbox "Enter new secret key:" 8 60 "${CONFIG[secret_key]}" 3>&1 1>&2 2>&3)
        if [ -n "$NEW_SECRET" ]; then
          CONFIG[secret_key]="$NEW_SECRET"
          save_config
          whiptail --msgbox "Secret key updated to: ${CONFIG[secret_key]}" 8 40
        fi
        ;;
      "2")
        NEW_PORT=$(whiptail --inputbox "Enter new port:" 8 60 "${CONFIG[port]}" 3>&1 1>&2 2>&3)
        if [[ "$NEW_PORT" =~ ^[0-9]+$ ]]; then
          CONFIG[port]="$NEW_PORT"
          save_config
          whiptail --msgbox "Port updated to: ${CONFIG[port]}" 8 40
        else
          whiptail --msgbox "Invalid port value." 8 40
        fi
        ;;
      "3")
        NEW_REFRESH=$(whiptail --inputbox "Enter new refresh interval (sec, min 0.5):" 8 60 "${CONFIG[monitor_refresh]}" 3>&1 1>&2 2>&3)
        if [[ "$NEW_REFRESH" =~ ^[0-9]+(\.[0-9]+)?$ ]] && (( $(echo "$NEW_REFRESH >= 0.5" | bc -l) )); then
          CONFIG[monitor_refresh]="$NEW_REFRESH"
          save_config
          whiptail --msgbox "Monitor refresh updated to: ${CONFIG[monitor_refresh]} sec" 8 40
        else
          whiptail --msgbox "Invalid refresh value. Minimum is 0.5 sec." 8 40
        fi
        ;;
      "4")
        break
        ;;
      *)
        break
        ;;
    esac
  done
}

# Function: Service Management Menu (Restart/Enable/Disable/Stop Service)
manage_service() {
  while true; do
    CHOICE=$(whiptail --title "Service Management" --menu "Current Service Status:\n(Use this menu to manage the web panel service)" 15 60 5 \
      "1" "Restart Service" \
      "2" "Enable Service" \
      "3" "Disable Service" \
      "4" "Stop Service" \
      "5" "Back" 3>&1 1>&2 2>&3)
    case $CHOICE in
      "1")
        sudo systemctl restart web_panel.service
        whiptail --msgbox "Service restarted." 8 40
        ;;
      "2")
        sudo systemctl enable web_panel.service
        whiptail --msgbox "Service enabled." 8 40
        ;;
      "3")
        sudo systemctl disable web_panel.service
        whiptail --msgbox "Service disabled." 8 40
        ;;
      "4")
        sudo systemctl stop web_panel.service
        whiptail --msgbox "Service stopped." 8 40
        ;;
      "5")
        break
        ;;
      *)
        break
        ;;
    esac
  done
}

# Function: Run Install Script
run_install_script() {
  if [ -x "./install.sh" ]; then
    sudo ./install.sh
  else
    whiptail --msgbox "install.sh not found or not executable." 8 40
  fi
}

# Function: Run Uninstall Script
run_uninstall_script() {
  if [ -x "./uninstall.sh" ]; then
    sudo ./uninstall.sh
  else
    whiptail --msgbox "uninstall.sh not found or not executable." 8 40
  fi
}

# Main Menu Loop
while true; do
  CHOICE=$(whiptail --title "RetroPie Light Web Manager" --menu "Select an option:" 20 70 6 \
    "1" "Configure Credentials" \
    "2" "Configure App Settings" \
    "3" "Service Management" \
    "4" "Run Install Script" \
    "5" "Run Uninstall Script" \
    "6" "Exit" 3>&1 1>&2 2>&3)
  case $CHOICE in
    "1")
      configure_credentials
      ;;
    "2")
      configure_app_settings
      ;;
    "3")
      manage_service
      ;;
    "4")
      run_install_script
      ;;
    "5")
      run_uninstall_script
      ;;
    "6")
      exit 0
      ;;
    *)
      exit 0
      ;;
  esac
done
