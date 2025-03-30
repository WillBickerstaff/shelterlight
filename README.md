# Shelter Light Control System - Setup & Configuration

---

## ✨ USB Configuration Behaviour

When a USB device is inserted and mounted at `media_mount_point`, the following will occur:

1. **Configuration Validity Check:**

   - If a `config.ini` is found on the USB device, it will be validated.

2. **Backup Existing Config & Logs:**

   - Regardless of whether the USB contains a valid `config.ini`, the system will back up the current system configuration and logs to the USB device.

3. **Apply New Configuration (if valid):**

   - If the USB `config.ini` is valid, it will be copied to the system.

4. **Restart (if valid):**

   - If a valid configuration is found and applied, the main loop will restart to load the new configuration.

If the `config.ini` on the USB is **invalid or missing**, the system will still back up existing configuration and logs, but continue using the current configuration.

#### For a detailed description of backup operation, configuration options and behaviour see [config.readme.md](./config.readme.md)

---

## 📂 Python Environment Setup

This system is written in **Python 3.13.2** and is intended to run on Raspberry Pi Zero (or similar).

### 🔥 Required Python Libraries

The following Python packages are required:

- `RPi.GPIO` — Raspberry Pi GPIO control
- `pyserial` — Serial communication for GPS module
- `lightgbm` — Machine learning for schedule prediction
- `psycopg2` — PostgreSQL database driver
- `pandas` — Data manipulation
- `numpy` — Numerical operations

A complete list is provided in `req_modules.txt`:

```
RPi.GPIO
pyserial
lightgbm
psycopg2
pandas
numpy
```

---

### ✅ Installation

To avoid affecting your system Python environment, it is recommended to install dependencies in a **virtual environment**.

#### 1. Create & Activate Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

#### 2. Install Dependencies

```bash
pip install -r req_modules.txt
```

---

## 🚀 Running as a Systemd Service

This system is configured to run automatically at boot using **systemd**.

### 🗂️ Service File

Create a new systemd service file:

```bash
sudo nano /etc/systemd/system/shelterlight.service
```

Paste the following content:

```ini
[Unit]
Description=Shelter Light Controller
After=network.target

[Service]
ExecStart=/home/pi/shelterlight/venv/bin/python /home/pi/shelterlight/shelterlight.py
WorkingDirectory=/home/pi/shelterlight
Restart=on-failure
RestartSec=5
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
```

---

### ⚙️ Enable & Start the Service

Run the following commands to enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable shelterlight.service
sudo systemctl start shelterlight.service
sudo systemctl status shelterlight.service
```

---

### 🔄 Auto-Restart Behaviour

The service is configured with:

```ini
Restart=on-failure
RestartSec=5
```

This means the service will automatically restart **5 seconds** after any unexpected failure.

---

### 📄 Logs

To view runtime logs:

```bash
journalctl -u shelterlight.service -f
```

---

### ⛔️ Stopping & Disabling

```bash
sudo systemctl stop shelterlight.service
sudo systemctl disable shelterlight.service
```

---

### ℹ️ Notes

- The service requires access to GPIO and USB devices.
- Make sure all hardware components are connected before starting the service.
- If using **System Time Sync from GPS**, ensure appropriate `sudoers` permissions.

---

## 🕒 System Time Synchronisation

The system uses the GPS module as the authoritative time source. After a successful fix, the system clock is updated to GPS-provided **UTC time**.

### ✨ How it works

After a valid fix, the system executes:

```bash
sudo /bin/date -s <utc_time>
```

This will synchronise the Raspberry Pi system time to UTC.

### 🔒 Permissions & Security

Setting system time requires **sudo** privileges.

1. **Create a sudoers rule:**
    ```bash
    sudo visudo -f /etc/sudoers.d/shelterlight
    ```
    Add:
    ```
    pi ALL=(ALL) NOPASSWD: /bin/date
    ```

2. **Disable NTP (Optional)**
    ```bash
    sudo timedatectl set-ntp false
    ```

### ℹ️ Why this is necessary

The Raspberry Pi Zero does not have a battery-backed RTC. This system operates offline and uses GPS as the only reliable time source.

---
