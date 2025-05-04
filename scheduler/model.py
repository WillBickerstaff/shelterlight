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
from scheduler.base import SchedulerComponent


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

    def __init__(self, feature_engineer):
        super().__init__()
        self.features = feature_engineer

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
        df = self.features._create_base_features(df_activity)
        df = self._add_schedule_accuracy_features(df, df_schedules)

        # 2-Select features for training
        feature_cols = self.features._get_feature_columns()
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

        feature_cols = self.features._get_feature_columns()

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
            logging.error("Error retrieving training data: %s", e,
                          exc_info=True)
            raise

        # Return the complete dataset
        return df_activity, df_schedules

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
