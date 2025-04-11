
# RetroPie Light Web Game Manager

This repository contains a full-featured web panel for managing your RetroPie file system, monitoring system performance, and controlling your Raspberry Pi. The web interface is built using Python and Flask, and it features persistent configuration storage, system control options (such as reboot/shutdown), file management, and a text-based SSH GUI for changing settings and managing the service.

## Repository Contents

- **web_panel.py**  
  The main Python Flask application that provides:
  - File and directory management (browse, upload, delete, edit).
  - System monitoring (CPU temperature, CPU usage, memory usage, disk usage).
  - NVMe sensor selection with persistence (the last selected sensor is stored in `selected_sensor.txt`).
  - System control functions (reboot and shutdown the Raspberry Pi).
  - An endpoint for editing `/boot/firmware/config.txt`.

- **config.cfg**  
  A configuration file that stores persistent settings (login, password, secret key, port, and monitoring refresh interval).

- **web_panel.service**  
  A systemd service file to run the Flask application at startup.

- **install.sh**  
  An installation script that automates the following:
  - Updating packages and installing dependencies.
  - Creating a temporary directory with the correct permissions.
  - Cloning or updating the repository.
  - Setting executable permissions for project files.
  - Installing the systemd service and starting the web panel automatically at boot.

- **uninstall.sh**  
  An uninstallation script that stops and disables the web panel service and optionally deletes the repository folder.

- **gui_web_panel.sh**  
  A text-based graphical (TUI) script (using whiptail) for managing settings and service control via SSH. It offers separate submenus for:
  - Configuring credentials (login & password).
  - Configuring app settings (secret key, port, and monitoring refresh interval).
  - Managing the service (restart, enable, disable).
  - Running install and uninstall scripts.

## Prerequisites

- A Raspberry Pi running RetroPie.
- Basic familiarity with the terminal.
- Required packages: `python3`, `git`, `python3-pip`, and `whiptail`.

> **Note:** Ensure that you have a temporary directory (`/home/pi/tmp`) set up with appropriate permissions:
> ```bash
> sudo mkdir -p /home/pi/tmp && sudo chmod 1777 /home/pi/tmp
> ```

## Installation Steps

1. **Clone the Repository**

   Open a terminal and run:
   ```bash
   sudo git clone https://github.com/yourusername/retropie_lwgmenager.git /home/pi/retropie_lwgmenager
   cd /home/pi/retropie_lwgmenager
   ```
   > If the repository is already present, update it using:
   > ```bash
   > cd /home/pi/retropie_lwgmenager && sudo git pull
   > ```

2. **Run the Installation Script**

   Make the installation script executable and run it:
   ```bash
   sudo chmod +x install.sh
   sudo ./install.sh
   ```
   This script will:
   - Update your package lists and install dependencies.
   - Create the `/home/pi/tmp` directory with proper permissions.
   - Clone or update the repository.
   - Adjust file permissions for all project files.
   - Copy `web_panel.service` to `/etc/systemd/system/`.
   - Reload systemd, enable the service for auto-start on boot, and start the service immediately.

3. **Verify the Service**

   Check the service status with:
   ```bash
   sudo systemctl status web_panel.service
   ```
   If any issues occur, review logs with:
   ```bash
   sudo journalctl -u web_panel.service
   ```

## Usage and Operation

### Web Interface

Access the web panel by navigating to your Raspberry Pi’s IP address and the configured port (default is `5000`) in your browser. The web interface includes:

- **Monitoring Section:**  
  Displays live system statistics (CPU temperature, usage, memory usage, disk usage) using progress bars.  
  *NVMe Sensor:* A dropdown allows you to select an NVMe sensor. Your selection is saved to a file so that it persists across page refreshes.

- **Control Section:**  
  Provides buttons to **Reboot** or **Shutdown** your Raspberry Pi directly from the interface.

- **File Management:**  
  Browse directories, upload files (with a real-time progress bar), create folders, edit files, and delete files or folders (with bulk deletion capability).

- **Configuration:**  
  Modify:
  - **Admin Credentials:** Change the login and password.
  - **App Settings:** Change the secret key, port, and monitoring refresh interval.
  These settings are stored in `config.cfg` and persist across restarts.

### SSH GUI

Run the text-based GUI to manage settings and service control from an SSH session:
```bash
sudo /home/pi/retropie_lwgmenager/gui_web_panel.sh
```
This TUI lets you:
- Configure credentials (displaying current values).
- Configure app settings (secret key, port, and monitoring refresh interval).
- Manage the service by restarting, enabling, or disabling it.
- Run the install or uninstall scripts.

## Customization

You can customize various aspects of the web panel:

- **Configuration:**  
  Edit `config.cfg` directly to change default values if needed.

- **Monitoring Refresh:**  
  The refresh interval is configurable; set a minimum of `0.5` seconds.

- **Service Control:**  
  The web panel includes controls to restart, enable, or disable the service via the web interface or SSH GUI.

## Uninstallation

To uninstall the web panel, run:
```bash
sudo chmod +x uninstall.sh
sudo ./uninstall.sh
```
The uninstallation script will stop and disable the service, remove the systemd service file, and prompt you whether to delete the repository folder.

## Troubleshooting Tips

- **Service Not Running:**  
  Check the status and logs:
  ```bash
  sudo systemctl status web_panel.service
  sudo journalctl -u web_panel.service
  ```

- **File Upload Issues:**  
  Ensure that the temporary directory exists:
  ```bash
  sudo mkdir -p /home/pi/tmp && sudo chmod 1777 /home/pi/tmp
  ```

- **NVMe Sensor Persistence:**  
  The selected sensor is saved to `selected_sensor.txt` in the project folder. Make sure this file is accessible.

## Contributing

Contributions, issues, and feature requests are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.


Enjoy using the RetroPie Light Web Manager to efficiently manage your RetroPie setup!
```

---

Feel free to adjust the repository URL, author information, and any other details as needed. This README is now ready to be copied into your GitHub repository.
