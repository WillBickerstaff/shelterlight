import unittest
import os
import sys
from unittest.mock import MagicMock, patch, mock_open
import util

# Set up logging ONCE for the entire test module
util.setup_test_logging()

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

from lightlib.USBManager import USBFileManager

class MinimalUSBTest(unittest.TestCase):
    @patch('lightlib.USBManager.os')  # ← this patches the 'os' module used in USBManager.py
    @patch('lightlib.USBManager.ConfigLoader.validate_config_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('shutil.copy2')
    def test_config_copy(self, mock_copy2, mock_file, mock_validate, mock_os):  # ← this is where 'mock_os' comes from
        mock_config = 'mock_config.ini'
        mount = os.path.join("mock", "mount", "point")
        manager = USBFileManager(mount_point=mount)
        expected_path = os.path.join(mount, mock_config)
        mock_os.path.join = os.path.join
        # Set side effect for mocked os.path.exists
        mock_os.path.exists.side_effect = lambda path: os.path.normpath(path) == os.path.normpath(expected_path)

        # Run test logic
        result = manager.replace_config_with_usb(mock_config)

        # Assert that the copy happened
        mock_copy2.assert_called_once_with(expected_path, 'config.ini')
        self.assertTrue(result)

if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
