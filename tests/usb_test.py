"""tests.usb_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing for USB functionality
Author: Will Bickerstaff
Version: 0.1
"""

import unittest
import os
import sys
from unittest.mock import MagicMock, patch, mock_open
import util

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, base_path)


if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

# Set up logging ONCE for the entire test module
util.setup_test_logging()
from lightlib.USBManager import USBFileManager, ConfigReloaded


class TestUSBManager(unittest.TestCase):
    """Tests for USB operations."""

    def setUp(self):
        """Set up the test environment forcls each test case."""
        self.mount_point = os.path.join("mock", "mount", "point")
        self.usb_manager = USBFileManager(mount_point=self.mount_point)

    @patch('lightlib.USBManager.os')  # patches 'os' module in USBManager.py
    @patch('lightlib.USBManager.ConfigLoader.validate_config_file',
           return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('shutil.copy2')
    def test_config_copy(self, mock_copy2, mock_file, mock_validate, mock_os):
        """Test config copies locally."""
        mock_config = 'mock_config.ini'
        mount = os.path.join("mock", "mount", "point")
        manager = USBFileManager(mount_point=mount)
        expected_path = os.path.join(mount, mock_config)
        mock_os.path.join = os.path.join
        # Set side effect for mocked os.path.exists
        mock_os.path.exists.side_effect = \
            lambda path: os.path.normpath(path) == \
            os.path.normpath(expected_path)

        # Run test logic
        result = manager.replace_config_with_usb(mock_config)

        # Assert that the copy happened
        mock_copy2.assert_called_once_with(expected_path, 'config.ini')
        self.assertTrue(result)

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
