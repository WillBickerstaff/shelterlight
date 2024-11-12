import sys
import os
import unittest
import logging
from unittest.mock import patch, MagicMock
from lightlib.USBManager import USBFileManager, ConfigReloaded

# Adjust the import path for the test environment
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shelterlight import main_loop, usb_listener

class TestUSBManager(unittest.TestCase):
    def setUp(self):
        #Set up USBFileManager instance with a mock mount point for each test.
        self.default_loglevel = logging.DEBUG
        logging.basicConfig(level=self.default_loglevel)
        self.usb_manager = USBFileManager(mount_point='/mock/mount/point')

    def test_usb_check_triggers_config_reload(self):
        with patch.object(self.usb_manager, 'backup_files_to_usb'), \
             patch.object(self.usb_manager, 'replace_config_with_usb', return_value=True):
            # Verify that usb_check raises ConfigReloaded when replace_config_with_usb returns True
            with self.assertRaises(ConfigReloaded):
                self.usb_manager.usb_check()

    def test_replace_config_with_usb_validation_failure(self):
        with patch('lightlib.config.ConfigLoader.validate_config_file', return_value=False):
            result = self.usb_manager.replace_config_with_usb('mock_config.ini')
            #Verify replace_config_with_usb returns False if config validation fails.
            self.assertFalse(result)