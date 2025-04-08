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
import logging
import util
# Set up logging ONCE for the entire test module
util.setup_test_logging()

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, base_path)

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

from lightlib.USBManager import USBFileManager, ConfigReloaded


class TestUSBManager(unittest.TestCase):
    """Tests for USB operations."""

    def setUp(self):
        """Set up the test environment forcls each test case."""
        self.mount_point = os.path.join("mock", "mount", "point")
        self.usb_manager = USBFileManager(mount_point=self.mount_point)

    def tearDown(self):
        """Ensure logging handlers are flushed after each test."""
        for handler in logging.getLogger().handlers:
            handler.flush()  # Make sure log entries are written

    @patch('lightlib.USBManager.os')  # patches 'os' module in USBManager.py
    @patch('lightlib.USBManager.ConfigLoader.validate_config_file',
           return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('shutil.copy2')
    def test_config_copy(self, mock_copy2, mock_file, mock_validate, mock_os):
        """Test config copies locally."""
        mock_config = 'mock_config.ini'
        expected_path = os.path.join(self.mount_point, mock_config)
        mock_os.path.join = os.path.join
        # Set side effect for mocked os.path.exists
        mock_os.path.exists.side_effect = \
            lambda path: os.path.normpath(path) == \
            os.path.normpath(expected_path)

        # Run test logic
        result = self.usb_manager.replace_config_with_usb(mock_config)

        # Assert that the copy happened
        mock_copy2.assert_called_once_with(expected_path, 'config.ini')
        self.assertTrue(result)

    @patch('lightlib.USBManager.datetime_to_iso',
           return_value="2025-04-08T122218")
    @patch.object(USBFileManager, 'replace_config_with_usb', return_value=True)
    @patch('lightlib.USBManager.os.path.ismount', return_value=True)
    @patch('lightlib.USBManager.os.listdir', return_value=["mockfile"])
    def test_usb_check_triggers_config_reload(
            self, mock_listdir, mock_ismount, mock_replace, mock_datetime):
        """Test usb_check raises ConfigReloaded when config is replaced."""
        try:
            """Check a new config triggers a config file reload."""
            with self.assertRaises(ConfigReloaded):
                self.usb_manager.usb_check()

            # Check config replacement happened and ConfigReloaded was raised
            mock_replace.assert_called_once()
        except ConfigReloaded:
            logging.info("Config reloaded as expected.")

    @patch('lightlib.USBManager.USBFileManager.replace_config_with_usb',
           return_value=False)
    @patch.object(USBFileManager, 'backup_files_to_usb')
    def test_replace_config_with_usb_validation_failure(self, mock_backup,
                                                        mock_replace):
        """Check config file is not replaced if validation fails."""
        logging.debug("Logging is working here 1")
        with patch('lightlib.config.ConfigLoader.validate_config_file',
                   return_value=False):
            result = self.usb_manager.replace_config_with_usb(
                'mock_config.ini')
            # Verify replace_config_with_usb returns False if config
            # validation fails.
            self.assertFalse(result)

    @patch('lightlib.USBManager.os')  # patches 'os' module in USBManager.py
    @patch('lightlib.USBManager.ConfigLoader.validate_config_file',
           return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('shutil.copy2')
    @patch('lightlib.USBManager.datetime_to_iso')  # Mocking datetime_to_iso
    def test_backup_files_to_usb_copies_expected_files(
            self, mock_datetime, mock_copy2, mock_file,
            mock_validate, mock_os):
        """Test backup files to USB copies expected files."""
        mock_config = 'mock_config.ini'
        expected_path = os.path.join(self.mount_point, mock_config)

        # Mock datetime_to_iso to return a fixed timestamp for testing
        mock_datetime.return_value = "2025-04-07T00:00:00Z"

        # Mock os.path.join to return the expected path as a string
        mock_os.path.join.side_effect = \
            lambda *args: os.path.normpath(os.path.join(*args))

        # Set side effect for mocked os.path.exists
        mock_os.path.exists.side_effect = \
            lambda path: os.path.normpath(path) == \
            os.path.normpath(expected_path)

        # USBManager backup status should be false
        self.assertFalse(self.usb_manager._backed_up)
        # Run test logic
        config_backup_path = os.path.join(
            self.mount_point, "smartlight", "configs",
            "config_backup_2025-04-07T00:00:00Z.ini")
        logging.debug(f"Expected backup path: {config_backup_path}")
        self.usb_manager.backup_files_to_usb()

        # Match the call to mock_copy2 with the correct timestamp
        mock_copy2.assert_any_call("config.ini", config_backup_path)

        # Ensure that _backed-up is now True
        self.assertTrue(self.usb_manager._backed_up)

    @patch.object(USBFileManager, 'replace_config_with_usb',
                  return_value=False)
    @patch.object(USBFileManager, 'backup_files_to_usb')  # Verified elsewhere
    @patch('lightlib.USBManager.os.path.ismount')
    @patch('lightlib.USBManager.os.listdir')
    def test_backup_occurs_on_each_usb_insertion(
            self, mock_listdir, mock_ismount, mock_backup, mock_replace):
        """Test backup triggered on each USB insertion."""
        # Simulate the sequence: Not Inserted, Inserted, Removed, Inserted
        usb_states = [False, True, False, True]

        def ismount_side_effect(_):
            return usb_states.pop(0)

        def listdir_side_effect(_):
            # If last ismount was True, return content; else []
            return ["dummy_file"] if mock_ismount.return_value else []

        mock_ismount.side_effect = ismount_side_effect
        mock_listdir.side_effect = listdir_side_effect

        for i in range(4):
            logging.debug(f"USB Check #{i + 1}")
            self.usb_manager.usb_check()

        # Backup should have been called twice.
        self.assertEqual(mock_backup.call_count, 2)


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
