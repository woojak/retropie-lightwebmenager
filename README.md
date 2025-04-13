# RetroPie Light Web Game Manager

This repository contains a full-featured web panel for managing your RetroPie file system, monitoring system performance, and controlling your Raspberry Pi. The web interface is built using Python and Flask, featuring persistent configuration storage, system control options (such as reboot/shutdown), comprehensive file management with bulk selection (including a “select all” feature), and a text-based SSH GUI for managing settings and controlling the service.

## Repository Contents

- **web_panel.py**  
  The main Python Flask application that provides:
  - **File and Directory Management:**  
    Browse directories, upload files (with a real-time progress bar and dynamic upload speed display), create folders, edit files, and delete files/folders. The file management section now supports bulk selection via a “select all” checkbox for quickly managing multiple files at once.
  - **System Monitoring:**  
    Displays live system statistics, including CPU temperature, CPU frequency (current and maximum), memory usage, disk usage, and system uptime. Visual progress bars represent these metrics, with the CPU usage display now showing the current/max CPU frequency.
  - **NVMe Sensor Selection:**  
    If enabled in the configuration, you can choose an NVMe sensor from a dropdown menu to monitor its temperature. Your selection is saved persistently.
  - **System Control Functions:**  
    Reboot or shutdown your Raspberry Pi directly from the web interface without accidental re-triggering of the action upon page refresh.
  - **Configuration Management:**  
    Modify application settings—including admin credentials, secret key, port, monitoring refresh interval, NVMe sensor display, and the configuration file location for editing RPI config.txt—via a dedicated settings page. All changes are persistently saved in `config.cfg`.
  - **Editing RPI Config.txt:**  
    Provides an endpoint for modifying the Raspberry Pi configuration file. You can now choose between editing `/boot/firmware/config.txt` (for 64-bit systems) or `/boot/config.txt` (for 32-bit systems) based on the selection stored in the configuration file.

- **config.cfg**  
  A configuration file that stores persistent settings, including:
  - Admin credentials (default: login: admin and password: mawerik1 — recommended to change)
  - Secret key (recommended to change)
  - Port number
  - Monitoring refresh interval (with a minimum of 0.5 seconds)
  - NVMe sensor selection and display status (if an NVMe device is present)
  - The config file location selection for editing the RPI configuration (choosing between the 64-bit system `/boot/firmware/config.txt` or the 32-bit system `/boot/config.txt`)

- **web_panel.service**  
  A systemd service file that runs the Flask application on startup.

- **install.sh**  
  An installation script that automates:
  - Updating packages and installing dependencies.
  - Creating the temporary directory with proper permissions.
  - Cloning (or updating) the repository.
  - Setting executable permissions for project files.
  - Installing the systemd service, enabling it to start at boot, and starting the service immediately.

- **uninstall.sh**  
  An uninstallation script that stops and disables the web panel service and optionally deletes the repository folder.

- **gui_web_panel.sh**  
  A text-based graphical (TUI) script (using whiptail) for managing settings and controlling the service via SSH. It offers submenus for:
  - Configuring credentials (displaying current values).
  - Configuring app settings (secret key, port, monitoring refresh interval, and config file location).
  - Managing the service (restart, enable, stop, disable).
  - Running the install or uninstall scripts.

## Prerequisites

- A Raspberry Pi running RetroPie.
- Basic familiarity with the terminal.
- Required packages: `python3`, `git`, `python3-pip`, and `whiptail`.

## Installation Steps

### 1. Clone the Repository

Open a terminal and run:
```bash
sudo git clone --depth=1 https://github.com/woojak/retropie_lwgmenager.git
cd /home/pi/retropie_lwgmenager
```
If the repository is already present, update it using:
```bash
cd /home/pi/retropie_lwgmenager && sudo git pull
```

### 2. Run the Installation Script

Make the installation script executable and run it:
```bash
sudo chmod +x install.sh
sudo ./install.sh
```
This script will:
- Update your package lists and install dependencies.
- Create the `/home/pi/tmp` directory with proper permissions.
- Clone (or update) the repository.
- Set executable permissions for all project files.
- Copy `web_panel.service` to `/etc/systemd/system/`.
- Reload systemd, enable the service to start at boot, and start it immediately.

### 3. Verify the Service

Check the service status with:
```bash
sudo systemctl status web_panel.service
```
If issues occur, review logs with:
```bash
sudo journalctl -u web_panel.service
```

---

## Usage and Operation

### Web Interface

![Screenshot](https://raw.githubusercontent.com/woojak/retropie_lwgmenager/refs/heads/main/images/Main.png)

Access the web panel (default credentials: user: admin, password: mawerik1) by navigating to your Raspberry Pi’s IP address and the configured port (default is 5000) in your browser. The web interface includes:

- **Monitoring Section:**  
  Displays live system statistics such as CPU temperature, CPU frequency (in MHz), memory usage, disk usage, and system uptime with progress bars. If NVMe monitoring is enabled, a dropdown menu allows you to select the sensor, and your selection is saved persistently.

- **Control Section:**  
  Provides buttons to reboot or shut down your Raspberry Pi directly from the interface, with the application redirecting to the main page to prevent accidental repeated actions.

- **File Management:**  
  Browse directories, upload files (with a real-time progress bar and dynamic upload speed display), create folders, edit files, and delete files or folders. The updated interface supports bulk selection through a “select all” checkbox for faster operations.

- **Configuration:**  
  Modify admin credentials and application settings, such as the secret key, port, monitoring refresh interval, NVMe sensor display, and the Raspberry Pi configuration file location (64-bit vs. 32-bit systems). All changes are saved in `config.cfg` and persist across sessions.

- **Editing RPI config.txt:**  
  Provides an endpoint for editing the Raspberry Pi configuration file. You can choose between `/boot/firmware/config.txt` for 64-bit systems or `/boot/config.txt` for 32-bit systems as per the selected option in the configuration.

### SSH GUI

Run the text-based GUI to manage settings and service control via SSH:
```bash
sudo /home/pi/retropie_lwgmenager/gui_web_panel.sh
```
This TUI offers menus for:
- Configuring credentials (displaying current values).
- Configuring app settings (secret key, port, monitoring refresh interval, and config file location).
- Managing the service by restarting, enabling, stopping, or disabling it.
- Running the installation or uninstallation scripts.

## Customization

- **Configuration:**  
  You can directly edit the `config.cfg` file to change default settings if necessary.

- **Monitoring Refresh:**  
  The refresh interval for system metrics is configurable (minimum 0.5 seconds).

- **Service Control:**  
  The web panel provides controls to restart, enable, stop, or disable the service through both the web interface and the SSH GUI.

## Uninstallation

To uninstall the web panel, run:
```bash
sudo chmod +x uninstall.sh
sudo ./uninstall.sh
```
This script stops and disables the service, removes the systemd service file, and optionally deletes the repository folder.

## Troubleshooting Tips

- **Service Not Running:**  
  Check the service status and logs:
  ```bash
  sudo systemctl status web_panel.service
  sudo journalctl -u web_panel.service
  ```
- **Module Not Found ('flask'):**

  1. Verify your Python version:
     ```bash
     python --version
     python3 --version
     ```
     Ensure that you know whether your script is meant for Python 2 or Python 3 (most modern systems use Python 3).

  2. Install Flask using pip:
     ```bash
     sudo pip3 install flask
     ```
     (If you need Python 2, use `sudo pip install flask`.)

- **File Upload Issues:**  
  Ensure that the temporary directory exists with proper permissions:
  ```bash
  sudo mkdir -p /home/pi/tmp && sudo chmod 1777 /home/pi/tmp
  ```

## Contributing

Contributions, issues, and feature requests are welcome! Please open an issue or submit a pull request.

---

Enjoy using the RetroPie Light Web Game Manager to efficiently manage your RetroPie setup!
