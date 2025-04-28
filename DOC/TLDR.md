# TLDR

> *last updated for: **Raspberry Pi OS Bookworm (2025)** — Kernel 6.1.x*

1.  **Flash the OS**

    Using  Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or `dd`
    - **Raspberry Pi OS Lite**

2. **Enable SSH (optional but recommended)**

   Create an empty file named `ssh` in the `/boot` partition to allow remote access for debugging. or once booted through `sudo raspi-config` **Advanced Options** -> **SSH**

3.  **Boot your Raspberry Pi**

4.  **Expand the filesystem**
    `sudo raspi-config` **Advanced Options** -> **Expand Filesystem** Confirm & `sudo reboot`

## Set the Timezone

```bash
sudo raspi-config
```
Choose **Localisation Options** -> **Timezone**. At the bottom of the list of available timezones the option *'None of the above'* exists, choose this and then **'UTC'**

## Enable Hardware Serial
```bash
sudo raspi-config
```
Choose **Interface Options** -> **I6 Serial Port**, choose **"NO"** when asked if you would like a login shell accessible over serial and **"YES"** when asked if you would like serial port hardware to be enabled

**RPi Zero**

Disable Bluetooth

```bash
sudo nano /boot/firmware/config.txt
```

add `dtoverlay=disable-bt` to the end of the file

## Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-lgpio python3-dev libpq-dev postgresql libopenblas-dev build-essential git
```

---

## Setup the Database

**Create the database and user**
```bash
sudo -u postgres psql
```

Inside the `psql` shell:

```sql
CREATE DATABASE activity_db;
CREATE USER pi WITH ENCRYPTED PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE activity_db TO pi;

\c activity_db
GRANT USAGE ON SCHEMA public TO pi;
GRANT CREATE ON SCHEMA public TO pi;
\q
```

**Edit config.ini**

Change the database settings to match above

```ini
[ACTIVITY_DB]
host = localhost
port = 5432
database = activity_db
user = pi
password = changeme
connect_retry = 3
connect_retry_delay = 5
```

---

## Setup the python environment

**Grab the source**

Grab the source for the application from the git repository with:
```bash
git clone https://WillBickerstaff/shelterlight
```

**Virtual environment**

Create and activate a virtual environment

```bash
cd ~/shelterlight
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

**Install Dependencies**

First numpy
```bash
pip install --prefer-binary numpy
```

Then the remaining dependencies:

```bash
pip install -r req_modules.txt
```

---

## Setup systemd

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
ExecStart=/home/pi/shelterlight/.venv/bin/python /home/pi/shelterlight/shelterlight.py
WorkingDirectory=/home/pi/shelterlight
Restart=on-failure
RestartSec=5
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
```

**Enable & Start the Service**

Run the following commands to enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable shelterlight.service
sudo systemctl start shelterlight.service
sudo systemctl status shelterlight.service
```

---

## Log File Management

**Log Rotation**

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
---

### Apply Logrotate Immediately (Optional)

You can manually force logrotate to test your configuration:

```bash
sudo logrotate -f /etc/logrotate.d/shelterlight
```

---

## Database Cleanup

**Configure passwordless Database Access**

```bash
nano /home/pi/.pgpass
```

Add the following line (match your config.ini credentials):

```
localhost:5432:smartlight:pi:changeme
```

Set the correct file permissions:

**Automate the cleanup task using cron.**

Edit the crontab for user pi:

```bash
crontab -e
```

Add the following line to remove old data monthly:

```bash
0 12 1 * * psql -U pi -d activity_db -c  "DELETE FROM activity_log WHERE timestamp < NOW() - INTERVAL '90 days'; DELETE FROM light_schedules WHERE date < NOW() - INTERVAL '180 days';"
```
