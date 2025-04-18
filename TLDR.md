# TLDR

1.  **Flash the OS**

    Using  Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or `dd`

2. **Enable SSH (optional but recommended)**

   Create an empty file named `ssh` in the `/boot` partition to allow remote access for debugging.

3.  **Boot your Raspberry Pi**

## Set the Timezone

```bash
sudo raspi-config
```
Choose **Localisation Options** -> **Timezone**. At the bottom of the list of available timezones the option *'None of the above'* exists, choose this and then **'UTC'**

## Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libpq-dev postgresql libopenblas-dev git
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
python3 -m venv venv
source venv/bin/activate
```

**Install Dependencies**

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
ExecStart=/home/pi/shelterlight/venv/bin/python /home/pi/shelterlight/shelterlight.py
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

```bash
chmod 600 /home/pi/.pgpass
```

**Automate the cleanup task using cron.**

Edit the crontab for user pi:

```bash
crontab -e
```

Add the following line to remove old data monthly:

```bash
0 12 1 * * psql -U pi -d smartlight -c "DELETE FROM activity_log WHERE timestamp < NOW() - INTERVAL '90 days'; DELETE FROM light_schedules WHERE date < NOW() - INTERVAL '180 days';"
```
