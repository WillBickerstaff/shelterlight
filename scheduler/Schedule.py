"""scheduler.schedule.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate daily schedules
Author: Will Bickerstaff
Version: 0.1
"""

from threading import Lock
from shelterGPS.Helio import SunTimes
import pandas as pd
import numpy as np
import lightgbm as lgb  # https://lightgbm.readthedocs.io/en/stable/
from datetime import datetime, timedelta
import logging


class LightScheduler:
    """
    A Singleton class that manages light scheduling using machine learning.

    This class uses LightGBM to learn patterns from historical activity data
    and generate optimal lighting schedules. It implements the Singleton
    to ensure only one instance manages the scheduling system.

    Attributes:
        model (lightgbm.Booster): Trained LightGBM model
        interval_minutes (int): Time interval for schedule segments
            (default: 10)
        min_confidence (float): Minimum prediction confidence threshold 
            (default: 0.6)
        schedule_cache (dict): Cache for current day's schedule
        db (DatabaseConnection): Database connection instance
        model_params (dict): LightGBM model parameters

    Note:
        The class uses threading.Lock for thread-safe singleton implementation
    """
    # Singleton instance and lock
    _instance = None
    _lock = Lock()

    def __new__(cls):
        """
        Ensures only one instance of LightScheduler exists (Singleton pattern).
        
        Returns:
            LightScheduler: The single instance of the scheduler
        """
        with cls._lock:  # Thread-safe instance creation
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        """
        Initializes the LightScheduler with default values.
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

    def set_db_connection(self, db_connection):
        self.db = db_connection

    def _prepare_training_data(self, days_history=30):
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

    def _create_base_features(self, df):
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

        # Add darkness information
        SunActivity = SunTimes()
        darkness_start = SunActivity.UTC_sunset_today
        darkness_end = SunActivity.UTC_sunrise_tomorrow

        df['is_dark'] = df['timestamp'].dt.time.apply(
            lambda x: LightScheduler.is_dark(
                x, darkness_start, darkness_end))

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

    def is_dark(time_obj, start_dark, end_dark):
        """Determine if a given time falls within darkness hours.

        Args
        ----
            time_obj (datetime.time): The time to check.
            start (datetime.time): Darkness start time.
            end (datetime.time): Darkness end time.

        Returns
        -------
            int: 1 if within darkness hours, 0 otherwise.
        """
        if start_dark < end_dark:
            # Darkness is within one day
            return 1 if start_dark <= time_obj <= end_dark else 0
        else:
            # Darkness spans midnight
            return 1 if (time_obj >= start_dark or time_obj <= end_dark) else 0

    def _add_schedule_accuracy_features(self):
        """Enhance dataset with historical schedule accuracy metrics.

        Integrate past scheduling accuracy data into the activity dataset.
        This helps the model learn from past mistakes by including false 
        positives, false negatives, and confidence levels per time interval.

        """
        # 1️-Aggregate historical accuracy per interval
        
        # 2-Merge the aggregated schedule accuracy into the main database
        
        # 3-Handle missing values for intervals with no recorded schedule accuracy

    def train_model(self):

        pass

    def generate_daily_schedule(self, date, darkness_start, darkness_end):

        pass

    def store_schedule(self):

        pass

    def get_schedule(self):

        pass

    def evaluate_previous_schedule(self, date):

        pass

    def update_schedule_accuracy(self, date):

        pass

    def update_daily_schedule(self):

        pass

    def get_current_schedule(self):

        pass

    def should_light_be_on(self, current_time=None):

        pass

    def set_interval_minutes(self, minutes):

        pass

    def set_confidence_threshold(self, threshold):

        pass

    def _add_schedule_accuracy_features(self):

        pass
    
    def train_model(self, days_history=30):
        """Train the LightGBM model with recent historical data."""

        """Predict the likelihood of activity for a given timestamp."""
        pass
    
    def _create_prediction_features(self, timestamp):
        """Create a feature vector for a single timestamp."""

        pass