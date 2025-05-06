"""scheduler.features.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Feature engineering for light scheduling predictions, including
             time encoding, darkness classification, historical accuracy
             embedding, and activity trend analysis.

Author: Will Bickerstaff
Version: 0.1
"""
import logging
import datetime as dt
import pandas as pd
import numpy as np
from lightlib.persist import PersistentData
from lightlib.common import get_today, get_tomorrow, get_now
from scheduler.base import SchedulerComponent


class FeatureEngineer(SchedulerComponent):
    """Generate time-based, environmental & historical features for scheduling.

    This class is responsible for:
    - Generating cyclical time features (hour/day/month)
    - Assessing whether a given time falls within darkness hours
    - Retrieving rolling activity history from the database
    - Embedding historical scheduling performance metrics
    - Providing structured feature vectors for model training and prediction

    It supports both batch feature creation (for training) and
    single-timestamp vectorization (for prediction or debugging).

    Inherits from SchedulerComponent to gain access to shared config,
    such as the database connection, schedule interval, and cache.
    """

    def __init__(self):
        super().__init__()  # Ensure base SchedulerComponent config works
        self._warned_missing = None

    def _generate_features_dict(self, timestamp: dt.datetime) -> dict:
        """Generate feature values for a timestamp.

        Args
        ----
            timestamp (dt.datetime): The timestamp to generate features for.

        -Extracts time-based features (hour, day of week, month).
        -Converts these into cyclical features (`sin/cos` encoding).
        -Determines whether the timestamp falls within darkness hours.
        -Retrieves historical schedule accuracy features for this interval.
        -Computes rolling activity features for short- and long-term trends.

        Returns
        -------
            dict: A dictionary of extracted feature values.
        """
        # Extract time components
        hour = timestamp.hour
        minute = timestamp.minute
        day_of_week = timestamp.weekday()
        month = timestamp.month

        # Create cyclical time features
        #    sin(2pi * value/max_value)
        #    cos(2pi * value/max_value)

        # - Hours (24-hour cycle)
        # - hour_sin, hour_cos (24-hour cycle)
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)

        # - Days of week (7-day cycle)
        # - day_sin, day_cos (7-day cycle)
        day_sin = np.sin(2 * np.pi * day_of_week / 7)
        day_cos = np.cos(2 * np.pi * day_of_week / 7)

        # - Months (12-month cycle)
        # - month_sin, month_cos (12-month cycle)
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)

        # Calculate interval number
        interval_number = (hour * 60 + minute) // self.interval_minutes

        # Retrieve historical accuracy features (default if missing)
        history = self._get_cached_schedule_entry(
            timestamp.date(), interval_number)
        historical_accuracy = history.get(
            "historical_accuracy", 0.5)
        historical_false_positives = history.get(
            "historical_false_positives", 0)
        historical_false_negatives = history.get(
            "historical_false_negatives", 0)
        historical_confidence = history.get(
            "historical_confidence", 0.5)

        # Compute rolling activity features
        past_activity = self._retrieve_past_activity(
            timestamp.date(), interval_number)

        # Compute rolling activity features
        if len(past_activity) >= 6:
            rolling_activity_1h = np.mean(past_activity[-6:])  # Last hour
        else:
            rolling_activity_1h = 0

        if past_activity:
            rolling_activity_1d = np.mean(past_activity)       # Last 24 hours
        else:
            rolling_activity_1d = 0

        # Construct full dictionary of all available features
        feature_values = {
            "hour_sin": hour_sin, "hour_cos": hour_cos,
            "day_sin": day_sin, "day_cos": day_cos,
            "month_sin": month_sin, "month_cos": month_cos,
            "rolling_activity_1h": rolling_activity_1h,
            "rolling_activity_1d": rolling_activity_1d,
            "interval_number": interval_number,
            "historical_accuracy": historical_accuracy,
            "historical_false_positives": historical_false_positives,
            "historical_false_negatives": historical_false_negatives,
            "historical_confidence": historical_confidence
        }

        # Only return the features needed by the model.
        # _get_feature_columns() lists the features the model uses.
        # This lets us:
        # - Control which features are used in one place
        # - Try out new features here without affecting the model
        # - Keep training and prediction using the same inputs
        return {
            key: feature_values[key] for key in self._get_feature_columns()}

    def _get_feature_columns(self) -> list[str]:
        """Return the list of features used by the model.

        These are the columns the model uses when training and making
        predictions. Any other features that are calculated will be ignored.

        Returns
        -------
            list[str]: The names of the features the model expects.
        """
        return [
            'hour_sin', 'hour_cos',        # Hour encoding
            'month_sin', 'month_cos',      # Seasonal encoding
            'day_sin', 'day_cos',          # Weekly pattern encoding
            'rolling_activity_1h',         # Short-term activity trend
            'rolling_activity_1d',         # Long-term activity trend
            'interval_number',             # Time interval index
            'historical_accuracy',         # Past scheduling success rate
            'historical_false_positives',  # Past over-predictions
            'historical_false_negatives',  # Past under-predictions
            'historical_confidence'        # Average confidence in past
                                           # schedules
        ]

    def _create_base_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add training features.

        - Daily patterns (through hour encoding)
        - Weekly patterns (through day_of_week encoding)
        - Seasonal patterns (through month encoding)
        - Recent activity patterns (through rolling averages)
        """
        # Apply the shared feature function to all timestamps
        feature_dicts = df['timestamp'].apply(self._generate_features_dict)

        # Convert the list of feature dictionaries into a DataFrame
        features_df = pd.DataFrame(feature_dicts.tolist(), index=df.index)

        # Merge the features back into the original dataset
        df = pd.concat([df, features_df], axis=1)

        logging.info("Activity data processed successfully")
        return df

    def _create_prediction_features(
            self, timestamp: dt.datetime) -> tuple[np.ndarray, pd.DataFrame]:
        """Create a feature vector for a single timestamp.

        Args
        ----
            timestamp (dt.datetime): The timestamp to generate features for.

        Returns
        -------
            tuple[np.ndarray, pd.DataFrame]:
                - NumPy array of feature values for model inference.
                - DataFrame with named columns for debugging or model training.
        """
        feature_dict = self._generate_features_dict(timestamp)

        # Ensure expected features match the generated features
        expected_features = set(self._get_feature_columns())
        generated_features = set(feature_dict.keys())

        if expected_features != generated_features:
            missing = expected_features - generated_features
            extra = generated_features - expected_features
            raise ValueError(
                f"Feature mismatch!\nMissing: {missing}\nExtra: {extra}"
            )

        # Convert dictionary to NumPy array (for prediction)
        # Keep in order for testing
        feature_values = np.array(
            [feature_dict[f] for f in expected_features])

        # Convert dictionary to DataFrame (for debugging/training)
        # Keep in order for testing
        feature_df = pd.DataFrame([feature_dict],
                                  columns=sorted(list(expected_features)))

        logging.debug(f"Generated features: {feature_dict}")
        logging.debug(f"Feature array shape: {feature_values.shape}")
        logging.debug(f"Expected features: {self._get_feature_columns()}")

        return feature_values, feature_df

    def _retrieve_past_activity(self, date: dt.date, interval_number: int,
                                history_days: int = 1) -> list[int]:
        """Retrieve activity for a specific interval over previous days.

        Args
        ----
            date (dt.date): The date for which to retrieve past activity.
            interval_number (int): The interval number on that date.
            history_days (int): How many previous days to include.

        Returns
        -------
            list[int]: A list of activity values (0 or 1) for the interval over
                       the past `history_days`.
        """
        if self.db is None or self.db.conn.closed:
            self.set_db_connection()
            if self.db is None:
                logging.error("No DB connection for _retrieve_past_activity")
                return []

        try:
            # Get start and end timestamps for each historical interval
            results = []
            for days_ago in range(1, history_days + 1):
                historical_date = date - dt.timedelta(days=days_ago)
                base_time = dt.datetime.combine(
                    historical_date, dt.time(0, 0), tzinfo=dt.timezone.utc)
                start_time = base_time + dt.timedelta(
                    minutes=interval_number * self.interval_minutes)
                end_time = start_time + dt.timedelta(
                    minutes=self.interval_minutes)

                with self.db.conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM activity_log
                        WHERE timestamp >= %s AND timestamp < %s
                    """, (start_time, end_time))

                    count = cursor.fetchone()[0]
                    results.append(1 if count > 0 else 0)

            return results

        except Exception as e:
            logging.error("Failed to retrieve past activity: %s", e)
            return []

    def _get_cached_schedule_entry(self, date: dt.date, interval: int) -> dict:
        """Retrieve a cached schedule entry for a given date and interval.

        Args
        ----
            date (dt.date): The date to look up.
            interval (int): The interval number within the date.

        Returns
        -------
            dict: Cached schedule data for the interval, or empty dict if
                  missing.
        """
        return self.schedule_cache.get(str(date), {}).get(interval, {})
