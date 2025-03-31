# Shelter Light Control System - Setup & Configuration

---

## 🚲 Project Overview

**Shelter Light Control System** is a standalone, autonomous lighting controller designed for bicycle shelters and similar outdoor environments.
It uses a GPS module and activity detection inputs to intelligently schedule lighting during hours of darkness, based on historical activity patterns and sunrise/sunset times.

The system is designed to operate completely **offline and headless** (no display, no network), learning and adapting over time without external input.
Configuration updates and system logs can be managed via **USB device insertion**.

The system runs on a **Raspberry Pi Zero** (or similar) and is built using **Python 3.13.2** with minimal external dependencies.

---

## 🍓 Minimal Raspberry Pi Installation

The Shelter Light Control System is designed to run efficiently on a **Raspberry Pi Zero** (or similar) with a minimal, headless configuration.

### 🔥 Recommended OS

- **Raspberry Pi OS Lite (32-bit)**
  *(Debian Bookworm based, headless, no desktop)*
  Example: `2025-02-16-raspios-bookworm-armhf-lite.img`

### ⚙️ Minimal Setup Steps

1. **Flash OS Image**

   - Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or `dd` to write the OS image to your microSD card.
2. **Enable SSH (optional but recommended)**

   - Create an empty file named `ssh` in the `/boot` partition to allow remote access for debugging.
3. **Disable Unnecessary Services**

   Certain system services are not required and should be disabled to improve boot time and reduce resource usage.

   See the section **Disabling Unnecessary Services** later in this document for recommended services to disable.
4. **Install System Packages**

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip libpq-dev postgresql
   ```
5. **Optional Configuration Tweaks**

   - Disable HDMI output to save power:
     ```bash
     /usr/bin/tvservice -o
     ```

---

## 🗄️ Initial Database Setup

The Shelter Light Control System uses a **local PostgreSQL database** to store historical activity logs and generated light schedules.

### 📌 Database Configuration

Database connection settings are defined in `config.ini` under the `[ACTIVITY_DB]` section.

**Example configuration:**

```ini
[ACTIVITY_DB]
host = localhost
port = 5432
database = smartlight
user = pi
password = changeme
connect_retry = 3
connect_retry_delay = 5
```

### 🐃 Create Database & User

Run the following commands:

```bash
sudo -u postgres psql
```

Inside the `psql` shell:

```sql
CREATE DATABASE smartlight;
CREATE USER pi WITH ENCRYPTED PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE smartlight TO pi;
\q
```

### 🏐️ Create Tables

The system will automatically create the required tables (`activity_log` and `light_schedules`) when it first runs.

**Alternatively, to create manually:**

Connect to the database

```bash
psql -U pi -d smartlight
```

Paste the table creation SQL statements

```sql
-- Create activity_log table
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    day_of_week SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    year SMALLINT NOT NULL,
    duration SMALLINT NOT NULL,
    activity_pin SMALLINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_timestamp
ON activity_log (timestamp);

-- Create light_schedules table
CREATE TABLE IF NOT EXISTS light_schedules (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    interval_number SMALLINT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    prediction BOOLEAN NOT NULL,
    was_correct BOOLEAN,
    false_positive BOOLEAN DEFAULT FALSE,
    false_negative BOOLEAN DEFAULT FALSE,
    confidence DECIMAL(5,4),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_interval CHECK (interval_number >= 0 AND interval_number <= 47),
    CONSTRAINT valid_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT unique_schedule_interval UNIQUE (date, interval_number)
);

CREATE INDEX IF NOT EXISTS idx_light_schedules_date 
ON light_schedules(date);
CREATE INDEX IF NOT EXISTS idx_light_schedules_interval 
ON light_schedules(interval_number);

-- Create update trigger for updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_light_schedules_updated_at ON light_schedules;
CREATE TRIGGER update_light_schedules_updated_at
    BEFORE UPDATE ON light_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

\q

```

---

## 🔋 Python Environment Setup

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

### ⟳ Auto-Restart Behaviour

With the service configured:

```ini
Restart=on-failure
RestartSec=5
```

The service will automatically restart **5 seconds** after any unexpected failure.

---

### 📄 Logs

To view runtime logs:

```bash
journalctl -u shelterlight.service -f
```

---

### ❌ Stopping & Disabling

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

---

### ℹ️ Why this is necessary

The Raspberry Pi Zero does not have a battery-backed RTC. This system operates offline and uses GPS as the only reliable time source.

---

## 📄 Log File Management

### 🌀 Log Rotation

To prevent log files from consuming excessive disk space, it is recommended to configure **logrotate** for the shelter light log files.

This will ensure that old logs are compressed and automatically removed after a defined retention period.

---

### ⚙️ Configuration Example

Create a logrotate configuration file:

```bash
sudo nano /etc/logrotate.d/shelterlight
```

Example content:

```bash
/home/pi/shelterlight/shelterlight.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    delaycompress
    copytruncate
}
```

**Explanation:**

| Option            | Description                                           |
| ----------------- | ----------------------------------------------------- |
| `daily`         | Rotate the log file daily.                            |
| `rotate 7`      | Keep the last 7 rotated log files.                    |
| `compress`      | Compress old log files to save space.                 |
| `missingok`     | Do not raise an error if the log file is missing.     |
| `notifempty`    | Do not rotate if the log file is empty.               |
| `delaycompress` | Compress the previous log file, not the current one.  |
| `copytruncate`  | Truncate the original log file after creating a copy. |

---

### 🚀 Apply Logrotate Immediately (Optional)

You can manually force logrotate to test your configuration:

```bash
sudo logrotate -f /etc/logrotate.d/shelterlight
```

---

### 🔄 Automatic Execution

By default, logrotate runs daily via **cron** on Raspberry Pi OS.
No additional action is required after creating the config file.

---

### 💾 USB Backup of Rotated Logs

When a USB device is inserted, **all log files, including rotated and compressed logs**, will be backed up to the USB drive.
This includes:

- `shelterlight.log`
- `shelterlight.log.1`
- `shelterlight.log.2.gz`
- etc.

The backup files will be renamed to include an ISO-formatted timestamp:

```bash
/media/usb/smartlight/logs/shelterlight.log_backup_2025-03-31T14:23:07
/media/usb/smartlight/logs/shelterlight.log.1_backup_2025-03-31T14:23:07
/media/usb/smartlight/logs/shelterlight.log.2.gz_backup_2025-03-31T14:23:07
```

The backup operation happens **once per USB insertion event.**
If the USB is removed and re-inserted, a fresh backup will be created.

---

## 🚫 Disabling Unnecessary Services

To improve system performance, reduce boot time, and lower power consumption, certain default Raspberry Pi OS services can be safely disabled for this headless, offline application.

The following services are not required for the Shelter Light Control System and can be disabled:

### ⚙️ Recommended Services to Disable

| Service                | Reason                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| bluetooth.service      | Bluetooth hardware is not used.                                                              |
| hciuart.service        | Bluetooth UART service, not needed.                                                          |
| avahi-daemon.service   | mDNS/DNS-SD service (Bonjour/ZeroConf), not used.                                            |
| triggerhappy.service   | Listens for keyboard/mouse button events (special & media keys). Not needed in headless use. |
| wpa_supplicant.service | Wi-Fi service. System runs offline with no network requirement.                              |
| dhcpcd.service         | DHCP client service. No network required.                                                    |
| nfs-common.service     | Network filesystem client. Not used.                                                         |
| rpcbind.service        | RPC service for NFS, not required.                                                           |
| cups.service           | Printing service, not required.                                                              |

---

### 🛠️ Disable Services

Disable these services with:

```bash
sudo systemctl disable bluetooth.service
sudo systemctl disable hciuart.service
sudo systemctl disable avahi-daemon.service
sudo systemctl disable triggerhappy.service
sudo systemctl disable wpa_supplicant.service
sudo systemctl disable dhcpcd.service
sudo systemctl disable nfs-common.service
sudo systemctl disable rpcbind.service
sudo systemctl disable cups.service
```

If Wi-Fi or networking is required later (e.g., for debugging), to re-enable:

```bash
sudo systemctl enable wpa_supplicant.service
sudo systemctl enable dhcpcd.service
```

---

### ⚠️ Other Services to consider

| Service                 | Function                                                                                                                                                                                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| networking.service      | Configures network interfaces (mainly ethernet & static IPs). Not needed unless you plan to connect to a network regularly and want easy control.                                                                                           |
| network-manager.service | A tool for managing network connections (wired, WiFi, VPN, etc.). It handles dynamic networks, roaming, user-managed connections, etc. Not needed unless you plan to connect to a network regularly and want easy control.                  |
| ssh.service             | the SSH server (OpenSSH) allows you to remotely log in to the Pi from another machine. Disable SSH for security and simplicity. But if you want to maintain or debug the system remotely without physically accessing it, leave it enabled. |

Each of these can be disabled with:

```bash
sudo systemctl disable networking.service
sudo systemctl disable network-manager.service
sudo systemctl disable ssh.service
```

---

## 🛠️ Maintenance & Monitoring

The Shelter Light Control System is designed to run unattended. However, minimal periodic maintenance is recommended to ensure long-term reliability.

| Task                   | Frequency                        | Reason                                                      | Commands / Actions                                                                                                           |
| ---------------------- | -------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| USB Backup Retrieval   | Monthly or after unusual weather | Back up logs & configuration, and check for errors          | Insert USB and check ``/media/usb/smartlight/logs/``                                                                         |
| Log File Storage Check | Quarterly                        | Ensure log rotation is working and storage space is healthy | ``sudo du -sh /home/pi/shelterlight/*.log```<br>```sudo df -h /``                                                          |
| Database Health Check  | Every 6 months                   | Verify database integrity and storage                       | ``sudo -u postgres psql -c "\l"```<br>```psql -U pi -d smartlight -c "\dt"```<br>```du -sh /var/lib/postgresql/14/main`` |
| Hardware Inspection    | Annually / after severe weather  | Ensure cables, sensors & hardware are intact                | Visual check                                                                                                                 |
| SD Card Health         | Annually                         | SD cards wear out over time                                 | ``sudo smartctl -a /dev/mmcblk0```<br>` (Requires smartmontools)`<br>`Consider cloning the SD card                       |

---

## 🧹 Database Cleanup

Over time, the database may accumulate old activity and schedule data. It is recommended to periodically remove older records to prevent excessive disk usage.

### 🔐 Passwordless Database Access for Automation

Since the system is configured with password access, you can securely automate cleanup tasks by creating a .pgpass file:

```bash
nano /home/pi/.pgpass
```

Add the following line (match your config.ini credentials):

```
localhost:5432:smartlight:pi:changeme
```

Set the correct file permissions:

```bash
chmod 600 /home/pi/.pgpass
```

### ⏰ Automate the cleanup task using cron.

Edit the crontab for user pi:

```bash
crontab -e
```

Add the following line to remove old data monthly:

```bash
0 12 1 * * psql -U pi -d smartlight -c "DELETE FROM activity_log WHERE timestamp < NOW() - INTERVAL '90 days'; DELETE FROM light_schedules WHERE date < NOW() - INTERVAL '180 days';"
```

Activity data over 90 days old and schedules over 180 days old will be cleared out on the 1st of every month at midday.

PostgreSQL does not immediately free disk space when records are deleted. Instead, deleted rows are marked as "dead" and remain in the table until a VACUUM operation is performed.

If you want to physically reclaim disk space after cleanup:

```bash
psql -U pi -d smartlight -c "VACUUM FULL;"
```

**Note:**

Regular auto-vacuum is usually enabled by default and will handle cleanup over time.

VACUUM FULL will lock the tables until it completes, so it should only be run during maintenance periods when the service can tolerate downtime.

### 🧹 To check auto-vacuum status

Log into PostgreSQL:

```bash
psql -U pi -d smartlight
```

Then run:

```sql
SHOW autovacuum;
```

Expected result:

```markdown
 autovacuum
-------------
 on
(1 row)
```

If it says off, then autovacuum is disabled (which is rare on modern PostgreSQL). To enable, edit your postgresql.conf file (usually in /etc/postgresql/14/main/postgresql.conf or similar):

```ini
autovacuum = on
```

Then restart PostgreSQL:

```bash
sudo systemctl restart postgresql
```

---

## ⚙️ Configuration Overview

The system uses an `.ini` configuration file (`config.ini`) to control behaviour, GPIO pin assignments, database connection, location fallback, GPS settings, and more. Default values are embedded in the system and automatically used if options are missing.

Full configuration documentation is provided in **[config.readme.md](./config.readme.md)**
