# ⚙️ Configuration Options

This document describes the configuration options used by the Bike Shelter Light Control System.

---

## USB Configuration Behaviour

If a USB device is inserted and mounted at `media_mount_point`, the following will occur:

1. **Configuration Validity Check:**
   - If a `config.ini` is found at the root of the USB device, it will be validated.

2. **Backup Existing Config:**
   - If valid, the system will backup the current system configuration:

3. **Copy Log Files:**
   - All log files will be copied to the USB device.

4. **Apply New Configuration:**
   - The validated `config.ini` from the USB will be copied to the system.

5. **Restart:**
   - The main loop will be restarted to load the new configuration.

If the `config.ini` on the USB is **invalid**, the system will log a warning and continue using the current configuration.

---

🔄 Configuration & Log File Backup

When a valid config.ini is found on an inserted USB device, the system will back up the current configuration and log files to the USB drive before applying the new configuration.

📂 Backup Location

The backups will be stored in the following directories on the USB device:

Configuration backups:/media/<usb_device>/smartlight/configs/

Log file backups:/media/<usb_device>/smartlight/logs/

⚠️ The actual mount point is defined by the media_mount_point option in [DATA_STORE].

📝 Backup File Names

Backups will include an ISO-formatted timestamp to ensure uniqueness:

Config File:config_backup_<timestamp>.ini

Log File:log_backup_<timestamp>.log

Example:

/media/usb/smartlight/configs/config_backup_2025-03-31T14:23:07.ini
/media/usb/smartlight/logs/log_backup_2025-03-31T14:23:07.log

The backup operation is only performed once per USB insertion event.If the USB device is removed and re-inserted, the backup will occur again if a valid config is present.

---

## [GENERAL]

General system options.

| Option           | Type  | Description                                              |
|------------------|:----:|----------------------------------------------------------|
| `log_level`     | str   | Logging level (e.g. `INFO`, `DEBUG`, `WARNING`).         |
| `log_file`      | str   | Path to the log file.                                    |
| `cycle_time`    | int   | System cycle time in seconds.                           |
| `cancel_input`  | int   | GPIO pin used for cancel input.                         |
| `confirm_input` | int   | GPIO pin used for confirm input.                        |
| `sync_system_time` | bool | Whether to sync system time after a valid GPS fix.    |

---

## [LOCATION]

Fallback location details used **only if** repeated GPS fix failures occur **and** no previously determined location is found in `persist.json`.

| Option           | Type  | Description                                     |
|------------------|:----:|-------------------------------------------------|
| `ISO_country2`  | str   | 2-character ISO country code.                  |
| `place_name`    | str   | Location place name (e.g. city).               |

If the system cannot establish location from GPS or persistent data, it will fall back to these values.

---

## [GPS]

GPS module settings.

| Option               | Type   | Description                                      |
|---------------------|:-----:|--------------------------------------------------|
| `serial_port`      | str    | Serial port used by the GPS module.             |
| `baudrate`         | int    | Serial communication baud rate.                 |
| `timeout`          | float  | Timeout for serial communication.               |
| `pwr_pin`          | int    | GPIO pin used to power the GPS module.          |
| `pwr_up_time`      | float  | Time (s) to wait after powering GPS before fix. |
| `fix_retry_interval`| float  | Interval between GPS fix attempts.              |
| `max_fix_time`     | float  | Max time to attempt GPS fix.                    |
| `failed_fix_days`  | int    | Days of repeated fix failure before fault.      |

---

## [IO]

Digital input/output GPIO configuration.

| Option                   | Type       | Description                                                        |
|-------------------------|:---------:|--------------------------------------------------------------------|
| `activity_digital_inputs`| list[int] | Comma-separated list of GPIO pins used as activity inputs.        |
| `max_activity_time`     | int       | Max time (s) that an activity input can remain high before fault. |
| `health_check_interval` | float     | Interval (s) between input health checks.                         |
| `lights_output`         | int       | GPIO pin(s) used to control lighting.                             |
| `fault_output`          | int       | GPIO pin used for fault indication.                               |
| `crit_fault_out`        | int       | GPIO pin used for critical fault indication.                      |

Example:

```ini
[IO]
activity_digital_inputs = 17, 18, 27, 22
max_activity_time = 1200
health_check_interval = 300
lights_output = 16
fault_output = 15
crit_fault_out = 14
```

---

## [FIX_WINDOW]

Determines when the system will attempt to obtain a GPS fix.
The default behaviour is to attempt GPS fixes during daylight hours (when lighting control is not needed) and avoid slow GPS fixes impacting light control.

Offsets shift the window:
- **Negative value:** Shift window before sunrise/sunset.
- **Positive value:** Shift window after sunrise/sunset.

| Option          | Type | Description                                      |
|---------------|:---:|--------------------------------------------------|
| `sunrise_offset` | int | Offset in seconds applied to sunrise time.      |
| `sunset_offset`  | int | Offset in seconds applied to sunset time.       |

Example:
```ini
[FIX_WINDOW]
sunrise_offset = 30
sunset_offset = -30
```

---

## [FLAGS]

Currently unused. Reserved for future logging or debug flag options.

| Option   | Type | Description                   |
|--------|:---:|-------------------------------|
| `LOGLEVEL` | str | Optional logging level override. |

---

## [DATA_STORE]

Persistent data store configuration.

This section defines where the system stores learned lighting schedules, historical GPS fixes, and other runtime data that must persist across reboots.

If a USB device is mounted at `media_mount_point`, the system will use it for storing and loading persistent data.
If no device is mounted, default internal storage will be used.

The system does **not** automatically move data to the USB. The persistent store will simply point to the mounted media location **if present**.

| Option                 | Type | Description                                                         |
|-----------------------|:---:|---------------------------------------------------------------------|
| `media_mount_point`   | str | Path where USB storage is mounted. Will use if present.             |
| `persistent_data_JSON`| str | Filename for persistent data file (JSON format).                    |

Example:
```ini
[DATA_STORE]
media_mount_point = "/media"
persistent_data_JSON = "persist.json"
```

---

## [ACTIVITY_DB]

PostgreSQL database connection settings for storing historical activity data.

| Option               | Type | Description                                             |
|--------------------|:---:|---------------------------------------------------------|
| `host`            | str  | Database hostname or IP address.                       |
| `port`            | int  | Database port. Default is `5432`.                      |
| `database`        | str  | Name of the activity database.                         |
| `user`            | str  | Database username.                                     |
| `password`        | str  | Database password.                                     |
| `connect_retry`   | int  | Number of connection retries before failure.           |
| `connect_retry_delay`| int | Delay in seconds between connection retries.           |

Example:
```ini
[ACTIVITY_DB]
host = "localhost"
port = 5432
database = "activity_db"
user = "pi"
password = "pi"
connect_retry = 5
connect_retry_delay = 2
```

---

