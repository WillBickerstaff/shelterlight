import os
import logging
import datetime as dt
import shutil
from typing import Optional
import RPi.GPIO as GPIO # type: ignore
from lightlib.config import ConfigLoader
from smartlight import CANCEL_CONFIRM, warn_and_wait
from common import datetime_to_iso

class USBFileManager:
    """Singleton for managing USB file operations, including backing up and
    potentially overwriting onboard configuration with a validated USB config."""

    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        """Ensure only a single instance of USBFileManager exists."""
        if cls._instance is None:
            cls._instance = super(USBFileManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, mount_point: Optional[str] = None):
        """Initialize USBFileManager with a mount point for USB drives.

        Args:
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
        try:
            self.backup_files_to_usb()
            self.replace_config_with_usb()
        except FileNotFoundError as e:
            logging.warning("USB not found or inaccessible: %s", e)

    def is_usb_inserted(self) -> bool:
        """Check if a USB drive is inserted at the mount point.

        Returns:
            bool: True if the USB drive is inserted, False otherwise.
        """
        if os.path.ismount(self.mount_point) and os.listdir(self.mount_point):
            return True
        else:
            self._backed_up = False  # Reset to allow future backups
            self._config_copied = False  # Reset to allow future overwrites
            return False  # Ensure a consistent return value

    def backup_files_to_usb(self) -> None:
        """Back up the onboard config and log files to the USB drive.

        Raises:
            FileNotFoundError: If the USB drive is not mounted or accessible.
        """
        if self._backed_up:
            return  # Skip if already backed up

        if not self.is_usb_inserted():
            raise FileNotFoundError(
                "USB drive not inserted or mount point inaccessible.")

        timestamp = datetime_to_iso(dt.datetime.now())
        usb_backup_dir = os.path.join(self.mount_point, "smartlight", "configs")
        usb_log_dir = os.path.join(self.mount_point, "smartlight", "logs")
        os.makedirs(usb_backup_dir, exist_ok=True)
        os.makedirs(usb_log_dir, exist_ok=True)

        # Backup config and log files
        config_source = "config.ini"
        config_backup = os.path.join(
            usb_backup_dir, f"config_backup_{timestamp}.ini")
        shutil.copy2(config_source, config_backup)
        logging.info("Config file backed up to USB: %s", config_backup)

        log_file = ConfigLoader().log_file
        log_backup = os.path.join(usb_log_dir, f"log_backup_{timestamp}.log")
        shutil.copy2(log_file, log_backup)
        logging.info("Log file backed up to USB: %s", log_backup)

        self._backed_up = True  # Mark as backed up

    def replace_config_with_usb(
        self, usb_config_filename: str = "usb_config.ini") -> bool:
        """Replace the onboard config with a validated USB config if not
           canceled.

        Args:
            usb_config_filename (str): Name of the config file on USB to
                                       validate and use.

        Returns:
            bool: True if USB config is successfully copied; False if canceled.
        """
        if self._config_copied:
            return True  # Skip if already copied

        usb_config_path = os.path.join(self.mount_point, usb_config_filename)

        # Check if USB drive and config file are present
        if not self.is_usb_inserted() or not os.path.isfile(usb_config_path):
            logging.warning(
                "USB drive or config file not found at %s.", usb_config_path)
            return False

        # Validate the USB configuration file
        if not ConfigLoader().validate_config_file(usb_config_path):
            logging.error("USB config file validation failed.")
            return False

        # Warn user and wait for cancellation or confirmation
        if warn_and_wait(
                message="About to overwrite onboard config. "
                        "Press cancel to abort.",
                wait_time=10,
                default_action = CANCEL_CONFIRM.CONFIRM) == \
                                 CANCEL_CONFIRM.CONFIRM:

            # Copy the validated USB config to replace onboard config
            shutil.copy2(usb_config_path, "config.ini")
            logging.info("Onboard config replaced with USB config from %s.",
                         usb_config_path)
            self._config_copied = True  # Mark as copied
            return True

        return False  # Return False if canceled