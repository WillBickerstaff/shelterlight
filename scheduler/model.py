"""scheduler.model.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: LightGBM model training and prediction for light scheduling.
             Uses recent activity and schedule accuracy to learn patterns.

Author: Will Bickerstaff
Version: 0.1
"""
import lightgbm as lgb  # https://lightgbm.readthedocs.io/en/stable/
import logging
import pandas as pd
import numpy as np
import datetime as dt
import scheduler.feature_sets as fset
from scheduler.base import SchedulerComponent
from lightlib.config import ConfigLoader
from lightlib.common import get_now

class LightModel(SchedulerComponent):
    """Train and apply a LightGBM model to predict light activation needs.

    This class handles:
    - Retrieving and preparing training data from the activity log
    - Incorporating historical schedule accuracy into feature engineering
    - Training a LightGBM model to predict activity
    - Generating predictions and probabilities for scheduling

    Inherits from SchedulerComponent to access shared configuration,
    including database connection, schedule intervals, and thresholds.
    """

    def __init__(self):
        super().__init__()
        self.model = None
        self.set_feature_set(ConfigLoader().model_features)
        self.model_params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1
        }

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
        logging.info("Training with feature set %s", self.feature_set.name)
        #   1-Retrieve & prepare training data
        fetched_data = self._prepare_training_data(days_history)
        # If there is no training data then exit
        if fetched_data is None:
            logging.warning(
                "No training data available, skipping model training")
            return

        df_activity, df_schedules = fetched_data
        df = self.features._create_base_features(df_activity)
        df = self._add_schedule_accuracy_features(df, df_schedules)

        # 2-Select features for training
        feature_cols = fset.FeatureSetManager.get_columns(self.feature_set)
        x = df[feature_cols]
        # 3-Define the target variable
        y = (df['activity_pin'] > 0).astype(int)
        label_dist = pd.Series(y).value_counts().to_dict()
        logging.debug("y_train distribution: %s", label_dist)
        logging.debug("Sample activity_pin values:\n%s",
                      df[['timestamp', 'activity_pin']].head(10))
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
        logging.debug("min_confidence in model: %.2f", self.min_confidence)

        if self.model is None:
            logging.error("No trained model found. Cannot make predictions.")
            return np.array([])

        feature_cols = fset.FeatureSetManager.get_columns(self.feature_set)

        # Drop polluting non-feature columns BEFORE selecting feature columns
        drop_cols = ['date', 'timestamp']
        df = df.drop(columns=[col for col in drop_cols if col in df.columns])

        # Always slice the DataFrame cleanly
        x_predict = df[feature_cols].copy()
        y_pred = self.model.predict(x_predict)
        probabilities = self.model.predict(x_predict, raw_score=False)
        predictions = (y_pred >= self.min_confidence).astype(int)

        logging.debug("min_confidence in model: %.2f", self.min_confidence)
        logging.debug("Prediction probabilities: %s", probabilities.tolist())
        logging.debug("Binary predictions: %s", predictions.tolist())

        return predictions, probabilities

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
        # Don't do anything if the DB connection is not established
        if self.db is None or self.db.conn.closed:
            logging.warning("DB connection not established, can't train")
            return None

        try:
            end_time = get_now()
            start_time = end_time - dt.timedelta(days=days_history)

            df_intervals = self._build_interval_grid(start_time, end_time)
            activity_ts = self._load_activity_data(start_time, end_time)
            df_intervals = self._assign_activity_flags(
                df_intervals, activity_ts)
            df_schedules = self._load_schedule_data(start_time, end_time)
            df_intervals, df_schedules = self._filter_no_activity_days(
                df_intervals, df_schedules)

            logging.info(f"Training set: {len(df_intervals)} intervals, "
                         f"{sum(df_intervals['activity_pin'])} with activity")

        except Exception as e:
            logging.error("Error retrieving training data: %s", e,
                          exc_info=True)
            raise

        # Return the complete dataset
        return df_intervals, df_schedules

    def _filter_no_activity_days(self,
                                 df_intervals: pd.DataFrame,
                                 df_schedules: pd.DataFrame
                                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Filter out dates with no recorded activity from training data.

        Args
        ----
            df_intervals (DataFrame): Interval-level data with
                'activity_pin' column
            df_schedules (DataFrame): Schedule accuracy data by date

        Returns
        -------
            Tuple of filtered (df_intervals, df_schedules)
        """
        activity_by_day = df_intervals.groupby("date")["activity_pin"].sum()
        active_dates = activity_by_day[activity_by_day > 0].index

        filtered_intervals = df_intervals[
            df_intervals["date"].isin(active_dates)]
        filtered_schedules = df_schedules[
            df_schedules["date"].isin(active_dates)]

        logging.info("Filtered out %d no-activity days; %d days retained.",
                     len(activity_by_day) - len(active_dates),
                     len(active_dates))
        return filtered_intervals, filtered_schedules

    def _load_schedule_data(self, start: dt.datetime,
                            end: dt.datetime) -> pd.DataFrame:
        """Load light schedule evaluation data from the database.

        Args
        ----
            start (datetime): Start of the date range (inclusive)
            end (datetime): End of the date range (exclusive)

        Returns
        -------
            DataFrame containing columns:
                - date
                - interval_number
                - was_correct
                - false_positive
                - false_negative
                - confidence
        """
        query = """
            SELECT
                date,
                interval_number,
                was_correct,
                false_positive,
                false_negative,
                confidence
            FROM light_schedules
            WHERE date >= %(start)s AND date < %(end)s
        """
        engine = self.db.get_alchemy_engine()
        return pd.read_sql_query(
            query, engine, params={'start': start.date(), 'end': end.date()})

    def _assign_activity_flags(self,
                               df_intervals: pd.DataFrame,
                               activity_ts: list[dt.datetime]) -> pd.DataFrame:
        """Assign activity flags to each interval.

        Args
        ----
            df_intervals (DataFrame): DataFrame of intervals with 'timestamp'
            activity_ts (list[datetime]): List of activity timestamps

        Returns
        -------
            DataFrame with an added 'activity_pin' column
        """
        interval_minutes = self.interval_minutes
        flags = []

        for ts in df_intervals['timestamp']:
            window_end = ts + dt.timedelta(minutes=interval_minutes)
            has_activity = any(ts <= a < window_end for a in activity_ts)
            flags.append(1 if has_activity else 0)

        df_intervals = df_intervals.copy()
        df_intervals['activity_pin'] = flags
        return df_intervals

    def _load_activity_data(self, start: dt.datetime,
                            end: dt.datetime) -> list[dt.datetime]:
        """Load activity timestamps from the database.

        Args
        ----
            start (datetime): Start of the date range
            end (datetime): End of the date range

        Returns
        -------
            List of datetime timestamps where activity occurred.
        """
        query = """
            SELECT timestamp FROM activity_log
            WHERE timestamp >= %(start)s AND timestamp < %(end)s
        """
        engine = self.db.get_alchemy_engine()
        df = pd.read_sql_query(query, con=engine,
                               params={'start': start, 'end': end})
        return df['timestamp'].tolist()

    def _build_interval_grid(self, start: dt.datetime,
                             end: dt.datetime) -> pd.DataFrame:
        """Build a DataFrame of time intervals between start and end.

        Args
        ----
            start (datetime): Start of the interval range
            end (datetime): End of the interval range

        Returns
        -------
            DataFrame with 'timestamp' and 'date' columns for each interval
        """
        interval_minutes = self.interval_minutes
        current = start.replace(minute=0, second=0, microsecond=0)
        timestamps = []

        while current < end:
            timestamps.append(current)
            current += dt.timedelta(minutes=interval_minutes)

        df = pd.DataFrame({'timestamp': timestamps})
        df['date'] = df['timestamp'].dt.date
        return df

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

    def set_feature_set(self, feature_set: fset.FeatureSet):
        """Set the feature set strategy for model training and prediction.

        Allows dynamic selection of which input features should be used by the
        LightGBM model. Useful for experimentation and evaluation of different
        feature subsets.

        Args
        ----
            feature_set (FeatureSet): The desired feature set configuration.
        """
        logging.debug("FeatureManager is using feature set %s",
                      feature_set.name)
        self.feature_set = feature_set
