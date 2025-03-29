"""tests.usb_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing for USB functionality
Author: Will Bickerstaff
Version: 0.1
"""

import sys
import os
import unittest
import logging
from unittest.mock import patch


base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)
parent_path = os.path.abspath(os.path.join(base_path, '..'))
sys.path.append(base_path)
sys.path.append(parent_path)

from lightlib.USBManager import USBFileManager, ConfigReloaded


class TestUSBManager(unittest.TestCase):
    """Testing USB."""

    def setUp(self):
        """Begin setup for each test."""
        # Set up USBFileManager instance with a mock mount point for each test.
        self.default_loglevel = logging.DEBUG
        logging.basicConfig(level=self.default_loglevel)
        self.usb_manager = USBFileManager(mount_point='/mock/mount/point')

    def test_usb_check_triggers_config_reload(self):
        """Check a new config triggers a config file reload."""
        with patch.object(self.usb_manager, 'backup_files_to_usb'), \
                patch.object(self.usb_manager, 'replace_config_with_usb',
                             return_value=True):
            # Verify that usb_check raises ConfigReloaded when
            # replace_config_with_usb returns True
            with self.assertRaises(ConfigReloaded):
                self.usb_manager.usb_check()

    def test_replace_config_with_usb_validation_failure(self):
        """Check config file is not replaced if validation fails."""
        with patch('lightlib.config.ConfigLoader.validate_config_file',
                   return_value=False):
            result = self.usb_manager.replace_config_with_usb(
                'mock_config.ini')
            # Verify replace_config_with_usb returns False if config
            # validation fails.
            self.assertFalse(result)
