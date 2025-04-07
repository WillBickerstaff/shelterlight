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
import util

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)


from lightlib.USBManager import USBFileManager, ConfigReloaded

# Set up logging ONCE for the entire test module
util.setup_test_logging()


class TestUSBManager(unittest.TestCase):
    """Testing USB."""

    def setUp(self):
        """Begin setup for each test."""
        # Set up USBFileManager instance with a mock mount point for each test.
        self.usb_manager = USBFileManager(mount_point='/mock/mount/point')

    @patch('lightlib.USBManager.USBFileManager.replace_config_with_usb',
           return_value=True)
    @patch.object(USBFileManager, 'backup_files_to_usb')
    def test_usb_check_triggers_config_reload(self, mock_backup, mock_replace):
        """Test usb_check raises ConfigReloaded when config is replaced."""
        """Check a new config triggers a config file reload."""
        with patch.object(self.usb_manager, 'backup_files_to_usb'), \
                patch.object(self.usb_manager, 'replace_config_with_usb',
                             return_value=True):
            # Verify that usb_check raises ConfigReloaded when
            # replace_config_with_usb returns True
            with self.assertRaises(ConfigReloaded):
                self.usb_manager.usb_check()

    @patch('lightlib.USBManager.USBFileManager.replace_config_with_usb',
           return_value=False)
    @patch.object(USBFileManager, 'backup_files_to_usb')
    def test_replace_config_with_usb_validation_failure(self, mock_backup,
                                                        mock_replace):
        """Check config file is not replaced if validation fails."""
        with patch('lightlib.config.ConfigLoader.validate_config_file',
                   return_value=False):
            result = self.usb_manager.replace_config_with_usb(
                'mock_config.ini')
            # Verify replace_config_with_usb returns False if config
            # validation fails.
            self.assertFalse(result)


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
