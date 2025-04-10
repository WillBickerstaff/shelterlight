"""tests.activity_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing for activity
Author: Will Bickerstaff
Version: 0.1
"""

from unittest.mock import patch, MagicMock
import datetime as dt
import unittest
import sys
import os
import logging
import types
import util
# Set up logging ONCE for the entire test module
util.setup_test_logging()


base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)

if 'RPi' not in sys.modules:
    from RPi.GPIO import GPIO
    sys.modules['RPi'] = types.ModuleType('RPi')
    sys.modules['RPi.GPIO'] = GPIO
    sys.modules['RPi'].GPIO = GPIO

from lightlib.activitydb import Activity, PinLevel, PinHealth
from lightlib.db import valid_smallint


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
        mock_db_class.valid_smallint = valid_smallint

        # Reset singleton and initialize fresh Activity instance
        Activity._instance = None
        self.activity = Activity()

    def test_start_activity_event_sets_state_and_status(self):
        """_start_activity_event should set pin HIGH & status to OK."""
        test_pin = 17
        self.activity._start_activity_event(test_pin)

        pin_status = self.activity._pin_status[test_pin]
        self.assertEqual(pin_status["state"], PinLevel.HIGH)
        self.assertEqual(pin_status["status"], PinHealth.OK)
        self.assertIn(test_pin, self.activity._start_times)

    def test_end_activity_event_logs_valid_activity(self):
        """_end_activity_event should log activity and reset pin state."""
        test_pin = 17
        start_time = dt.datetime.now(dt.timezone.utc) - \
            dt.timedelta(seconds=10)
        self.activity._start_times[test_pin] = start_time

        self.activity._end_activity_event(test_pin)

        pin_status = self.activity._pin_status[test_pin]
        self.assertEqual(pin_status["status"], PinHealth.OK)
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertNotIn(test_pin, self.activity._start_times)
        self.assertTrue(self.mock_db.query.called)

        call = self.mock_db.query.call_args
        if call:
            _, kwargs = call
            sql = kwargs.get("query", "<No query key>")
            params = kwargs.get("params", "<No params>")
            logging.debug("SQL that would have been executed:\n"
                          "%s\nwith parameters: %s", sql, params)
        else:
            logging.debug("mock_db.query was never called.")


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
