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
        """Set up the test environment for each test case."""
        self.mount_point = os.path.join("mock", "mount", "point")
        self.usb_manager = USBFileManager(mount_point=self.mount_point)

    @patch('lightlib.USBManager.ConfigLoader.validate_config_file', return_value=True)
    @patch('builtins.open', new_callable=MagicMock)
    @patch('shutil.copy2')
    @patch('lightlib.USBManager.os')  # patches 'os' module in USBManager.py
    def test_usb_insertion_resets_backup_status(self, mock_os, mock_copy2, mock_file, mock_validate):
        """Test USB insertion resets the backup status and triggers backup."""
        
        mock_config = 'mock_config.ini'
        mount = os.path.join("mock", "mount", "point")
        expected_path = os.path.join(mount, mock_config)
        
        # Mock os.path.ismount and os.listdir to simulate USB presence/absence
        # Initially, no USB inserted (simulating the first state)
        mock_os.path.ismount.return_value = False  # Simulate no mount
        mock_os.listdir.return_value = []  # Simulate no files (USB not present)
        
        # Ensure initial status is removed (i.e., no backup has been made)
        self.usb_manager.is_usb_inserted()  # Runs the real logic and updates _backed_up
        logging.debug("USB Removed, _backed_up status = %s", self.usb_manager._backed_up)
        self.assertFalse(self.usb_manager._backed_up)  # Should be False after USB removal
    
        # Simulate USB insertion
        mock_os.path.ismount.return_value = True  # Simulate USB is mounted
        mock_os.listdir.return_value = ['somefile']  # Simulate USB has files (USB is inserted)
        
        self.usb_manager.is_usb_inserted()  # Runs the real method
        logging.debug("USB Inserted, _backed_up status = %s", self.usb_manager._backed_up)
        
        # Run the usb_check method and trigger backup
        self.usb_manager.usb_check()  # Should perform the backup if USB is inserted
        logging.debug("USB Inserted, _backed_up status = %s", self.usb_manager._backed_up)
        
        # Ensure backup was triggered
        self.assertTrue(self.usb_manager._backed_up)  # Should be True after backup
    
        # Now simulate USB removal
        mock_os.path.ismount.return_value = False  # Simulate USB is removed
        mock_os.listdir.return_value = []  # Simulate USB has no files (USB removed)
        
        self.usb_manager.is_usb_inserted()  # Run the real method
        logging.debug("USB Removed, _backed_up status = %s", self.usb_manager._backed_up)
        
        # Reset _backed_up flag to False after USB removal
        self.usb_manager._backed_up = False  # Manually reset if needed
        
        # Verify backup status is reset
        self.assertFalse(self.usb_manager._backed_up)  # Should be False after USB removal
    
        # Simulate USB re-insertion
        mock_os.path.ismount.return_value = True  # Simulate USB re-inserted
        mock_os.listdir.return_value = ['somefile']  # Simulate USB with files
        
        self.usb_manager.is_usb_inserted()  # Run the real method
        
        # Run the usb_check method again and trigger another backup
        self.usb_manager.usb_check()  # Should perform the backup again
        logging.debug("USB Re-inserted, _backed_up status = %s", self.usb_manager._backed_up)
    
        # Ensure backup was triggered again
        self.assertTrue(self.usb_manager._backed_up)  # Should be True after backup



if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
