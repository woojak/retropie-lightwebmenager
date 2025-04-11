Poniżej znajdziesz zaktualizowany opis (README) repozytorium, który został dostosowany do aktualnego skryptu `web_panel.py`. Tekst zawiera szczegółowy opis funkcji, zawartości repozytorium, kroków instalacji, sposobu użycia oraz sekcję dotyczącą rozwiązywania problemów. Możesz go bezpośrednio skopiować do pliku README.md w swoim repozytorium na GitHub.

```markdown
# RetroPie Light Web Game Manager

This repository contains a full-featured web panel for managing your RetroPie file system, monitoring system performance, and controlling your Raspberry Pi. The web interface is built using Python and Flask and includes persistent configuration storage, system control options (such as reboot/shutdown), file management with bulk selection (including a "select all" feature), and a text-based SSH GUI for changing settings and managing the service.

## Repository Contents

- **web_panel.py**  
  The main Python Flask application that provides:
  - **File and directory management:**  
    Browse directories, upload files (with a real-time progress bar), create folders, edit files, and delete files/folders. The file management section now includes bulk selection with a “select all” checkbox for managing multiple files at once.
  - **System monitoring:**  
    Displays live system statistics such as CPU temperature, CPU usage, memory usage, disk usage, and system uptime with visual progress bars.
  - **NVMe sensor selection:**  
    If enabled in the configuration, allows you to select an NVMe sensor and monitor its temperature. Your selection is saved persistently.
  - **System control functions:**  
    Reboot or shutdown your Raspberry Pi directly via the web interface.
  - **Configuration management:**  
    Edit application settings (admin credentials, secret key, port, monitoring refresh interval, and NVMe sensor display) via a dedicated settings page.
  - **Editing RPI config.txt:**  
    Provides an endpoint for modifying `/boot/firmware/config.txt`.

- **config.cfg**  
  A configuration file that stores persistent settings, including:
  - Admin credentials (login and password)
  - Secret key
  - Port number
  - Monitoring refresh interval
  - NVMe sensor selection and display setting

- **web_panel.service**  
  A systemd service file that runs the Flask application on startup.

- **install.sh**  
  An installation script that automates:
  - Updating packages and installing dependencies.
  - Creating a temporary directory with the correct permissions.
  - Cloning (or updating) the repository.
  - Setting executable permissions for project files.
  - Installing the systemd service, enabling it to start at boot, and starting the service immediately.

- **uninstall.sh**  
  An uninstallation script that stops and disables the web panel service and optionally deletes the repository folder.

- **gui_web_panel.sh**  
  A text-based graphical (TUI) script (using whiptail) for managing settings and service control via SSH. It offers submenus for:
  - Configuring credentials (login & password)
  - Configuring app settings (secret key, port, and monitoring refresh interval)
  - Managing the service (restart, enable, disable)
  - Running the install or uninstall scripts

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
- Reload systemd, enable the service for auto-start at boot, and start the service immediately.

### 3. Verify the Service

Check the service status with:
```bash
sudo systemctl status web_panel.service
```
If issues occur, review logs with:
```bash
sudo journalctl -u web_panel.service
```

## Usage and Operation

### Web Interface

Access the web panel by navigating to your Raspberry Pi’s IP address and the configured port (default is 5000) in your browser. The web interface includes:

- **Monitoring Section:**  
  Displays live system statistics including CPU temperature, CPU usage, memory usage, disk usage, and system uptime using progress bars. If NVMe monitoring is enabled, a dropdown menu allows you to select the sensor, and your selection is saved.

- **Control Section:**  
  Provides buttons to reboot or shutdown your Raspberry Pi directly from the interface.

- **File Management:**  
  Browse directories, upload files with a real-time progress bar, create folders, edit files, and delete files or folders. The updated file management interface supports bulk selection via a "select all" checkbox for quicker operations.

- **Configuration:**  
  Modify admin credentials and app settings, such as the secret key, port, and monitoring refresh interval. All changes are saved in `config.cfg` and persist across sessions.

### SSH GUI

Run the text-based GUI to manage settings and service control via SSH:
```bash
sudo /home/pi/retropie_lwgmenager/gui_web_panel.sh
```
This TUI offers menus for:
- Configuring credentials (displaying current values).
- Configuring app settings (secret key, port, and monitoring refresh interval).
- Managing the service by restarting, enabling, or disabling it.
- Running the install or uninstall scripts.

## Customization

- **Configuration:**  
  You can directly edit the `config.cfg` file to change default settings if necessary.

- **Monitoring Refresh:**  
  The refresh interval for system metrics is configurable (minimum 0.5 seconds).

- **Service Control:**  
  The web panel provides controls to restart, enable, or disable the service through both the web interface and the SSH GUI.

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

- **File Upload Issues:**  
  Ensure that the temporary directory exists with proper permissions:
  ```bash
  sudo mkdir -p /home/pi/tmp && sudo chmod 1777 /home/pi/tmp
  ```

## Contributing

Contributions, issues, and feature requests are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.



Enjoy using the RetroPie Light Web Game Manager to efficiently manage your RetroPie setup!


