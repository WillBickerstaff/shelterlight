"""scheduler.schedule.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate daily schedules
Author: Will Bickerstaff
Version: 0.1
"""

from threading import Lock
from lightlib.persist import PersistentData
from lightlib.db import DB
from typing import Optional
import psycopg2
import pandas as pd
import numpy as np
import lightgbm as lgb  # https://lightgbm.readthedocs.io/en/stable/
import datetime as dt
import logging


class LightScheduler:
    """
    A Singleton class that manages light scheduling using machine learning.

    This class uses LightGBM to learn patterns from historical activity data
    and generate optimal lighting schedules. It implements the Singleton
    to ensure only one instance manages the scheduling system.

    Attributes
    ----------
        model (lightgbm.Booster): Trained LightGBM model
        interval_minutes (int): Time interval for schedule segments
            (default: 10)
        min_confidence (float): Minimum prediction confidence threshold
            (default: 0.6)
        schedule_cache (dict): Cache for current day's schedule
        db (DatabaseConnection): Database connection instance
        model_params (dict): LightGBM model parameters

    Note
    ----
        The class uses threading.Lock for thread-safe singleton implementation
    """

    # Singleton instance and lock
    _instance = None
    _lock = Lock()

    def __new__(cls):
        """
        Ensure only one instance of LightScheduler exists (Singleton pattern).

        Returns
        -------
            LightScheduler: The single instance of the scheduler
        """
        with cls._lock:  # Thread-safe instance creation
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        """Initialize the LightScheduler with default values.

        Only runs once due to Singleton pattern.
        """
        # Check if already initialized to prevent re-initialization
        if not hasattr(self, 'initialized'):
            self.initialized = True

            # Core components
            self.model = None  # LightGBM model instance
            self.interval_minutes = 10  # Schedule interval in minutes
            self.min_confidence = 0.6  # Minimum prediction threshold
            self.schedule_cache = {}  # Cache for current schedule
            self.db = None  # Database connection

            # LightGBM model configuration
            self.model_params = {
                'objective': 'binary',    # Binary classification task
                'metric': 'auc',          # Area Under Curve metric
                'boosting_type': 'gbdt',  # Gradient Boosting Decision Tree
                'num_leaves': 31,         # Maximum number of leaves in trees
                'learning_rate': 0.05,    # Learning rate for optimization
                'feature_fraction': 0.9,  # Frac of features used in each tree
                'bagging_fraction': 0.8,  # Frac of data used for each tree
                'bagging_freq': 5,        # Bagging frequency
                'verbose': -1             # Suppress logging output
            }

    def set_db_connection(self, db_connection: Optional[DB] = None) -> None:
        """Set or initialize the database connection.

        Args
        ----
            db_connection (DB, optional): A pre-existing database connection.
                                          If None, a new connection is created.
        """
        if db_connection:
            # Use the provided database connection
            # (for dependency injection/testing)
            self.db = db_connection
            logging.info("Database connection set via external instance.")
        else:
            # If no connection is provided, initialize a new DB connection
            connection_invalid = (
               not hasattr(self, "db") or
               self.db is None or
               self.db.conn.closed)
            if connection_invalid:
                logging.warning("Database connection is invalid or closed. "
                                "Attempting reconnection...")
                try:
                    self.db = DB()  # Try to establish a new connection
                    logging.info("Database reconnection successful.")
                except psycopg2.DatabaseError as e:
                    logging.error("Failed to reconnect to the database: %s", e)
                    self.db = None  # Set to None to prevent further issues
            else:
                logging.info("Database connection is still active.")

    def _prepare_training_data(self, days_history=30) -> tuple[pd.DataFrame,
                                                               pd.DataFrame]:
        """Get data from the activity log and previous schedules accuracy.

        Retrieve historical data from both activity logs and schedule accuracy
        records to prepare the training dataset.

        Args
        ----
            days_history (int): Number of days of historical data to use
                                (default: 30)

        Returns
        -------
            pandas.DataFrame: Prepared dataset with features and activity data

        Note
        ----
            Combines activity data with schedule accuracy metrics for model
            training.
        """
        # Define SQL queries
        # - Activity log query
        activity_query = """
            SELECT
                timestamp,
                day_of_week,
                month,
                year,
                duration,
                activity_pin,
                EXTRACT(EPOCH FROM timestamp) as epoch_time
            FROM activity_log
            WHERE timestamp >= NOW() - INTERVAL '%s days'
        """
        # - Schedule accuracy query
        schedule_query = """
            SELECT
                date,
                interval_number,
                was_correct,
                false_positive,
                false_negative,
                confidence
            FROM light_schedules
            WHERE date >= NOW() - INTERVAL '%s days'
        """

        # Execute queries and load into pandas DataFrames
        try:
            # Execute activity log query
            df_activity = pd.read_sql_query(
                activity_query,
                self.db.connection,
                params=(days_history,)
            )

            # Execute schedule accuracy query
            df_schedules = pd.read_sql_query(
                schedule_query,
                self.db.connection,
                params=(days_history,)
            )

            # Verify we have data
            if df_activity.empty:
                logging.warning(
                    "No activity data found for the specified period")
                return None

            logging.info(f"Retrieved {len(df_activity)} activity records and "
                         f"{len(df_schedules)} schedule records")
            # Enhanced feature engineering
            df = self._create_base_features(df_activity)
            # Add schedule accuracy features
            df = self._add_schedule_accuracy_features(df, df_schedules)

        except Exception as e:
            logging.error(f"Error retrieving training data: {str(e)}")
            raise

        # Return the complete dataset
        return df_activity, df_schedules

    def _create_base_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add training features.

        - Daily patterns (through hour encoding)
        - Weekly patterns (through day_of_week encoding)
        - Seasonal patterns (through month encoding)
        - Recent activity patterns (through rolling averages)
        - Environmental conditions (through darkness information)
        """
        # Process the activity data
        # Convert timestamp to datetime if not already
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Create interval features
        df['hour'] = df['timestamp'].dt.hour
        df['minute'] = df['timestamp'].dt.minute
        # Group times into intervals of self.interval_minutes.
        df['interval_number'] = ((df['hour'] * 60 + df['minute'])
                                 // self.interval_minutes)

        # Create cyclical time features
        #    sin(2π * value/max_value)
        #    cos(2π * value/max_value)

        # - Hours (24-hour cycle)
        # - hour_sin, hour_cos (24-hour cycle)
        df['hour_sin'] = np.sin(2 * np.pi * df['hour']/24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour']/24)

        # - Months (12-month cycle)
        # - month_sin, month_cos (12-month cycle)
        df['month_sin'] = np.sin(2 * np.pi * df['month']/12)
        df['month_cos'] = np.cos(2 * np.pi * df['month']/12)

        # - Days of week (7-day cycle)
        # - day_sin, day_cos (7-day cycle)
        df['day_sin'] = np.sin(2 * np.pi * df['day_of_week']/7)
        df['day_cos'] = np.cos(2 * np.pi * df['day_of_week']/7)

        # Create rolling activity features
        df.sort_values('timestamp', inplace=True)
        windows = [
            ('1h', 60 // self.interval_minutes),   # 1 hour
            ('4h', 240 // self.interval_minutes),  # 4 hours
            ('1d', 1440 // self.interval_minutes)  # 1 day
        ]

        # Get darkness times from PersistentData
        darkness_start, darkness_end = self._get_darkness_times()

        # Add darkness information
        df['is_dark'] = df['timestamp'].dt.time.apply(
            lambda x: self.is_dark(x, darkness_start, darkness_end)
        )

        # Create rolling averages of activity for different time windows.
        # Capture short-term and long-term trends in light usage.
        # For example, if lights were frequently on in the past hour, the model
        # should learn to keep them on.
        for name, window in windows:
            df[f'rolling_activity_{name}'] = (
                df.groupby('day_of_week')['activity_pin']
                .transform(
                    lambda x: x.rolling(window=window, min_periods=1).mean())
            )

        logging.info("Activity data processed successfully")
        return df

    def _get_darkness_times(self) -> tuple[dt.time, dt.time]:
        """Retrieve stored sunset and sunrise times from PersistentData.

        Returns
        -------
            tuple[dt.time, dt.time]: (darkness_start, darkness_end)
        """
        persistent_data = PersistentData()
        darkness_start = persistent_data.sunset_today
        darkness_end = persistent_data.sunrise_tomorrow

        # Ensure we have valid data, otherwise use default fallback
        if not darkness_start or not darkness_end:
            logging.warning(
                "Missing sunrise/sunset data, using default "
                "darkness (18:00-06:00).")
            darkness_start = dt.datetime.utcnow().replace(hour=18, minute=0)
            darkness_end = dt.datetime.utcnow().replace(hour=6, minute=0)

        return darkness_start.time(), darkness_end.time()

    @staticmethod
    def is_dark(time_obj: dt.time, darkness_start: dt.time,
                darkness_end: dt.time) -> int:
        """Determine if a given time falls within darkness hours.

        Uses stored sunset and sunrise times from PersistentData

        Args
        ----
            time_obj (dt.time): The time to check.

        Returns
        -------
            int: 1 if within darkness hours, 0 otherwise.
        """
        if darkness_start < darkness_end:
            # Darkness is within a single day (e.g., 18:00 - 06:00)
            return 1 if darkness_start <= time_obj <= darkness_end else 0
        else:
            # Darkness spans midnight (e.g., 21:00 - 05:00)
            return 1 if (time_obj >= darkness_start or
                         time_obj <= darkness_end) else 0

    def _add_schedule_accuracy_features(
                                self, df: pd.DataFrame,
                                df_schedules: pd.DataFrame) -> pd.DataFrame:
        """Enhance dataset with historical schedule accuracy metrics.

        Integrate past scheduling accuracy data into the activity dataset.
        This helps the model learn from past mistakes by including false
        positives, false negatives, and confidence levels per time interval.

        Args
        ----
        df (pandas.DataFrame): The main activity dataset.
        df_schedules (pandas.DataFrame): The historical schedule
            accuracy dataset.

        """
        # Aggregate historical accuracy per interval
        #   Calculate the mean accuracy (was_correct), Sum up false positives &
        #   false negatives, Compute the average confidence level
        accuracy_metrics = df_schedules.groupby(['interval_number']).agg({
            'was_correct': 'mean',      # Average accuracy per interval
            'false_positive': 'sum',    # Total false positives
            'false_negative': 'sum',    # Total false negatives
            'confidence': 'mean'        # Average confidence score
        }).reset_index()

        # Merge the aggregated schedule accuracy into the main database
        df = df.merge(
            accuracy_metrics,
            left_on='interval_number',  # Match intervals in activity data
            right_on='interval_number',
            how='left'                  # Preserve intervals in main dataset
        )

        # Handle missing values for intervals with no recorded accuracy
        #   Default accuracy: Assume 50% accuracy for unseen intervals
        df['historical_accuracy'] = df['was_correct'].fillna(0.5)
        # - Default false positive & false negative counts: Assume zero
        df['historical_false_positives'] = df['false_positive'].fillna(0)
        df['historical_false_negatives'] = df['false_negative'].fillna(0)
        # - Default confidence: Neutral confidence (0.5) for unseen intervals
        df['historical_confidence'] = df['confidence'].fillna(0.5)

        return df

    def train_model(self, days_history=30):
        """Train the LightGBM model using recent historical data.

        Retrieves historical data, selects relevant features, and trains a
        LightGBM model to predict when lights should be turned on.

        Args
        ----
            days_history (int): The number of days of historical data to use.

        Returns
        -------
            None
        """
        # 1️-Retrieve & prepare training data
        df = self._prepare_training_data(days_history)
        # 2-Select features for training
        feature_cols = self._get_feature_columns()
        x = df[feature_cols]
        # 3-Define the target variable
        y = (df['activity_pin'] > 0).astype(int)
        # 4-Create the dataset
        train_data = lgb.Dataset(x, label=y)
        # 5-Train the model
        self.model = lgb.train(
            self.model_params,
            train_data,
            num_boost_round=100,
            valid_sets=[train_data],
            early_stopping_rounds=10
        )
        # 6-log feature importance
        importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': self.model.feature_importance()
        }).sort_values('importance', ascending=False)

        logging.info("Feature importance:\n%s", importance)

    def _get_feature_columns(self) -> list[str]:
        """Return the list of feature columns used for training."""
        return [
            'hour_sin', 'hour_cos',  # Hour encoding
            'month_sin', 'month_cos',  # Seasonal encoding
            'day_sin', 'day_cos',  # Weekly pattern encoding
            'is_dark',  # Whether it's nighttime
            'rolling_activity_1h',  # Short-term activity trend
            'rolling_activity_1d',  # Long-term activity trend
            'interval_number',  # Time interval index
            'historical_accuracy',  # Past scheduling success rate
            'historical_false_positives',  # Past over-predictions
            'historical_false_negatives',  # Past under-predictions
            'historical_confidence'  # Average confidence in past schedules
        ]

    def generate_daily_schedule(self, date, darkness_start, darkness_end):
        """Generate a light schedule for a date based on model predictions.

        Create a daily schedule of when lights should be turned on,
        make sure predictions only fall within darkness hours.

        Args
        ----
            date (str): The date for which the schedule is
                        generated (YYYY-MM-DD).
            darkness_start (str): Time when darkness starts (HH:MM).
            darkness_end (str): Time when darkness ends (HH:MM).

        Returns
        -------
            dict: A dictionary mapping time intervals to predicted light
                  activation (True/False).
        """
        # Validate input parameters
        try:
            schedule_date = dt.datetime.strptime(
                date, "%Y-%m-%d").date()
            darkness_start = dt.datetime.strptime(
                darkness_start, "%H:%M").time()
            darkness_end = dt.datetime.strptime(
                darkness_end, "%H:%M").time()
        except ValueError as e:
            logging.error("Invalid date or time format: %s", e)
        return {}

        # Prepare prediction data
        interval_times = [
            (schedule_date, i) for i in range(
                (24 * 60) // self.interval_minutes)
        ]
        df = pd.DataFrame(interval_times, columns=["date", "interval_number"])

        # Compute necessary features for each interval
        df = self._create_base_features(df)

        # Filter for darkness hours only
        df["is_dark"] = df["timestamp"].dt.time.apply(self.is_dark)
        df = df[df["is_dark"] == 1]  # Keep only dark intervals

        # Make predictions using the trained model
        if self.model is None:
            logging.error("No trained model found. Cannot generate schedule.")
        return {}

        predictions = self._predict_schedule(df)

        # Store and return the generated schedule
        return self.store_schedule(schedule_date, df, predictions)

    def store_schedule(self, schedule_date: dt.date,
                       df: pd.DataFrame, predictions: list[int]) -> dict:
        """Store the generated schedule in cache and database.

        Args
        ----
            schedule_date (dt.date): The date of the schedule.
            df (pandas.DataFrame): DataFrame containing intervals for the date.
            predictions (list[int]): List of light activation predictions
                                    (0 or 1).

        Returns
        -------
            dict: The stored schedule mapping interval numbers to light status.
        """
        # Store in cache
        schedule = dict(zip(df["interval_number"], predictions))
        self.schedule_cache[schedule_date] = schedule

        # Store in database
        # Check we have a database connection
        if self.db is None or self.db.conn.closed:
            logging.warning("Database connection unavailable."
                            "Attempting reconnection...")
            self.set_db_connection()  # Attempt to reconnect

        if self.db is None:
            logging.error("Database connection could not be established."
                          "Skipping database storage.")
            return schedule  # Return cache-only schedule if DB is down

        # If we get here, database is healthy, Store in database
        try:
            with self.db.conn.cursor() as cursor:
                for interval, prediction in schedule.items():
                    start_time = (dt.datetime.combine(
                        schedule_date, dt.time(0, 0)) + dt.timedelta(
                            minutes=interval * self.interval_minutes)).time()
                    end_time = (dt.datetime.combine(
                        schedule_date, dt.time(0, 0)) + dt.timedelta(
                            minutes=(interval + 1) *
                            self.interval_minutes)).time()

                    cursor.execute("""
                        INSERT INTO light_schedules (date, interval_number,
                                                     start_time, end_time,
                                                     prediction)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (date, interval_number) DO UPDATE
                        SET prediction = EXCLUDED.prediction;
                    """, (schedule_date, interval, start_time, end_time,
                          prediction))

            self.db.conn.commit()  # Commit transaction
            logging.info(f"Stored schedule for {schedule_date} in database.")

        except psycopg2.DatabaseError as e:
            self.db.conn.rollback()  # Rollback on failure
            logging.error(f"Failed to store schedule for {schedule_date}: {e}")

        return schedule

    def get_schedule(self, target_date: dt.date) -> dict:
        """Retrieve the light schedule for a given date.

        Args
        ----
            target_date (dt.date): The date for which to retrieve the schedule.

        Returns
        -------
            dict: A dictionary mapping interval numbers to light status
                  (0 or 1). Returns an empty dict if no schedule is found.
        """
        # 1-Check if the schedule is already in cache
        # 2️-If not in cache, attempt to retrieve it from the database
        # 3️-If retrieved from the database, store it in cache
        # 4️-Return the retrieved schedule (or an empty dict if none found)
        pass

    def evaluate_previous_schedule(self, date: dt.date) -> None:
        """Evaluate the accuracy of the previous day's schedule.

        Args
        ----
            date (dt.date): The date of the schedule to evaluate.

        This method:
        -Retrieves the scheduled light intervals from `light_schedules`.
        -Retrieves actual activity timestamps from `activity_log`.
        -Compares each scheduled interval with actual activity.
        -Determines if the schedule was correct, a false positive,
         or a false negative.
        -Updates the accuracy metrics in `light_schedules` using
         `update_schedule_accuracy()`.
        """
        # 1️-Retrieve scheduled light intervals from `light_schedules`
        # 2️-Retrieve actual activity timestamps from `activity_log`
        # 3️-Compare scheduled intervals with actual activity
        # 4️-Identify false positives (lights on, no activity detected)
        # 5️-Identify false negatives (activity detected, lights not scheduled)
        # 6️-Update the schedule accuracy in the database
        pass

    def update_schedule_accuracy(self, date: dt.date, interval_number: int,
                                 was_correct: bool, false_positive: bool,
                                 false_negative: bool) -> None:
        """Update the accuracy metrics for a specific schedule interval.

        Args
        ----
            date (dt.date): The schedule date.
            interval_number (int): The interval number to update.
            was_correct (bool): Whether the schedule was correct.
            false_positive (bool): Whether the lights were on unnecessarily.
            false_negative (bool): Whether lights were off when needed.

        This method updates:
        - `was_correct` → 1, the schedule matched actual activity, 0 otherwise.
        - `false_positive` → 1, the schedule had unnecessary lights.
        - `false_negative` → 1, activity was detected but no lights
                                were scheduled.
        """
        # 1️-Construct and execute an SQL `UPDATE` statement to store accuracy
        # 2️-Commit the changes to the database
        # 3️-Handle potential exceptions (rollback on failure, log errors)
        pass

    def update_daily_schedule(self) -> Optional[dict]:
        """Generate and store tomorrow's schedule.

        This method:
        -Evaluates the accuracy of yesterday's schedule.
        -Trains the model with updated accuracy data.
        -Generates a new schedule for tomorrow.
        -Stores the new schedule in both the database and cache.
        -Handles potential failures and logs errors.

        Returns
        -------
            Optional[dict]: The generated schedule for tomorrow or None if an
                            error occurs.
        """
        try:
            # Make sure only one thread can try to update the schedule at
            # any time
            with self._lock:
                # 1️-Evaluate yesterday's schedule accuracy
                # 2️-Retrain the model using updated accuracy data
                # 3️-Generate a new schedule for tomorrow
                # 4️-Store the generated schedule in the database
                # 5️-Update the in-memory schedule cache
                # 6️-Log the successful update and return the new schedule

                return None  # Replace with the actual new schedule
        except Exception as e:
            # 7️-Handle errors, log the issue, and return None
            return None

    def get_current_schedule(self) -> dict:
        """Get the cached schedule or load it from the database if needed.

        This method:
        -Check if today's schedule is already in `self.schedule_cache`.
        -If the cache is empty or outdated, load the schedule from the db.
        -Update the cache with the retrieved schedule.
        -Return the cached schedule.

        Returns
        -------
            dict: The schedule for the current day
                  (interval_number → light status).
        """
        # 1️-Get today's date
        # 2️-Check if the schedule is already cached and up to date
        # 3-If not in cache, retrieve from the database using `get_schedule()`
        # 4️-Store the retrieved schedule in `self.schedule_cache`
        # 5️-Return the cached schedule
        pass

    def should_light_be_on(
            self, current_time: Optional[dt.datetime] = None) -> bool:
        """Determine if the lights should be on at a given moment.

        Args
        ----
            current_time (Optional[dt.datetime]):
                The time to check. Defaults to now if not provided.

        Returns
        -------
            bool: True if lights should be ON, False otherwise.

        This method:
        -Uses the current time if no time is provided.
        -Identifies the correct schedule (yesterday or today).
        -Retrieves the relevant interval number for the given time.
        -Checks if lights should be ON for that interval.
        """
        # 1️-Get the current time (use datetime.now() if None)
        # 2️-Identify the relevant schedule date (yesterday or today)
        # 3️-Retrieve the schedule for the identified date
        # 4️-Determine the current interval number
        # 5️-Check if lights should be ON for this interval
        # 6️-Return True (ON) or False (OFF)
        pass

    def set_interval_minutes(self, minutes: int) -> None:
        """Adjust interval duration for scheduling and recalculate schedules.

        Args
        ----
            minutes (int): The new interval duration in minutes.

        This method:
        -Validates the input to ensure it’s a positive integer.
        -Updates `self.interval_minutes` with the new value.
        -Logs the change for debugging.
        -Triggers a recalc of the current schedule to use the new interval.
        """
        # 1️-Validate that `minutes` is a positive integer
        # 2️-Update `self.interval_minutes`
        # 3️-Recalculate schedules based on the new interval
        pass

    def set_confidence_threshold(self, threshold: float) -> None:
        """Update the confidence threshold for predictions.

        The confidence threshold determines how certain the model must be
        before scheduling lights to turn on.

        The LightGBM model outputs a probability (0.0 to 1.0) for light
        activation. When generating a schedule, predictions will only activate
        lights if confidence ≥ threshold.

        Args
        ----
            threshold (float): The new confidence threshold (0.0 - 1.0).

        This method:
        -Validates the threshold value (must be between 0 and 1).
        -Updates `self.min_confidence` with the new threshold.
        -Logs the update.
        -Triggers retraining or schedule recalculations.
        """
        # 1️-Validate that `threshold` is between 0.0 and 1.0
        # 2️-Update `self.min_confidence`
        # 3️-Log the threshold change
        # 4️-Recalculate schedules or retrain the model if needed
        pass

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

        This method:
        -Extracts time-based features (hour, day of week, month).
        -Converts these into cyclical features (`sin/cos` encoding).
        -Determines whether the timestamp falls within darkness hours.
        -Retrieves historical schedule accuracy features for this interval.
        -Computes rolling activity features for short- and long-term trends.
        -Returns both a structured DataFrame and a NumPy array.
        """
        # 1️-Extract time components
        # 2️-Apply cyclical transformations (sin/cos encoding)
        # 3️-Determine if the timestamp is within darkness hours
        # 4️-Calculate interval number
        # 5-Retrieve historical accuracy features (default fallback if missing)
        # 6️-Compute rolling activity features
        # 7️-Construct feature vector
        # 8️-Create DataFrame for debugging & training
        pass

    def _generate_features_dict(self, timestamp: dt.datetime) -> dict:
        """Generate feature values for a timestamp.

        Args
        ----
            timestamp (dt.datetime): The timestamp to generate features for.

        Returns
        -------
            dict: A dictionary of extracted feature values.
        """

        # Extract time components
        hour = timestamp.hour
        minute = timestamp.minute
        day_of_week = timestamp.weekday()
        month = timestamp.month
    
        # Apply cyclical transformations (sin/cos encoding)
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)
        day_sin = np.sin(2 * np.pi * day_of_week / 7)
        day_cos = np.cos(2 * np.pi * day_of_week / 7)
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)

        # Determine if the timestamp is within darkness hours
        is_dark = self.is_dark(timestamp.time())
    
        # Calculate interval number
        interval_number = (hour * 60 + minute) // self.interval_minutes

        # Retrieve historical accuracy features (default if missing)
        history = self.get_schedule(timestamp.date()).get(interval_number, {})
        historical_accuracy = history.get("historical_accuracy", 0.5)
        historical_false_positives = history.get("historical_false_positives", 0)
        historical_false_negatives = history.get("historical_false_negatives", 0)
        historical_confidence = history.get("historical_confidence", 0.5)
    
        # Compute rolling activity features
        past_activity = self._retrieve_past_activity(timestamp.date(), interval_number)
        rolling_activity_1h = np.mean(past_activity[-6:]) if len(past_activity) >= 6 else 0  # Last hour
        rolling_activity_1d = np.mean(past_activity) if past_activity else 0  # Last 24 hours

        # Construct feature dictionary using `_get_feature_columns()`
        feature_values = {
            "hour_sin": hour_sin, "hour_cos": hour_cos,
            "day_sin": day_sin, "day_cos": day_cos,
            "month_sin": month_sin, "month_cos": month_cos,
            "is_dark": is_dark,
            "rolling_activity_1h": rolling_activity_1h,
            "rolling_activity_1d": rolling_activity_1d,
            "interval_number": interval_number,
            "historical_accuracy": historical_accuracy,
            "historical_false_positives": historical_false_positives,
            "historical_false_negatives": historical_false_negatives,
            "historical_confidence": historical_confidence
        }

        # Ensure only the required features are included
        return {key: feature_values[key] for key in self._get_feature_columns()}