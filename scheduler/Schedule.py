"""scheduler.schedule.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate daily schedules, train the learning model
Author: Will Bickerstaff
Version: 0.1
"""

from threading import Lock
from lightlib.persist import PersistentData
from lightlib.db import DB
from lightlib.common import DATE_TODAY
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
            self._warned_missing = None

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
            self.set_db_connection()

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
        # Don't do eanythin if the DB connection is not established
        if self.db is None or self.db.conn.closed:
            logging.warning("DB connection not established, can't train")
            return None
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

        engine = self.db.get_alchemy_engine()
        # Execute queries and load into pandas DataFrames
        try:
            if engine is not None:
                logging.debug("Using SQLAlchemy to retrieve training data.")
            else:
                engine = self.db.conn
                logging.debug("Using psycopg2 to retrieve training data.")

            # Execute activity log query
            df_activity = pd.read_sql_query(
                activity_query,
                engine,
                params=(days_history,)
            )

            # Execute schedule accuracy query
            df_schedules = pd.read_sql_query(
                schedule_query,
                engine,
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
        # Apply the shared feature function to all timestamps
        feature_dicts = df['timestamp'].apply(self._generate_features_dict)

        # Convert the list of feature dictionaries into a DataFrame
        features_df = pd.DataFrame(feature_dicts.tolist(), index=df.index)

        # Merge the features back into the original dataset
        df = pd.concat([df, features_df], axis=1)

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

        # Create a tracking attribute for the logged warning
        # (Removes multiple log entries)
        if not hasattr(self, "_warned_missing"):
            self._warned_missing = None
        # Ensure we have valid data, otherwise use default fallback
        if not darkness_start or not darkness_end:
            if self._warned_missing != DATE_TODAY:
                logging.warning("Missing sunrise/sunset data, using default "
                                "darkness (15:30-09:00).")
                # Track that the warning has been looged today
                # (reduce log spam)
                self._warned_missing = DATE_TODAY
            now = dt.datetime.now(dt.UTC)
            darkness_start = now.replace(hour=15, minute=30)
            darkness_end = now.replace(hour=9, minute=0) + dt.timedelta(days=1)

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
        # cast columns before filling
        df['was_correct'] = df['was_correct'].astype(float)
        df['confidence'] = df['confidence'].astype(float)
        df['false_positive'] = df['false_positive'].astype(int)
        df['false_negative'] = df['false_negative'].astype(int)

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
        #   1-Retrieve & prepare training data
        fetched_data = self._prepare_training_data(days_history)
        # If there is no training data then exit
        if fetched_data is None:
            logging.warning(
                "No training data available, skipping model training")
            return

        df_activity, df_schedules = fetched_data
        df = self._create_base_features(df_activity)
        df = self._add_schedule_accuracy_features(df, df_schedules)

        # 2-Select features for training
        feature_cols = self._get_feature_columns()
        x = df[feature_cols]
        # 3-Define the target variable
        y = (df['activity_pin'] > 0).astype(int)
        # 4-Create the dataset
        train_data = lgb.Dataset(x, label=y)
        # 5-Train the model
        try:
            # Attempt with newer LightGBM API
            self.model = lgb.train(
                self.model_params,
                train_data,
                num_boost_round=100,
                valid_sets=[train_data],
                early_stopping_rounds=10
            )
        except TypeError:
            # Fallback to callbacks on older LightGBM versions
            logging.warning("LightGBM Unsupported kwarg early_stopping_rounds"
                            "falling back to callbacks API")
            self.model = lgb.train(
                self.model_params,
                train_data,
                num_boost_round=100,
                valid_sets=[train_data],
                callbacks=[lgb.early_stopping(stopping_rounds=10)]
            )
        # 6-log feature importance
        importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': self.model.feature_importance()
        }).sort_values('importance', ascending=False)

        logging.info("Feature importance:\n%s", importance)

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
            'is_dark',                     # Whether it's nighttime
            'rolling_activity_1h',         # Short-term activity trend
            'rolling_activity_1d',         # Long-term activity trend
            'interval_number',             # Time interval index
            'historical_accuracy',         # Past scheduling success rate
            'historical_false_positives',  # Past over-predictions
            'historical_false_negatives',  # Past under-predictions
            'historical_confidence'        # Average confidence in past
                                           # schedules
        ]

    def _progressive_history(self) -> int:
        """Return the maximum available number of days for training.

        Allow the model to adjust its training history dynamically based on
        how much data is available in the activity log. Starts small and
        grows progressively up to a maximum.

        Returns
        -------
        int
            The number of days to use for training, capped at MAX_DAYS_HISTORY.
        """
        MAX_DAYS_HISTORY = 30   # Cap at 30 days
        MIN_DAYS_HISTORY = 2    # Minimum to avoid meaningless tiny training

        try:
            # Check database connection
            if self.db is None or self.db.conn.closed:
                self.set_db_connection()
                if self.db is None:
                    logging.error(
                        "No database connection available to check history.")
                    return MIN_DAYS_HISTORY

            # Query for the oldest timestamp in activity_log
            query = "SELECT MIN(timestamp) FROM activity_log;"
            with self.db.conn.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                oldest_timestamp = result[0]

            if oldest_timestamp is None:
                # No data at all yet
                logging.warning(
                    "0 activity records found. Using minimum training window.")
                return MIN_DAYS_HISTORY

            today = dt.datetime.now(dt.UTC)
            history_days = (today - oldest_timestamp).days
            effective_days = max(MIN_DAYS_HISTORY,
                                 min(history_days, MAX_DAYS_HISTORY))

            logging.info("Progressive training window determined: %d days "
                         "(raw history: %d days)",
                         effective_days, history_days)

            return effective_days

        except Exception as e:
            logging.error(
                "Failed to calculate progressive training history: %s", e)
            return MIN_DAYS_HISTORY

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

        # Build empty df with just date
        num_intervals = (24 * 60) // self.interval_minutes
        df = pd.DataFrame({'date': [schedule_date] * num_intervals})

        # Add timestamp for each interval
        df['timestamp'] = [
            dt.datetime.combine(schedule_date, dt.time(
                hour=(i * self.interval_minutes) // 60,
                minute=(i * self.interval_minutes) % 60
            ))
            for i in range(num_intervals)
        ]

        # Compute necessary features (includes interval_number correctly)
        df = self._create_base_features(df)

        # Calculate is_dark field based on darkness window
        df['is_dark'] = df['timestamp'].dt.time.apply(
            lambda t: self.is_dark(t, darkness_start, darkness_end)
        )

        # Filter to only darkness intervals
        df = df[df['is_dark'] == 1]

        logging.debug(
            "Prediction DataFrame after darkness filter: \n%s", df.head())

        if df.empty:
            logging.warning(
                "No darkness intervals found for %s. Empty schedule.",
                schedule_date)
            return {}

        if self.model is None:
            logging.error("No trained model found. Cannot generate schedule.")
            return {}

        predictions, probabilities = self._predict_schedule(df)
        # logging.debug("Predictions: %s", predictions.tolist())
        # logging.debug("Prediction probabilities: %s", probabilities.tolist())

        return self.store_schedule(schedule_date, df,
                                   predictions, probabilities)

    def _predict_schedule(self, df: pd.DataFrame) -> np.ndarray:
        """Generate predictions for the given schedule DataFrame.

        Args
        ----
            df (pd.DataFrame): DataFrame containing feature columns
            for prediction.

        Returns
        -------
            np.ndarray: Array of predicted labels (0 or 1).
        """
        if self.model is None:
            logging.error("No trained model found. Cannot make predictions.")
            return np.array([])

        feature_cols = self._get_feature_columns()

        # Drop polluting non-feature columns BEFORE selecting feature columns
        drop_cols = ['date', 'timestamp']
        df = df.drop(columns=[col for col in drop_cols if col in df.columns])

        # logging.debug("After dropping non-features, DataFrame columns: %s",
        #              df.columns.tolist())
        # logging.debug("Expected feature columns: %s", feature_cols)
        # Always slice the DataFrame cleanly
        x_predict = df[feature_cols].copy()

        y_pred = self.model.predict(x_predict)
        probabilities = self.model.predict(x_predict, raw_score=False)
        predictions = (y_pred >= self.min_confidence).astype(int)

        return predictions, probabilities

    def store_schedule(self, schedule_date: dt.date, df: pd.DataFrame,
                       predictions: np.ndarray,
                       probabilities: np.ndarray) -> dict:
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
        schedule = {}
        for idx, row in enumerate(df.itertuples(index=False)):
            interval = int(row.interval_number)
            schedule[interval] = {
                "start": (dt.datetime.combine(schedule_date, dt.time(0, 0)) +
                          dt.timedelta(minutes=interval *
                                       self.interval_minutes)).time(),
                "end": (dt.datetime.combine(schedule_date, dt.time(0, 0)) +
                        dt.timedelta(minutes=(interval+1) *
                                     self.interval_minutes)).time(),
                "prediction": True if int(predictions[idx]) > 0 else False,
                "confidence": float(probabilities[idx])
            }

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
                for interval, info in schedule.items():
                    cursor.execute("""
                        INSERT INTO light_schedules (date, interval_number,
                                                     start_time, end_time,
                                                     prediction)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (date, interval_number) DO UPDATE
                        SET prediction = EXCLUDED.prediction;
                    """, (schedule_date, int(interval), info["start"],
                          info["end"], info["prediction"]))

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
        # Check if the schedule is already in cache
        if self.schedule_cache.get('date') == target_date:
            return self.schedule_cache.get('schedule', {})
        # If not in cache, attempt to retrieve it from the database
        # Check DB connection
        if self.db is None or self.db.conn.closed:
            logging.warning("Database connection unavailable. "
                            "Attempting reconnection...")
            self.set_db_connection()
            if self.db is None:
                logging.error("Database connection could not be established.")
                return {}

        # Query the database
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT interval_number, start_time, end_time, prediction,
                confidence
                    FROM light_schedules
                    WHERE date = %s
                """, (target_date,))
                rows = cur.fetchall()
                logging.debug("get_schedule fetched %i rows for %s",
                              len(rows), target_date)
            # Convert results to a dictionary
            schedule = {}
            for row in rows:
                schedule[row[0]] = {
                    "start": row[1],
                    "end": row[2],
                    "prediction": row[3],
                    "confidence": row[4] if row[4] is not None else 0.5
                }
        # If retrieved from the database, store it in cache
            self.schedule_cache = {
                'date': target_date,
                'schedule': schedule
            }

            return schedule

        except psycopg2.DatabaseError as e:
            logging.error(
                f"Failed to retrieve schedule for {target_date}: {e}")
            return {}

    def evaluate_previous_schedule(self, date: dt.date) -> None:
        """Evaluate the accuracy of the previous day's schedule.

        Args
        ----
            date (dt.date): The date of the schedule to evaluate.

        -Retrieve the scheduled light intervals from `light_schedules`.
        -Retrieve actual activity timestamps from `activity_log`.
        -Compare each scheduled interval with actual activity.
        -Determine if the schedule was correct, a false positive,
         or a false negative.
        -Update the accuracy metrics in `light_schedules` using
         `update_schedule_accuracy()`.
        """
        schedule_query = """
            SELECT interval_number, start_time, end_time, prediction
            FROM light_schedules
            WHERE date = %s
        """
        activity_query = """
            SELECT timestamp
            FROM activity_log
            WHERE DATE(timestamp) = %s
        """
        # Fetch actual activity data and the schedule for the date
        try:
            with self.db.conn.cursor() as cur:
                # Fetch schedule entries for the date
                cur.execute(schedule_query, (date,))
                scheduled_intervals = cur.fetchall()

                # Fetch all activity timestamps
                cur.execute(activity_query, (date,))
                activity_timestamps = [row[0] for row in cur.fetchall()]

            # Build a set of activity times for fast lookup
            activity_times = [ts.time() for ts in activity_timestamps]

            seen_intervals = set()

            for interval, start_time, end_time, prediction \
                    in scheduled_intervals:

                # Skip evaluation if the interval hasn't ended yet
                now = dt.datetime.now(dt.UTC)
                if dt.datetime.combine(date, end_time) > now:
                    continue

                seen_intervals.add(interval)

                # Skip intervals where prediction was off
                if not prediction:
                    continue

                # Check if any activity happened during this interval
                activity_occurred = any(
                    start_time <= act_time <= end_time
                    for act_time in activity_times
                )

                # Classify the outcome
                was_correct = activity_occurred
                false_positive = not activity_occurred
                false_negative = False  # False negatives below

                self.update_schedule_accuracy(
                    date=date,
                    interval_number=interval,
                    was_correct=was_correct,
                    false_positive=false_positive,
                    false_negative=false_negative
                )

            # False negatives: activity without a scheduled light
            for ts in activity_timestamps:
                interval = (ts.hour * 60 + ts.minute) // self.interval_minutes
                if interval not in seen_intervals:
                    self.update_schedule_accuracy(
                        date=date,
                        interval_number=interval,
                        was_correct=False,
                        false_positive=False,
                        false_negative=True
                    )
            logging.info(f"Schedule evaluation completed for {date}")

        except Exception as e:
            logging.error(f"Failed to evaluate schedule for {date}: {e}")

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

        Updates:
        - was_correct → 1, the schedule matched actual activity, 0 otherwise.
        - false_positive → 1, the schedule had unnecessary lights.
        - false_negative → 1, activity was detected but no lights
                                were scheduled.
        """
        update_query = """
            UPDATE light_schedules
            SET
                was_correct = %s,
                false_positive = %s,
                false_negative = %s
            WHERE date = %s AND interval_number = %s
        """

        try:
            with self.db.conn.cursor() as cur:
                cur.execute(update_query, (
                    was_correct, false_positive, false_negative, date,
                    interval_number
                ))
            self.db.conn.commit()
            logging.debug(
                f"Updated accuracy for {date} interval {interval_number}")

        except Exception as e:
            # Handle potential exceptions (rollback on failure, log errors)
            self.db.conn.rollback()
            logging.error(f"Failed to update accuracy for {date} interval "
                          f"{interval_number}: {e}")

    def update_daily_schedule(self) -> Optional[dict]:
        """Generate and store tomorrow's schedule.

        - Evaluate the accuracy of yesterday's schedule.
        - Retrain the model with updated data.
        - Generate a new schedule for tomorrow.
        - Store it in the database and updates the in-memory cache.

        Returns
        -------
            Optional[dict]: The generated schedule for tomorrow or None if an
                            error occurs.
        """
        try:
            # Make sure only one thread can try to update the schedule at
            # any time
            with self._lock:
                # Evaluate yesterday's schedule accuracy
                yesterday = dt.datetime.now().date() - dt.timedelta(days=1)
                self.evaluate_previous_schedule(yesterday)
                # Retrain the model using updated accuracy data
                self.train_model(days_history=self._progressive_history())
                # Get tomorrow's date and darkness period
                tomorrow = dt.datetime.now().date() + dt.timedelta(days=1)
                darkness_start, darkness_end = self._get_darkness_times()
                # Generate a new schedule for tomorrow
                new_schedule = self.generate_daily_schedule(
                    tomorrow.strftime("%Y-%m-%d"),
                    darkness_start.strftime("%H:%M"),
                    darkness_end.strftime("%H:%M")
                )
                # Storage of the generated schedule in the database & cache
                # is completed by `self.generate_daily_schedule' with its
                # final call to `self.store_schedule'
                if not new_schedule:
                    # Empty schedule
                    logging.warning("Empty schedule generated for %s",
                                    tomorrow)
                else:
                    # Log the successful update and return the new schedule
                    logging.info("Successfully updated schedule for %s",
                                 tomorrow)
                self._log_schedule(new_schedule, tomorrow)
                return new_schedule

        except Exception as e:
            logging.error("Failed to update daily schedule: %s", e)
            raise e
            return None

    def get_current_schedule(self,
                             target_date: Optional[dt.date] = None) -> dict:
        """Get the cached schedule or load it from the database if needed.

        Returns
        -------
            dict: (Optional[dt.date]): Date for the schedule.
                                       Defaults to today.
        """
        # Get today's date if no date is given
        if target_date is None:
            target_date = dt.datetime.now().date()

        # Check if the schedule is already cached and up to date
        logging.debug(
            f"Checking cache for date: {self.schedule_cache.get('date')}")
        if (self.schedule_cache and
                self.schedule_cache.get('date') == target_date):
            logging.info("Schedule retrieved from cache")
            return self.schedule_cache['schedule']

        # Not in cache, retrieve from the database using `get_schedule()`
        schedule = self.get_schedule(target_date)
        # Store the retrieved schedule in `self.schedule_cache`
        self.schedule_cache = {
            'date': target_date,
            'schedule': schedule
        }
        logging.info(f"Schedule loaded from DB: {schedule}")
        return schedule

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
        # Get the current time (use datetime.now() if None)
        now = current_time or dt.datetime.now(dt.UTC)
        # Identify the relevant schedule date (yesterday or today)
        # Get darkness times for today (could span two dates)
        darkness_start, darkness_end = self._get_darkness_times()

        # Determine if this moment falls in today's or yesterday's schedule
        if darkness_start < darkness_end:
            # Darkness is within a single day (e.g. 18:00–06:00)
            schedule_date = now.date()
        else:
            # Darkness spans midnight: decide based on whether time is after
            # midnight but before sunrise
            if now.time() <= darkness_end:
                schedule_date = (now - dt.timedelta(days=1)).date()
            else:
                schedule_date = now.date()
        # Retrieve the schedule for the identified date
        schedule = self.get_schedule(schedule_date)
        # Determine the current interval number
        interval_number = (now.hour * 60 + now.minute) // self.interval_minutes
        # return if lights should be ON for this interval
        return schedule.get(interval_number, 0) == 1

    def set_interval_minutes(self, minutes: int,
                             retrain: Optional[int] = 1) -> None:
        """Adjust interval duration for scheduling and recalculate schedules.

        Controls the granularity of the schedule. For example,
        an interval of 10 means the model will make predictions in
        10-minute segments.

        Args
        ----
            minutes (int): The new interval duration in minutes.
            retrain Optional[int]: 1 or 0, retrain the model after changing.
                                   Default is 1 (retrain)

        Raises
        ------
            ValueError: If the interval is not a positive integer.
        """
        if not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("Interval must be a positive integer")

        old_interval = self.interval_minutes
        self.interval_minutes = minutes

        logging.info(
            "Updated interval duration from %d to %d minutes",
            old_interval, self.interval_minutes
        )

        # Retrain the model, if needed.
        if retrain == 1:
            self.update_daily_schedule()

    def set_confidence_threshold(self, threshold: float,
                                 retrain: Optional[int] = 1) -> None:
        """Update the confidence threshold for predictions.

        Controls how certain the model must be before it
        schedules lights to turn on. Predictions with a confidence
        below this threshold will be ignored.

        Args
        ----
            threshold (float): The new confidence threshold
                               (must be between 0.0 and 1.0).
            retrain Optional[int]: 1 or 0, retrain the model after changing.
                                   Default is 1 (retrain)

        Raises
        ------
            ValueError: If the threshold is out of the valid range.
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "Confidence threshold must be between 0.0 and 1.0")

        old_threshold = self.min_confidence
        self.min_confidence = threshold

        logging.info(
            "Updated confidence threshold from %.2f to %.2f",
            old_threshold, self.min_confidence
        )

        # Retrain the model, if needed.
        if retrain == 1:
            self.update_daily_schedule()

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

        # Determine if the timestamp is within darkness hours
        darkness_start, darkness_end = self._get_darkness_times()
        is_dark = self.is_dark(timestamp.time(), darkness_start, darkness_end)

        # Calculate interval number
        interval_number = (hour * 60 + minute) // self.interval_minutes

        # Retrieve historical accuracy features (default if missing)
        history = self.get_schedule(timestamp.date()).get(interval_number, {})
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
            "is_dark": is_dark,
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
                start_time = dt.datetime.combine(
                    historical_date, dt.time(0, 0)
                ) + dt.timedelta(
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

    def _log_schedule(self, schedule: dict, schedule_date: dt.date) -> None:
        """Log the generated UTC schedule as a fomatted table (DEBUG only).

        Logs each scheduled interval where the light is predicted to be ON,
        along with its start and end time and associated confidence score.
        The output is formatted as a table and sorted chronologically by ON
        time.

        Logging only occurs if the active log level is DEBUG. If the schedule
        is empty, a warning is logged instead.

        Args
        ----
        schedule : dict
            The generated schedule, where each key is an interval number and
            the value is a dictionary containing 'start', 'end', 'prediction',
            and optionally 'confidence'.

        schedule_date : datetime.date
            The date the schedule was generated for, used in the log output.
        """
        if not schedule:
            logging.warning("Empty UTC Schedule generated")
            return
        if not logging.getLogger().isEnabledFor(logging.DEBUG):
            return  # Skip formatting unless debug level is enabled

        rows = []
        # Extract all intervals and build row data
        for interval, val in schedule.items():
            rows.append({
                "start": val["start"],
                "end": val["end"],
                "confidence": val.get("confidence", 0.0),
                "state": "ON" if val.get("prediction", 0) == 1 else "OFF"
            })

        # Sort by start time
        rows.sort(key=lambda r: r["start"])

        # Table heading
        lines = [
            "UTC Schedule generated:\n",
            "Sched Date  | Start    | End      | State | Confidence",
            "-" * 59
        ]
        for r in rows:
            lines.append(
                f" {schedule_date.strftime('%Y-%m-%d')} |"
                f" {r['start'].strftime('%H:%M')}    |"
                f" {r['end'].strftime('%H:%M')}    |"
                f" {r['state']:^5} | {r['confidence']:.2f}"
            )

        logging.debug("\n" + "\n".join(lines))
