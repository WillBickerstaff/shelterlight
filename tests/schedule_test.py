"""tests.schedule_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Scheduler Unit Testing
Author: Will Bickerstaff
Version: 0.1
"""

import unittest
from unittest.mock import MagicMock, patch
import datetime as dt
import pandas as pd
import numpy as np
import os
import sys
import logging
from . import util

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)

from scheduler.Schedule import LightScheduler

# Mock GPIO/serial for Raspberry Pi compatibility (import safety)
if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed


# Set up logging ONCE for the entire test module
util.setup_test_logging()


class TestLightScheduler(unittest.TestCase):
    """Unit tests for the LightScheduler class.

    This test suite verifies the functionality of the LightScheduler class,
    including schedule generation, model training, feature extraction,
    database interactions, and prediction logic. It uses mocking to isolate
    dependencies such as the database connection and model behavior.
    """

    def setUp(self):
        """Set up the test environment for each test case.

        This initializes a mocked LightScheduler instance and mocks its
        database connection, model, and methods to isolate the tests from
        external dependencies such as the actual database and model training.
        This runs before each individual test.
        """
        # Reset the singleton instance to avoid cross-test contamination
        LightScheduler._instance = None
        self.scheduler = LightScheduler()

        # Mock the database connection and prevent auto-reconnect clobbering
        self.scheduler.db = MagicMock()
        self.scheduler.db.conn.closed = False  # Ensure connection appears open

        # Clear cache to prevent side effects
        self.scheduler.schedule_cache = {}

        # Set standard values for tests
        self.scheduler.interval_minutes = 10
        self.scheduler.min_confidence = 0.6

    def test_get_schedule_from_db(self):
        """Test retrieval and return of the correct schedule data from the db.

        Verifies that the database cursor is used correctly and the fetched
        data is processed into the expected format.
        """
        # Arrange
        # Use future date to avoid clashes (today + 10 years)
        target_date = dt.date.today() + dt.timedelta(days=365 * 10)
        self.scheduler.schedule_cache = {}  # Clear cache

        # Create mock cursor and set up context manager
        mock_cursor = MagicMock()
        # Simulate 3 schedule records being fetched: [(interval, status), ...]
        mock_cursor.fetchall.return_value = [(0, 1), (1, 0), (2, 1)]
        # Mock the database connection to use the mock cursor
        self.scheduler.db.conn.cursor.return_value.__enter__.return_value = \
            mock_cursor
        # Prevent reconnection from clobbering the mock
        self.scheduler.db.conn.closed = False

        # Act & Assert -- 1st call
        # Should fetch from DB
        result = self.scheduler.get_schedule(target_date)

        # Confirm the fetched schedule is correctly processed into a dictionary
        expected = {0: 1, 1: 0, 2: 1}
        self.assertEqual(result, expected)
        # Verify that the database cursor's execute method was called
        mock_cursor.execute.assert_called_once()

        # Act & Assert -- 2nd call
        # Should fetch from cache, so no DB call
        mock_cursor.execute.reset_mock()
        # Fetch schedule again (should return from cache)
        cached_result = self.scheduler.get_schedule(target_date)
        self.assertEqual(cached_result, expected)
        # Check that no database query was made
        mock_cursor.execute.assert_not_called()

    def test_should_light_be_on_true(self):
        """Test True returned if current time matches a scheduled on time."""
        # Arrange
        # Set the test time
        now = dt.datetime(2025, 3, 20, 18, 10)  # 18:10 UTC
        # Configure scheduler with a 10 minute interval
        self.scheduler.interval_minutes = 10
        # Configure the darkness period
        self.scheduler._get_darkness_times = MagicMock(return_value=(
            dt.time(18, 0), dt.time(6, 0)
        ))
        # Mock schedule to mark interval 109 (18:10 UTC) as active (1)
        # interval_number = (hour * 60 + minute) // interval_minutes
        # For 18:10 UTC → (18 * 60 + 10) // 10 = 109
        self.scheduler.get_schedule = MagicMock(return_value={
            109: 1
        })

        # Act
        # Get the schedulers opinion on the current light status
        result = self.scheduler.should_light_be_on(current_time=now)

        # Assert
        # Confirm the scheduler required the light on
        self.assertTrue(result)

    def test_store_schedule(self):
        """Test store_schedule() correctly stores the generated schedule.

        Verifies that the database insert query is executed with the expected
        parameters.
        """
        # Arrange
        self.scheduler.interval_minutes = 10

        # Create a mock database cursor and patch it into the scheduler
        mock_cursor = MagicMock()
        self.scheduler.db.conn.cursor.return_value.__enter__.return_value = \
            mock_cursor

        # Define a test schedule date
        schedule_date = dt.date(2025, 3, 20)
        # Create mock DataFrame representing prediction intervals
        df = pd.DataFrame({'interval_number': [0, 1, 2]})
        # Predicted light status for each interval
        predictions = [1, 0, 1]

        # Act
        result = self.scheduler.store_schedule(schedule_date, df, predictions)

        # Assert
        # Verify the returned schedule dictionary matches expectations
        expected_schedule = {0: 1, 1: 0, 2: 1}
        self.assertEqual(result, expected_schedule)
        # Verify that the schedule cache is updated correctly
        self.assertEqual(
            self.scheduler.schedule_cache[schedule_date], expected_schedule)
        # Verify that a separate insert query was executed for each interval
        self.assertEqual(mock_cursor.execute.call_count, 3)

        # Verify the SQL insert query was called with the correct parameters
        # for each interval (date, interval number, start/end times,
        # and light status)
        mock_cursor.execute.assert_any_call(
            unittest.mock.ANY,
            (schedule_date, 0, dt.time(0, 0), dt.time(0, 10), 1)
        )
        mock_cursor.execute.assert_any_call(
            unittest.mock.ANY,
            (schedule_date, 1, dt.time(0, 10), dt.time(0, 20), 0)
        )
        mock_cursor.execute.assert_any_call(
            unittest.mock.ANY,
            (schedule_date, 2, dt.time(0, 20), dt.time(0, 30), 1)
        )

    def test_is_dark_within_same_day(self):
        """Test for a darkness period starting and ending in the same day.

        Verifies that the method correctly identifies if a given time is
        within the darkness period in this scenario.
        """
        # Define some darkness times
        darkness_start = dt.time(18, 0)
        darkness_end = dt.time(23, 30)

        # Time 19:00 is within darkness period, expect result = 1 (True)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(19, 0), darkness_start, darkness_end), 1)
        # Time 17:00 is before darkness period, expect result = 0 (False)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(17, 0), darkness_start, darkness_end), 0)
        # Time 23:45 is after darkness period, expect result = 0 (False)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(23, 45), darkness_start, darkness_end), 0)

    def test_is_dark_across_midnight(self):
        """Test for a darkness period that spans midnight.

        Verifies that the method correctly identifies if a given time is
        within the darkness period when it starts in the evening and ends
        the next morning.
        """
        # Darkness period: starts at 18:00, ends at 06:00 (next day)
        darkness_start = dt.time(18, 0)
        darkness_end = dt.time(6, 0)

        # Time 05:00 is within darkness period, expect 1 (True)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(5, 0), darkness_start, darkness_end), 1)
        # Time 17:00 is before darkness period, expect 0 (False)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(17, 0), darkness_start, darkness_end), 0)
        # Time 19:00 is within darkness period, expect 1 (True)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(19, 0), darkness_start, darkness_end), 1)
        # Time 07:00 is after darkness period, expect 0 (False)
        self.assertEqual(self.scheduler.is_dark(
            dt.time(7, 0), darkness_start, darkness_end), 0)

    def test_update_schedule_accuracy_executes_update(self):
        """Check for db update containing the correct schedule ID and accuracy.

        Test that the update_schedule_accuracy() method executes the database
        update query correctly with the provided schedule ID and accuracy
        value. This Verifies that the database execute method is called with
        the expected SQL query and parameters.
        """
        # Arrange: Mock DB cursor
        mock_cursor = MagicMock()
        self.scheduler.db.conn.cursor.return_value.__enter__.return_value = \
            mock_cursor

        # Create example schedule data
        target_date = dt.date(2025, 3, 20)
        schedule = {108: 1, 109: 0}  # Predicted schedule
        actual = {108: 1, 109: 1}    # Actual observed activity
        false_positive = 0
        false_negative = 1

        # Act
        self.scheduler.update_schedule_accuracy(
            target_date, schedule, actual, false_positive, false_negative)

        # Assert: Check that an UPDATE query was executed
        self.assertTrue(mock_cursor.execute.called)
        # Verify that the correct schedule date was passed in query parameters
        for call in mock_cursor.execute.call_args_list:
            self.assertIn(target_date, call[0][1])

    @patch("scheduler.Schedule.dt")
    def test_evaluate_previous_schedule_skips_future(self, mock_dt):
        """Test that evaluation is skipped for future schedules.

        Verifies that evaluate_previous_schedule() performs no evaluation or
        database update when the schedule date is in the future.
        """
        # Arrange
        now = dt.datetime.now(dt.UTC)
        mock_dt.datetime.utcnow = MagicMock(return_value=now)

        # Create a future date 10 days from now
        future_date = now + dt.timedelta(days=10)

        # Mock DB cursor to return scheduled and actual data in the future.
        # Note: In reality, actual activity cannot occur in the future.
        # This test only verifies evaluation is skipped for any future date.
        cursor = (
            self.scheduler.db.conn.cursor.return_value.__enter__.return_value)
        cursor.fetchall.side_effect = [
            [(future_date.replace(hour=18, minute=0), True)],   # Future pred
            [(future_date.replace(hour=18, minute=15), False)]  # Future actual
        ]

        # Mock update_schedule_accuracy to verify it's not called
        self.scheduler.update_schedule_accuracy = MagicMock()

        # Act:
        self.scheduler.evaluate_previous_schedule(now.date())

        # Assert: Verify update_schedule_accuracy() was not triggered
        self.scheduler.update_schedule_accuracy.assert_not_called()

    def test_get_current_schedule_returns_cached(self):
        """Ensure get_current_schedule() returns the cached schedule."""
        today = dt.date(2025, 3, 20)
        expected_schedule = {0: 1, 1: 0}  # Expected cache

        # Populate cache with today's date and expected schedule
        self.scheduler.schedule_cache = {
            'date': today,   # Ensure correct date
            'schedule': expected_schedule
        }

        # Mock db.get_schedule() to raise if called
        self.scheduler.get_schedule = MagicMock(
            side_effect=Exception(
                "Database should not be called when cache exists"))

        # Act: Retrieve the schedule
        result = self.scheduler.get_current_schedule(today)

        # Debugging Output
        logging.debug("Expected: %s", expected_schedule)
        logging.debug("Actual: %s", result)
        logging.debug("Scheduler Cache: %s", self.scheduler.schedule_cache)

        # Assert
        self.assertEqual(result, expected_schedule)
        self.scheduler.get_schedule.assert_not_called()

    def test_get_current_schedule_falls_back_to_db(self):
        """Retrieve a schedule from the db if a cached copy does not exist.

        Check the cache is populated with the schedule from the database if
        the schedule is not in the cache.
        """
        today = dt.date(2025, 3, 20)
        self.scheduler.schedule_cache = {}  # Make sure cache is empty
        # Mock get_schedule() to return a known schedule
        self.scheduler.get_schedule = MagicMock(return_value={200: 1})

        result = self.scheduler.get_current_schedule(today)
        self.assertEqual(result, {200: 1})
        self.assertEqual(self.scheduler.schedule_cache['date'], today)

    @patch("scheduler.Schedule.lgb")
    def test_train_model_calls_lgb_train(self, mock_lgb):
        """Check that lgb.train is called with training data."""
        # Mock training dataset with expected feature columns
        mock_df = pd.DataFrame({
            'activity_pin': [1, 0, 1],
            **{col: [0.1, 0.2, 0.3] for
               col in self.scheduler._get_feature_columns()}
        })
        self.scheduler._prepare_training_data = MagicMock(return_value=mock_df)

        # Mock LightGBM model and feature importance
        mock_model = MagicMock()
        mock_model.feature_importance.return_value = np.random.randint(
            1, 100, len(self.scheduler._get_feature_columns()))

        # Assign the mocked model
        mock_lgb.train.return_value = mock_model
        self.scheduler.train_model()

        # Assertions
        self.assertTrue(mock_lgb.train.called)
        self.assertTrue(mock_model.feature_importance.called)

    def test_create_prediction_features_output_shape(self):
        """Test expected feature arrays are returned."""
        timestamp = dt.datetime(2025, 3, 20, 18, 0)

        # Mock the features dictionary
        self.scheduler._generate_features_dict = MagicMock(return_value={
            'hour_sin': 0.0,
            'hour_cos': 1.0,
            'day_sin': 0.5,
            'day_cos': 0.5,
            'month_sin': 0.1,
            'month_cos': 0.9,
            'is_dark': 1,
            'rolling_activity_1h': 0.2,
            'rolling_activity_1d': 0.3,
            'interval_number': 108,
            'historical_accuracy': 0.5,
            'historical_false_positives': 0,
            'historical_false_negatives': 1,
            'historical_confidence': 0.7
        })

        features_array, features_df = \
            self.scheduler._create_prediction_features(timestamp)

        # Check returned types
        self.assertIsInstance(features_array, np.ndarray)
        self.assertIsInstance(features_df, pd.DataFrame)
        # Check array shape matches expected number of feature columns
        self.assertEqual(features_array.shape[0], len(
            self.scheduler._get_feature_columns()))
        # Ensure all expected feature columns exist in the DataFrame
        # (order-is not important)
        expected_columns = set(self.scheduler._get_feature_columns())
        actual_columns = set(features_df.columns)

        self.assertSetEqual(actual_columns, expected_columns,
                            "Mismatch in feature columns")

    def test_set_confidence_threshold_valid(self):
        """Test confidence threshold is updated when given a valid float."""
        self.scheduler.update_daily_schedule = MagicMock()
        self.scheduler.set_confidence_threshold(0.75)
        # Check confidence threshold is updated
        self.assertEqual(self.scheduler.min_confidence, 0.75)
        # Check that update_daily_schedule() was triggered
        self.scheduler.update_daily_schedule.assert_called_once()

    def test_set_confidence_threshold_invalid(self):
        """Test confidence threshold errors when given an invalid float."""
        # Threshold > 1.0 is invalid, expect a ValueError
        with self.assertRaises(ValueError):
            self.scheduler.set_confidence_threshold(1.5)

    def test_set_interval_minutes_valid(self):
        """Test interval minutes is updated when given a valid int.

        Verifies that:
            - A valid interval under 1 hour is accepted.
            - A valid interval over 1 hour is accepted.
            - update_daily_schedule() is triggered only once on first
            valid change.
        """
        # Arrange
        self.scheduler.update_daily_schedule = MagicMock()
        # Act 1st
        self.scheduler.set_interval_minutes(15)  # Under 1 hour
        # Assert 1st
        self.assertEqual(self.scheduler.interval_minutes, 15)
        # Just verify called this time
        self.scheduler.update_daily_schedule.assert_called_once()
        # Act 2nd
        self.scheduler.set_interval_minutes(75)  # Over 1 hour, still valid
        # Assert 2nd
        self.assertEqual(self.scheduler.interval_minutes, 75)
        # scheduler updated daily schedule already verified

    def test_set_interval_minutes_invalid(self):
        """Test interval minutes errors when given an invalid int."""
        # -minutes are invalid, expect a ValueError
        with self.assertRaises(ValueError):
            self.scheduler.set_interval_minutes(-5)

    def test_get_current_schedule_cached(self):
        """Test that the cached schedule is returned if it exists."""
        # Arrange
        today = dt.date.today()
        cached_schedule = {0: 1, 1: 0}
        # Pre-populate the cache with today's schedule
        self.scheduler.schedule_cache = {
            'date': today, 'schedule': cached_schedule}
        # Act
        result = self.scheduler.get_current_schedule()
        # Assert
        # Should return cached schedule
        self.assertEqual(result, cached_schedule)

    def test_update_daily_schedule_success(self):
        """Test that update_daily_schedule() completes successfully.

        Verifies that when no exceptions occur:
        - The previous schedule is evaluated.
        - The model is trained.
        - Today's schedule is generated.
        """
        # Arrange
        # Mock dependent methods to isolate test
        self.scheduler.evaluate_previous_schedule = MagicMock()
        self.scheduler.train_model = MagicMock()
        self.scheduler._get_darkness_times = MagicMock(return_value=(
            dt.time(18, 0), dt.time(6, 0)
        ))
        mock_schedule = {0: 1, 1: 0}
        self.scheduler.generate_daily_schedule = MagicMock(
            return_value=mock_schedule)

        # Act
        result = self.scheduler.update_daily_schedule()

        # Assert
        # Should return the generated schedule
        self.assertEqual(result, mock_schedule)
        # Check dependent methods were called
        self.scheduler.evaluate_previous_schedule.assert_called_once()
        self.scheduler.train_model.assert_called_once()
        self.scheduler.generate_daily_schedule.assert_called_once()

    def test_update_daily_schedule_handles_exception(self):
        """Test that update_daily_schedule() handles exceptions.

        Verifies that if an exception occurs during evaluation of the previous
        schedule, the method returns None and does not proceed to train the
        model or generate today's schedule, leaving the system running in
        reactive mode.
        """
        # Arrange
        # Force evaluate_previous_schedule() to raise an Exception
        self.scheduler.evaluate_previous_schedule = MagicMock(
            side_effect=Exception("DB failure")
        )
        self.scheduler.train_model = MagicMock()
        self.scheduler.generate_daily_schedule = MagicMock()

        # Act
        result = self.scheduler.update_daily_schedule()

        # Assert
        # Should return None if exception occurs
        self.assertIsNone(result)
        self.scheduler.evaluate_previous_schedule.assert_called_once()
        # Following methods should not be called after failure
        self.scheduler.train_model.assert_not_called()
        self.scheduler.generate_daily_schedule.assert_not_called()


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
