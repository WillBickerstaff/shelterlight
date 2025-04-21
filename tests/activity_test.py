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

# Patch lgpio if running on non-RPi platforms
try:
    import lgpio
except ImportError:
    from tests.RPi import lgpio as fake_lgpio
    sys.modules['lgpio'] = fake_lgpio

from lightlib.activitydb import Activity, PinLevel, PinHealth
from lightlib.common import valid_smallint

class TestActivity(unittest.TestCase):
    """Tests Activity functions."""

    @patch('lightlib.activitydb.ConfigLoader')
    @patch('lightlib.activitydb.DB')
    def setUp(self, mock_db_class, mock_config_loader):
        """Set up the test environment for each test case."""
        self.test_pin = 11
        # Mock config values
        mock_config_loader.return_value.activity_digital_inputs = \
            [self.test_pin]
        mock_config_loader.return_value.max_activity_time = 60
        mock_config_loader.return_value.health_check_interval = 300

        # Stub DB connection
        self.mock_db = MagicMock()
        mock_db_class.return_value = self.mock_db
        mock_db_class.valid_smallint = valid_smallint

        # Reset singleton and initialize fresh Activity
        Activity._instance = None
        self.activity = Activity()

    def test_start_activity_event_sets_state_and_status(self):
        """_start_activity_event should set pin HIGH & status to OK."""
        self.activity._start_activity_event(self.test_pin)

        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["state"], PinLevel.HIGH)
        self.assertEqual(pin_status["status"], PinHealth.OK)
        self.assertIn(self.test_pin, self.activity._start_times)

    def test_end_activity_event_logs_valid_activity(self):
        """_end_activity_event should log activity and reset pin state."""
        start_time = dt.datetime.now(dt.timezone.utc) - \
            dt.timedelta(seconds=10)
        self.activity._start_times[self.test_pin] = start_time

        self.activity._end_activity_event(self.test_pin)

        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["status"], PinHealth.OK)
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertNotIn(self.test_pin, self.activity._start_times)
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

    def test_pin_fault_detection(self):
        """Test long detection marks FAULT & auto clears on falling edge."""
        threshold = self.activity._fault_threshold

        # Simulate a long HIGH to trigger fault
        self.activity._start_times[self.test_pin] = (
            dt.datetime.now(dt.timezone.utc) -
            dt.timedelta(seconds=threshold + 5))
        self.activity._pin_status[self.test_pin]["state"] = PinLevel.HIGH

        # First fault check (should set FAULT)
        logging.debug("1st Fault check")
        self.activity._run_fault_check_cycle()
        self.assertEqual(
            self.activity._pin_status[self.test_pin]["status"],
            PinHealth.FAULT,
            "Pin should be marked FAULT due to prolonged HIGH signal."
        )
        logging.debug("Pin correctly set FAULT")

        logging.debug("Setting pin edge low to trigger _end_activity_event")
        # Call _end_activity_event to simulate falling edge
        self.activity._end_activity_event(self.test_pin)

        # Should now be OK
        self.assertEqual(
            self.activity._pin_status[self.test_pin]["status"],
            PinHealth.OK,
            "Pin should reset to OK after falling edge."
        )
        logging.debug("Pin correctly set OK")
        self.assertEqual(
            self.activity._pin_status[self.test_pin]["state"],
            PinLevel.LOW,
            "Pin state should be LOW after falling edge."
        )
        logging.debug("Pin State is LOW")

        # 2nd fault check (should set OK)
        logging.debug("2nd Fault check")
        self.activity._run_fault_check_cycle()
        self.assertEqual(
            self.activity._pin_status[self.test_pin]["status"],
            PinHealth.OK,
            "Pin should be marked OK due to LOW signal."
        )
        logging.debug("Pin correctly set FAULT")
        logging.debug("** Pin successfully cleared fault on falling edge **")

    def test_end_activity_event_handles_excessive_duration(self):
        """_end_activity_event skips database if duration exceeds SMALLINT."""
        # Set start time beyond the 32767-second limit
        self.activity._fault_threshold = 99999
        sub_time = 32768
        self.activity._start_times[self.test_pin] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=sub_time)
        )
        self.activity._pin_status[self.test_pin]["state"] = PinLevel.HIGH
        self.activity._pin_status[self.test_pin]["status"] = PinHealth.FAULT
        logging.debug("Pin %i forced to FAULT with duration %is (invalid)",
                      self.test_pin, sub_time)

        # Patch the logger to verify error message
        with self.assertLogs(level="DEBUG") as log:
            self.activity._end_activity_event(self.test_pin)

        # Should NOT call query() due to duration error
        self.mock_db.query.assert_not_called()
        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertEqual(pin_status["status"], PinHealth.OK)
        logging.debug("Pin status correctly reset\n\t\tState: %s\tStatus: %s",
                      self.activity._pin_status[self.test_pin]["state"].name,
                      self.activity._pin_status[self.test_pin]["status"].name)

        # Should log an appropriate error message
        self.assertTrue(any(
            "duration must be <=" in message
            for message in log.output
        ))

        log_summary = "\n".join(log.output)
        logging.debug("Captured logs:\n%s", log_summary)

    def test_end_activity_event_accepts_max_valid_smallint(self):
        """_end_activity_event should log duration of 32767 seconds."""
        self.activity._fault_threshold = 99999
        duration = 32767  # Max allowed SMALLINT value
        start_time = dt.datetime.now(dt.timezone.utc) - \
            dt.timedelta(seconds=duration)
        self.activity._start_times[self.test_pin] = start_time
        self.activity._pin_status[self.test_pin]["state"] = PinLevel.HIGH
        self.activity._pin_status[self.test_pin]["status"] = PinHealth.OK

        logging.debug("Pin %i set with duration %is (valid)",
                      self.test_pin, duration)

        # Patch the logger to verify error message
        with self.assertLogs(level="DEBUG") as log:
            self.activity._end_activity_event(self.test_pin)

        # Should attempt to insert into DB
        self.mock_db.query.assert_called_once()
        logging.debug("Database query was called")

        # Check that start_time was removed
        self.assertNotIn(self.test_pin, self.activity._start_times)

        # Pin state and status should still be cleared
        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertEqual(pin_status["status"], PinHealth.OK)

        log_summary = "\n".join(log.output)
        logging.debug("Captured logs:\n%s", log_summary)

    def test_end_activity_event_skips_if_no_start_time(self):
        """_end_activity_event should skip logging if start time is missing."""
        # Simulate no start time
        self.activity._start_times = {}  # ensure it's not present
        self.activity._pin_status[self.test_pin]["state"] = PinLevel.HIGH
        self.activity._pin_status[self.test_pin]["status"] = PinHealth.FAULT

        with self.assertLogs(level="WARNING") as log:
            self.activity._end_activity_event(self.test_pin)

        # DB should not be called
        self.mock_db.query.assert_not_called()

        # Confirm warning was logged
        self.assertTrue(any(
            "No start time found for pin" in message
            for message in log.output
        ))

        # State should still be LOW and OK (recovery behavior)
        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertEqual(pin_status["status"], PinHealth.OK)

        log_summary = "\n".join(log.output)
        logging.debug("Captured logs:\n%s", log_summary)

    def test_end_activity_event_skips_log_if_dur_is_gt_config_threshold(self):
        """Should skip logging if duration exceeds config max_activity_time."""
        self.activity._fault_threshold = 1200
        logging.debug("Fault threshold set to %s",
                      self.activity._fault_threshold)
        # Exceed the patched threshold
        duration = self.activity._fault_threshold + 1

        self.activity._start_times[self.test_pin] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=duration)
        )
        self.activity._pin_status[self.test_pin]["state"] = PinLevel.HIGH
        self.activity._pin_status[self.test_pin]["status"] = PinHealth.FAULT

        with self.assertLogs(level="WARNING") as log:
            self.activity._end_activity_event(self.test_pin)

        self.mock_db.query.assert_not_called()

        pin_status = self.activity._pin_status[self.test_pin]
        self.assertEqual(pin_status["state"], PinLevel.LOW)
        self.assertEqual(pin_status["status"], PinHealth.OK)

        self.assertTrue(any(
            "exceeded max_activity_time" in msg
            for msg in log.output
        ))

        logging.debug("Exceeded max_activity_time threshold; "
                      "log skipped as expected.")

    def test_multiple_pins_independent_states(self):
        """Each pin should retain and update independent status/state."""
        # Initial combinations for setup
        initial_combinations = [
            (PinHealth.OK, PinLevel.HIGH),
            (PinHealth.OK, PinLevel.LOW),
            (PinHealth.FAULT, PinLevel.HIGH),
            (PinHealth.FAULT, PinLevel.LOW)]

        # New combinations to update to after first verification
        updated_combinations = [
            (PinHealth.FAULT, PinLevel.LOW),
            (PinHealth.FAULT, PinLevel.HIGH),
            (PinHealth.OK, PinLevel.LOW),
            (PinHealth.OK, PinLevel.HIGH)]

        # Generate pin numbers for each test case
        pin_base = 17
        pins = [pin_base + i for i in range(len(initial_combinations))]

        # Assign initial states
        for pin, (health, level) in zip(pins, initial_combinations):
            self.activity._pin_status[pin] = {"status": health, "state": level}
            logging.debug(
                "Initially set Pin %i => Status: %s, State: %s",
                pin, health.name, level.name)

        # Verify initial states
        for pin, (expected_status, expected_state) in zip(
                pins, initial_combinations):
            with self.subTest(phase="initial", pin=pin):
                result = self.activity.get_pin_status(pin)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["state"], expected_state)
                logging.debug(
                    "Verified (initial) Pin %i => Status: %s, State: %s",
                    pin, result["status"].name, result["state"].name)

        # Update states
        for pin, (new_status, new_state) in zip(pins, updated_combinations):
            self.activity._pin_status[pin]["status"] = new_status
            self.activity._pin_status[pin]["state"] = new_state
            logging.debug(
                "Updated Pin %i => Status: %s, State: %s",
                pin, new_status.name, new_state.name)

        # Verify updated states
        for pin, (expected_status, expected_state) in zip(
                pins, updated_combinations):
            with self.subTest(phase="updated", pin=pin):
                result = self.activity.get_pin_status(pin)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["state"], expected_state)
                logging.debug(
                    "Verified (updated) Pin %i => Status: %s, State: %s",
                    pin, result["status"].name, result["state"].name)

if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
