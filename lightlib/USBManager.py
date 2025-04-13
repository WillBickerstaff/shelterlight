"""lightlib.USBManager.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Manages actions for USB drive insertion & copying of config files
Author: Will Bickerstaff
Version: 0.1
"""

from lightlib.config import ConfigLoader
from lightlib.smartlight import CANCEL_CONFIRM, warn_and_wait
from lightlib.common import datetime_to_iso, ConfigReloaded

import os
import sys
import logging
import datetime as dt
import shutil
from typing import Optional

# Add paths for imports from the project directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..')))


class USBFileManager:
    """Singleton for managing USB file operations.

    including backing up and potentially overwriting onboard configuration
    with a validated USB config
    """

    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        """Ensure only a single instance of USBFileManager exists."""
        if cls._instance is None:
            cls._instance = super(USBFileManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, mount_point: Optional[str] = None):
        """Initialize USBFileManager with a mount point for USB drives.

        Args
        ----
            mount_point (Optional[str]): Path to the USB drive's mount point.
            Defaults to config value if not provided.
        """
        if not hasattr(self, "_initialized"):
            self.mount_point = mount_point or ConfigLoader().media_mount_point
            self._config_copied = False
            self._backed_up = False
            self._initialized = True  # Prevent reinitialization in singleton

    def usb_check(self) -> None:
        """Check USB, backup files, and attempt config replacement."""
        if not self.is_usb_inserted():
            # Log warning and skip if no USB inserted
            logging.warning("USB drive not inserted or inaccessible. "
                            "Skipping backup and config replacement.")
            return  # No need to proceed if USB is not inserted

        try:
            # Perform backup if USB is inserted
            self.backup_files_to_usb()

            # Check if config needs to be replaced, raise ConfigReloaded
            if self.replace_config_with_usb():
                logging.info("Configuration update detected")
                raise ConfigReloaded  # Trigger reload for valid config change
        except FileNotFoundError as e:
            # Handle case when USB is not accessible or other IO issues
            logging.warning("USB not found or inaccessible: %s", e)

    def is_usb_inserted(self) -> bool:
        """Check if a USB drive is inserted at the mount point.

        Returns
        -------
            bool: True if the USB drive is inserted, False otherwise.
        """
        if os.path.ismount(self.mount_point) and os.listdir(self.mount_point):
            logging.debug("Detected USB Insertion")
            return True
        else:
            logging.debug("No USB inserted")
            self._backed_up = False  # Reset to allow future backups
            self._config_copied = False  # Reset to allow future overwrites
            return False  # Ensure a consistent return value

    def backup_files_to_usb(self) -> None:
        """Back up the onboard config and log files to the USB drive.

        Raises
        ------
            FileNotFoundError: If the USB drive is not mounted or accessible.
        """
        if self._backed_up:
            logging.debug("Backup not required - already done.")
            return  # Skip if already backed up

        if not self.is_usb_inserted():
            raise FileNotFoundError(
                "USB drive not inserted or mount point inaccessible.")

        logging.debug("Beginning file backup to USB")
        timestamp = datetime_to_iso(dt.datetime.now())
        usb_backup_dir = os.path.join(
            self.mount_point, "smartlight", "configs")
        usb_log_dir = os.path.join(self.mount_point, "smartlight", "logs")
        os.makedirs(usb_backup_dir, exist_ok=True)
        os.makedirs(usb_log_dir, exist_ok=True)

        # Backup config and log files
        config_source = "config.ini"
        dest_filename = f"config_backup_{timestamp}.ini"
        config_backup = os.path.join(
            usb_backup_dir, dest_filename)
        logging.debug("Copying config file to %s", config_backup)
        shutil.copy2(config_source, config_backup)
        logging.info("Config file backed up to USB: %s", config_backup)

        log_file = ConfigLoader().log_file
        log_dir = os.path.dirname(log_file)
        log_base = os.path.basename(log_file)

        # Copy current log file and rotated logs
        for filename in os.listdir(log_dir):
            if filename.startswith(log_base):
                source_path = os.path.join(log_dir, filename)
                backup_name = f"{filename}_backup_{timestamp}"
                dest_path = os.path.join(usb_log_dir, backup_name)
                shutil.copy2(source_path, dest_path)
                logging.info("Log file backed up to USB: %s", dest_path)

        self._backed_up = True  # Mark as backed up

    def replace_config_with_usb(
            self, usb_config_filename: str = "smartlight_config.ini") -> bool:
        """Replace onboard config with a validated USB config if not canceled.

        This method checks for the specified configuration file on the USB
        drive, validates it, and if confirmed by the user, replaces the onboard
        configuration file with the one from the USB.

        Args
        ----
            usb_config_filename (str): Name of the config file on USB to
                                       validate and use.
                                       (default is "smartlight_config.ini").

        Returns
        -------
            bool: True if the USB config file is successfully validated and
                  copied. False otherwise.
        """
        # Return True if already copied (assume we are trying to trigger a
        # reload)
        if self._config_copied:
            return True  # Skip if already copied

        usb_config_path = os.path.join(self.mount_point, usb_config_filename)

        # Check if the USB is inserted and contains the specified config file
        if not self.is_usb_inserted() or not os.path.isfile(usb_config_path):
            logging.warning(
                "USB drive or config file not found at %s.", usb_config_path)
            return False

        # Validate the configuration file format and content
        if not ConfigLoader().validate_config_file(usb_config_path):
            logging.error("USB config file validation failed.")
            return False

        # Prompt user for confirmation to overwrite onboard config
        user_choice = warn_and_wait(
            message="Onboard config will be replaced in 10s. "
            "Press cancel to abort. Overwriting",
            wait_time=10,
            default_action=CANCEL_CONFIRM.CONFIRM)

        if user_choice == CANCEL_CONFIRM.CONFIRM:
            # User confirmed, copy the validated USB config to replace onboard
            shutil.copy2(usb_config_path, "config.ini")
            logging.info(
                "Onboard config successfully replaced with "
                "USB config from %s.",
                usb_config_path)
            self._config_copied = True  # Mark as copied to avoid re-copying
            return True

        # Operation was canceled by the user
        logging.info("Configuration replacement canceled by user.")
        return False
