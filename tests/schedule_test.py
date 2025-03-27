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

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)
parent_path = os.path.abspath(os.path.join(base_path, '..'))
sys.path.append(base_path)
sys.path.append(parent_path)

from scheduler.Schedule import LightScheduler

# Mock GPIO/serial for Raspberry Pi compatibility (import safety)
if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed


class TestLightScheduler(unittest.TestCase):

    def setUp(self):
        self.scheduler = LightScheduler()
        
        # Create a mock database connection and ensure `.conn.closed` is False
        mock_conn = MagicMock()
        mock_conn.closed = False
        self.scheduler.db = MagicMock()
        self.scheduler.db.conn = mock_conn
    
        # General scheduler settings
        self.scheduler.interval_minutes = 10
        self.scheduler.min_confidence = 0.6
    
        # Logging config (once only to avoid repeated handlers)
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s [%(levelname)s] %(message)s",
                handlers=[
                    logging.FileHandler("test_output.log", mode='a'),
                    logging.StreamHandler()
                ]
            )

    def test_get_schedule_from_db(self):
        # Arrange
        target_date = dt.date(2025, 3, 20)
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(0, 1), (1, 0), (2, 1)]

        self.scheduler.db.conn.cursor.return_value = mock_cursor

        # Act
        result = self.scheduler.get_schedule(target_date)

        # Assert
        expected = {0: 1, 1: 0, 2: 1}
        self.assertEqual(result, expected)
        self.scheduler.db.conn.cursor.assert_called()
        mock_cursor.execute.assert_called_with(
            """
                    SELECT interval_number, prediction
                    FROM light_schedules
                    WHERE date = %s
                """, (target_date,)
        )

    def test_should_light_be_on_true(self):
        # Arrange
        now = dt.datetime(2025, 3, 20, 18, 10)  # 18:10 UTC
        self.scheduler.interval_minutes = 10
        self.scheduler._get_darkness_times = MagicMock(return_value=(
            dt.time(18, 0), dt.time(6, 0)
        ))
        self.scheduler.get_schedule = MagicMock(return_value={
            109: 1  # 18:10 falls into interval 109
        })

        # Act
        result = self.scheduler.should_light_be_on(current_time=now)

        # Assert
        self.assertTrue(result)

    def test_store_schedule(self):
        # Arrange
        self.scheduler.interval_minutes = 10
    
        mock_cursor = MagicMock()
        self.scheduler.db.conn.cursor.return_value.__enter__.return_value = mock_cursor
    
        schedule_date = dt.date(2025, 3, 20)
        df = pd.DataFrame({'interval_number': [0, 1, 2]})
        predictions = [1, 0, 1]
    
        # Act
        result = self.scheduler.store_schedule(schedule_date, df, predictions)
    
        # Assert
        expected_schedule = {0: 1, 1: 0, 2: 1}
        self.assertEqual(result, expected_schedule)
        self.assertEqual(self.scheduler.schedule_cache[schedule_date], expected_schedule)
        self.assertEqual(mock_cursor.execute.call_count, 3)
    
        # Check individual SQL calls
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
        darkness_start = dt.time(18, 0)
        darkness_end = dt.time(23, 59)

        self.assertEqual(self.scheduler.is_dark(dt.time(19, 0), darkness_start, darkness_end), 1)
        self.assertEqual(self.scheduler.is_dark(dt.time(17, 0), darkness_start, darkness_end), 0)

    def test_is_dark_across_midnight(self):
        darkness_start = dt.time(18, 0)
        darkness_end = dt.time(6, 0)

        self.assertEqual(self.scheduler.is_dark(dt.time(5, 0), darkness_start, darkness_end), 1)
        self.assertEqual(self.scheduler.is_dark(dt.time(17, 0), darkness_start, darkness_end), 0)

    def test_update_schedule_accuracy_executes_update(self):
        mock_cursor = MagicMock()
        self.scheduler.db.conn.cursor.return_value.__enter__.return_value = mock_cursor

        self.scheduler.update_schedule_accuracy(
            date=dt.date(2025, 3, 20),
            interval_number=108,
            was_correct=True,
            false_positive=False,
            false_negative=False
        )

        self.assertTrue(mock_cursor.execute.called)
        args = mock_cursor.execute.call_args[0]
        self.assertIn("UPDATE light_schedules", args[0])
        self.assertEqual(args[1][1], 108)

    @patch("scheduler.Schedule.dt")
    def test_evaluate_previous_schedule_skips_future(self, mock_dt):
        now = dt.datetime(2025, 3, 20, 12, 0)
        mock_dt.datetime.utcnow = MagicMock(return_value=now)

        self.scheduler.db.conn.cursor.return_value.__enter__.return_value.fetchall.side_effect = [
            [(100, dt.time(20, 0), dt.time(21, 0), 1)],  # Schedule in future
            []  # No activity
        ]

        self.scheduler.update_schedule_accuracy = MagicMock()

        self.scheduler.evaluate_previous_schedule(now.date())
        self.scheduler.update_schedule_accuracy.assert_not_called()

    def test_get_current_schedule_returns_cached(self):
        """Ensure get_current_schedule() returns the cached schedule."""
    
        today = dt.date(2025, 3, 20)
        expected_schedule = {0: 1, 1: 0}  # Expected cache
    
        # Ensure the cache has the correct structure
        self.scheduler.schedule_cache = {
            'date': today,   # Ensure correct date
            'schedule': expected_schedule
        }
    
        # Act: Call get_current_schedule()
        result = self.scheduler.get_current_schedule()
    
        # Debugging Output
        logging.debug("Expected:", expected_schedule)
        logging.debug("Actual:", result)
        logging.debug("Scheduler Cache:", self.scheduler.schedule_cache)
    
        # Assert
        self.assertEqual(result, expected_schedule)


    def test_get_current_schedule_falls_back_to_db(self):
        today = dt.date(2025, 3, 20)
        self.scheduler.schedule_cache = {}
        self.scheduler.get_schedule = MagicMock(return_value={200: 1})

        result = self.scheduler.get_current_schedule(today)
        self.assertEqual(result, {200: 1})
        self.assertEqual(self.scheduler.schedule_cache['date'], today)

    @patch("scheduler.Schedule.lgb")
    def test_train_model_calls_lgb_train(self, mock_lgb):
        # Mock training dataset
        mock_df = pd.DataFrame({
            'activity_pin': [1, 0, 1],
            **{col: [0.1, 0.2, 0.3] for col in self.scheduler._get_feature_columns()}
        })
        self.scheduler._prepare_training_data = MagicMock(return_value=mock_df)
    
        # Mock LightGBM model and feature importance
        mock_model = MagicMock()
        mock_model.feature_importance.return_value = np.random.randint(1, 100, len(self.scheduler._get_feature_columns()))
    
        # Assign the mocked model
        mock_lgb.train.return_value = mock_model
        self.scheduler.train_model()
    
        # Assertions
        self.assertTrue(mock_lgb.train.called)
        self.assertTrue(mock_model.feature_importance.called)

    def test_create_prediction_features_output_shape(self):
        timestamp = dt.datetime(2025, 3, 20, 18, 0)

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

        features_array, features_df = self.scheduler._create_prediction_features(timestamp)

        self.assertIsInstance(features_array, np.ndarray)
        self.assertEqual(features_array.shape[0], len(self.scheduler._get_feature_columns()))
        self.assertIsInstance(features_df, pd.DataFrame)
        # Ensure all expected feature columns exist in the DataFrame
        # (order-is not important)
        expected_columns = set(self.scheduler._get_feature_columns())
        actual_columns = set(features_df.columns)
        
        self.assertSetEqual(actual_columns, expected_columns,
                            "Mismatch in feature columns")

    def test_set_confidence_threshold_valid(self):
        self.scheduler.update_daily_schedule = MagicMock()
        self.scheduler.set_confidence_threshold(0.75)
        self.assertEqual(self.scheduler.min_confidence, 0.75)
        self.scheduler.update_daily_schedule.assert_called_once()
    
    def test_set_confidence_threshold_invalid(self):
        with self.assertRaises(ValueError):
            self.scheduler.set_confidence_threshold(1.5)
    
    def test_set_interval_minutes_valid(self):
        self.scheduler.update_daily_schedule = MagicMock()
        self.scheduler.set_interval_minutes(15)
        self.assertEqual(self.scheduler.interval_minutes, 15)
        self.scheduler.update_daily_schedule.assert_called_once()

    def test_set_interval_minutes_invalid(self):
        with self.assertRaises(ValueError):
            self.scheduler.set_interval_minutes(-5)
    
    def test_get_current_schedule_cached(self):
        today = dt.date.today()
        cached_schedule = {0: 1, 1: 0}
        self.scheduler.schedule_cache = {'date': today, 'schedule': cached_schedule}
        result = self.scheduler.get_current_schedule()
        self.assertEqual(result, cached_schedule)
    
    def test_get_current_schedule_not_cached(self):
        today = dt.date.today()
        db_schedule = {0: 1, 1: 0}
        self.scheduler.schedule_cache = {}
    
        self.scheduler.get_schedule = MagicMock(return_value=db_schedule)
        result = self.scheduler.get_current_schedule()
        self.assertEqual(result, db_schedule)
        self.assertEqual(self.scheduler.schedule_cache['date'], today)

    def test_update_daily_schedule_success(self):
        # Arrange
        self.scheduler.evaluate_previous_schedule = MagicMock()
        self.scheduler.train_model = MagicMock()
        self.scheduler._get_darkness_times = MagicMock(return_value=(
            dt.time(18, 0), dt.time(6, 0)
        ))
        mock_schedule = {0: 1, 1: 0}
        self.scheduler.generate_daily_schedule = MagicMock(return_value=mock_schedule)
    
        # Act
        result = self.scheduler.update_daily_schedule()
    
        # Assert
        self.assertEqual(result, mock_schedule)
        self.scheduler.evaluate_previous_schedule.assert_called_once()
        self.scheduler.train_model.assert_called_once()
        self.scheduler.generate_daily_schedule.assert_called_once()
    
    def test_update_daily_schedule_handles_exception(self):
        # Arrange
        self.scheduler.evaluate_previous_schedule = MagicMock(
            side_effect=Exception("DB failure")
        )
        self.scheduler.train_model = MagicMock()
        self.scheduler.generate_daily_schedule = MagicMock()
    
        # Act
        result = self.scheduler.update_daily_schedule()
    
        # Assert
        self.assertIsNone(result)
        self.scheduler.evaluate_previous_schedule.assert_called_once()
        # Following methods should not be called after failure
        self.scheduler.train_model.assert_not_called()
        self.scheduler.generate_daily_schedule.assert_not_called()


    def test_update_daily_schedule_triggers_store_schedule(self):
        # Arrange
        mock_schedule = {0: 1, 1: 0}
        self.scheduler.evaluate_previous_schedule = MagicMock()
        self.scheduler.train_model = MagicMock()
        self.scheduler._get_darkness_times = MagicMock(return_value=(
            dt.time(18, 0), dt.time(6, 0)
        ))
    
        # Patch store_schedule inside generate_daily_schedule
        with patch.object(self.scheduler, 'generate_daily_schedule',
                          return_value=mock_schedule) as mock_generate:
            # Act
            result = self.scheduler.update_daily_schedule()
    
            # Assert
            mock_generate.assert_called_once()
            self.assertEqual(result, mock_schedule)
            self.assertEqual(self.scheduler.schedule_cache['schedule'], mock_schedule)
    
    def test_generate_daily_schedule_model_missing(self):
        # Arrange
        self.scheduler.model = None  # Simulate no trained model
    
        # Act
        result = self.scheduler.generate_daily_schedule(
            "2025-03-20", "18:00", "06:00"
        )
    
        # Assert
        self.assertEqual(result, {})
