"""tests.activity_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing for activity
Author: Will Bickerstaff
Version: 0.1
"""

from unittest.mock import patch, MagicMock
import unittest
import sys
import os
import logging
import util
# Set up logging ONCE for the entire test module
util.setup_test_logging()


base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)

if 'RPi' not in sys.modules:
    with patch('RPi.GPIO') as MockGPIO:
        from lightlib.activitydb import Activity, PinStatus
else:
    from lightlib.activitydb import Activity, PinStatus


class TestActivity(unittest.TestCase):
    """Tests Activity functions."""

    @patch('lightlib.activitydb.ConfigLoader')
    @patch('lightlib.activitydb.DB')
    def setUp(self, mock_db_class, mock_config_loader):
        """Set up the test environment for each test case."""
        # Mock config values
        mock_config_loader.return_value.activity_digital_inputs = [17]
        mock_config_loader.return_value.max_activity_time = 60
        mock_config_loader.return_value.health_check_interval = 300

        # Stub DB connection
        self.mock_db = MagicMock()
        mock_db_class.return_value = self.mock_db

        # Reset singleton and initialize fresh Activity instance
        Activity._instance = None
        self.activity = Activity()

    def test_stub(self):
        """Placeholder test to validate test runner."""
        self.assertTrue(True)


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
