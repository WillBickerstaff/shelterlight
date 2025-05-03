# Configuration Options

This document describes the configuration options used by the Bike Shelter Light Control System.

---

## USB Configuration Behaviour

If a USB device is inserted and mounted at `media_mount_point`, the following will occur:

1. **Configuration Validity Check:**

   - If a `config.ini` is found on the USB device, it will be validated. Sections and keys can be ommitted but all present must be valid. Any invalid entry will mark the entire config as invalid and defaults will be used for all settings. 

2. **Backup Existing Config & Logs:**

   - Regardless of whether the USB contains a valid `config.ini`, the system will back up the current system configuration and all log files, including rotated logs, to the USB device.

3. **Apply New Configuration (if valid):**

   - If the USB `config.ini` is valid, it will be copied to the system.

4. **Restart (if valid):**

   - If a valid configuration is found and applied, the main loop will restart to load the new configuration.

If the `config.ini` on the USB is **invalid or missing**, the system will still back up existing configuration and logs, but continue using the current configuration.

---

## Configuration & Log File Backup

When a USB device is inserted, the system will **always back up the current configuration and log files** to the USB drive, even if no config.ini is found or it is invalid.

### Backup Location

The backups will be stored in the following directories on the USB device:

- Configuration backups:
  `/media/<usb_device>/smartlight/configs/`
- Log file backups:
  `/media/<usb_device>/smartlight/logs/`

> The actual mount point is defined by the `media_mount_point` option in `[DATA_STORE]`.

---

## Default Values & Missing Options

If any configuration options are **omitted** from `config.ini`, the system will automatically use **default values** defined internally.
This ensures the system can continue to run safely even if the configuration file is incomplete.

All default values are documented in the tables below.
These defaults are hard-coded in the system source and will be used unless explicitly overridden in `config.ini`.

! If an option is incorrectly formatted, the default value will also be used and a warning will be logged.

---

## [GENERAL]

General system options.

| Option               | Type | Default            | Description                                                                     |
| -------------------- | ---- | ------------------ | ------------------------------------------------------------------------------- |
| `log_level`          | str  | `INFO`             | Logging level (e.g. `INFO`, `DEBUG`, `WARNING`).                                |
| `log_file`           | str  | `shelterlight.log` | Path to the log file.                                                           |
| `cycle_time`         | int  | `300`              | System cycle time in seconds.                                                   |
| `cancel_input`       | int  | `5`                | GPIO pin used for cancel input.                                                 |
| `confirm_input`      | int  | `6`                | GPIO pin used for confirm input.                                                |
| `sync_system_time`   | bool | `True`             | Whether to sync system time after a valid GPS fix.                              |
| `heartbeat_interval` | int  | `300`              | Interval in seconds at which heartbeat messages are logged, set to 0 for never. |

---

## [LOCATION]

Fallback location details used **only if** repeated GPS fix failures occur **and** no previously determined location is found in `persist.json`.

| Option         | Type | Default  | Description                      |
| -------------- | ---- | -------- | -------------------------------- |
| `ISO_country2` | str  | `GB`     | 2-character ISO country code.    |
| `place_name`   | str  | `London` | Location place name (e.g. city). |

---

## [GPS]

GPS module settings.

| Option               | Type  | Default        | Description                                     |
| -------------------- | ----- | -------------- | ----------------------------------------------- |
| `serial_port`        | str   | `/dev/serial0` | Serial port used by the GPS module.             |
| `baudrate`           | int   | `9600`         | Serial communication baud rate.                 |
| `timeout`            | float | `0.5`          | Timeout for serial communication.               |
| `pwr_pin`            | int   | `4`            | GPIO pin used to power the GPS module.          |
| `pwr_up_time`        | float | `2.0`          | Time (s) to wait after powering GPS before fix. |
| `fix_retry_interval` | float | `600.0`        | Interval between GPS fix attempts.              |
| `max_fix_time`       | float | `120.0`        | Max time to attempt GPS fix.                    |
| `failed_fix_days`    | int   | `14`           | Days of repeated fix failure before fault.      |
| `bypass_fix_window`  | bool  | `False`        | Allow GPS fixing at any time.                   |

**NOTE:**
The system always waits pwr_up_time after powering on the GPS before attempting to read any messages.
After that, it dynamically adjusts the start of verbose logging based on the duration of previous successful fix attempts:

This provides quiet fix attempts under normal conditions, while still offering full diagnostics if fixes take longer than usual.

---

## [IO]

Digital input/output GPIO configuration.

| Option                    | Type      | Default | Description                                                                                                                                                                       |
| ------------------------- | --------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `activity_digital_inputs` | list[int] | `17`    | Comma-separated list of GPIO pins used as activity inputs.                                                                                                                        |
| `activity_debounce`       | float     | `0.15`  | If edge detection fails these inputs switch to polling mode, debounce time is the time the input must remain in the changed state before the event will be registered.            |
| `max_activity_time`       | int       | `1800`  | Max time (s) that an activity input can remain high before fault. This has an absolute maximum limit of 32767s (9 hours 6 minutes). You can set it higher but 32767 will be used. |
| `health_check_interval`   | float     | `300`   | Interval (s) between input health checks.                                                                                                                                         |
| `lights_output`           | int       | `16`    | GPIO pin(s) used to control lighting.                                                                                                                                             |
| `fault_output`            | int       | `15`    | GPIO pin used for fault indication.                                                                                                                                               |
| `crit_fault_out`          | int       | `14`    | GPIO pin used for critical fault indication.                                                                                                                                      |
| `min_detect_on_dur`       | int       | `30`    | The minimum period in seconds that lights will switch **ON** for when activity is detected                                                                                        |

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

Determines when the system will attempt to obtain a GPS fix. The default behaviour is to attempt GPS fixes during daylight hours (when lighting control is not needed) and avoid slow GPS fixes impacting light control.

Offsets shift the window:

- **Negative value:** Shift window before sunrise/sunset.
- **Positive value:** Shift window after sunrise/sunset.

| Option           | Type | Default | Description                                |
| ---------------- | ---- | ------- | ------------------------------------------ |
| `sunrise_offset` | int  | `3600`  | Offset in seconds applied to sunrise time. |
| `sunset_offset`  | int  | `-1800` | Offset in seconds applied to sunset time.  |

Example:

```ini
[FIX_WINDOW]
sunrise_offset = 30
sunset_offset = -30
```

---

## [FLAGS]

Currently unused. Reserved for future logging or debug flag options.

| Option     | Type | Default  | Description                      |
| ---------- | ---- | -------- | -------------------------------- |
| `LOGLEVEL` | str  | *(None)* | Optional logging level override. |

---

## [DATA_STORE]

Persistent data store configuration.

This section defines where the system stores learned lighting schedules, historical GPS fixes, and other runtime data that must persist across reboots.

If a USB device is mounted at `media_mount_point`, the system will use it for storing and loading persistent data. If no device is mounted, default internal storage will be used.

The system does **not** automatically move data to the USB. The persistent store will simply point to the mounted media location **if present**.

| Option                 | Type | Default        | Description                                             |
| ---------------------- | ---- | -------------- | ------------------------------------------------------- |
| `media_mount_point`    | str  | `/media`       | Path where USB storage is mounted. Will use if present. |
| `persistent_data_JSON` | str  | `persist.json` | Filename for persistent data file (JSON format).        |

Example:

```ini
[DATA_STORE]
media_mount_point = "/media"
persistent_data_JSON = "persist.json"
```

---

## [ACTIVITY_DB]

PostgreSQL database connection settings for storing historical activity data.

| Option                | Type | Default       | Description                                  |
| --------------------- | ---- | ------------- | -------------------------------------------- |
| `host`                | str  | `localhost`   | Database hostname or IP address.             |
| `port`                | int  | `5432`        | Database port. Default is `5432`.            |
| `database`            | str  | `activity_db` | Name of the activity database.               |
| `user`                | str  | `pi`          | Database username.                           |
| `password`            | str  | `pi`          | Database password.                           |
| `connect_retry`       | int  | `5`           | Number of connection retries before failure. |
| `connect_retry_delay` | int  | `2`           | Delay in seconds between connection retries. |

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

## USB Backup of Rotated Logs

When a USB device is inserted, **all log files, including rotated and compressed logs, will be backed up to the USB drive.**

This includes files such as:

- `shelterlight.log`
- `shelterlight.log.1`
- `shelterlight.log.2.gz`

The backup files will be renamed to include an ISO-formatted timestamp:

```
/media/usb/smartlight/logs/shelterlight.log_backup_2025-03-31T14:23:07
/media/usb/smartlight/logs/shelterlight.log.1_backup_2025-03-31T14:23:07
/media/usb/smartlight/logs/shelterlight.log.2.gz_backup_2025-03-31T14:23:07
```

The backup operation is performed **once per USB insertion event.**
If the USB device is removed and re-inserted, a new backup will be created.

---
