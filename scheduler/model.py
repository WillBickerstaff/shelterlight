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
from .synthetic_days import generate_synthetic_days
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

    def _split_train_validation(self, df: pd.DataFrame,
                                feature_cols: list[str],
                                min_on_fraction: float = 0.05
                                ) -> tuple[pd.DataFrame, pd.DataFrame,
                                           pd.Series, pd.Series]:
        """Split data into training and validation sets.

        If the data has low ON rate, disbles validation and uses all data for
        training.

        Returns
        -------
            tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]
                x_train, x_val, y_train, y_val
        """
        df_sorted = df.sort_values("timestamp")
        y_all = (df_sorted['activity_pin'] > 0).astype(int)
        if len(df_sorted) < 1000:
            logging.warning("Validation disabled. Dataset too small "
                            "(%d rows).", len(df_sorted))
            return (df_sorted[feature_cols], pd.DataFrame(),
                    y_all, pd.Series(dtype=int))

        split_idx = int(len(df_sorted) * 0.8)
        x_train = df_sorted.iloc[:split_idx][feature_cols]
        y_train = y_all.iloc[:split_idx]
        x_val = df_sorted.iloc[split_idx:][feature_cols]
        y_val = y_all.iloc[split_idx:]

        train_on_ratio = y_train.mean()
        val_on_ratio = y_val.mean()

        logging.info("Training ON ratio: %.3f (%d ONs)",
                     train_on_ratio, y_train.sum())
        logging.info("Validation ON ratio: %.3f (%d ONs)",
                     val_on_ratio, y_val.sum())

        if not ConfigLoader().enable_model_validation or \
           train_on_ratio < min_on_fraction or \
           val_on_ratio < min_on_fraction:
            logging.warning("Validation disabled. Either explicitly in config "
                            "or there are insufficient ONs in "
                            "train or val set.")
            return (df_sorted[feature_cols], pd.DataFrame(),
                    y_all, pd.Series(dtype=int))

        logging.debug("Validation enabled. Splitting at index %d", split_idx)
        return x_train, x_val, y_train, y_val

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
            self.model = None
            return

        df_activity, df_schedules = fetched_data
        if df_activity.empty:
            logging.warning("No activity data rows found, "
                            "skipping model training.")
            self.model = None
            return

        df = self.features._create_base_features(df_activity)
        df = self._add_schedule_accuracy_features(df, df_schedules)

        # 2-Select features for training
        feature_cols = fset.FeatureSetManager.get_columns(self.feature_set)

        # Sort by timestamp for time-based split
        x_train, x_val, y_train, y_val = self._split_train_validation(
            df, feature_cols, ConfigLoader().min_on_fraction)

        # Ensure numeric types
        y_train = pd.to_numeric(y_train, errors='coerce').fillna(0).astype(int)
        y_val = pd.to_numeric(y_val, errors='coerce').fillna(0).astype(int)

        num_on = (y_train == 1).sum()
        num_off = (y_train == 0).sum()

        # Boost ONs if needed (for sparse datasets)
        if num_on > 0 and ConfigLoader().boost_enable:
            on_boost = ConfigLoader().ON_boost
            scale_pos_weight = num_off / (num_on / on_boost)
            self.model_params["scale_pos_weight"] = scale_pos_weight
            logging.info("Set scale_pos_weight to %.3f based on class "
                         "imbalance. ON_Boost is at: %.3f",
                         scale_pos_weight, on_boost)
        else:
            self.model_params["scale_pos_weight"] = 1.0
            logging.warning("No positive samples found or ON boost disabled. "
                            ". scale_pos_weight set to 1.0")

        self.model_params["min_data_in_leaf"] = ConfigLoader().min_data_in_leaf
        # 3-Define the target variable
        y = (df['activity_pin'] > 0).astype(int)
        label_dist = pd.Series(y).value_counts().to_dict()
        logging.debug("y_train distribution: %s", label_dist)
        logging.debug("Sample activity_pin values:\n%s",
                      df[['timestamp', 'activity_pin']].head(10))
        # 4-Create the dataset
        train_data = lgb.Dataset(x_train, label=y_train)

        # 5-Train the model
        if not x_val.empty:
            val_data = lgb.Dataset(x_val, label=y_val)
            self._train_with_data(train_data=train_data,
                                  val_data=val_data,
                                  feature_cols=feature_cols)
        else:
            self._train_with_data(train_data=train_data,
                                  val_data=None,
                                  feature_cols=feature_cols)

    def _train_with_data(self,
                         train_data: lgb.Dataset,
                         val_data: lgb.Dataset | None,
                         feature_cols: list[str]) -> None:
        """Train LightGBM model with optional validation set.

        Parameters
        ----------
        train_data : lgb.Dataset
            The training dataset.
        val_data : lgb.Dataset | None
            The validation dataset. If None, no early stopping is applied.
        feature_cols : list[str]
            Feature column names (used for logging importance).
        """
        use_validation = val_data is not None
        early_stopping_rounds = ConfigLoader().early_stopping_rounds
        boost_rounds = ConfigLoader().model_boost_rounds
        try:
            if use_validation:
                self.model = lgb.train(
                    self.model_params,
                    train_data,
                    num_boost_round=boost_rounds,
                    valid_sets=[train_data, val_data],
                    valid_names=["train", "valid"],
                    early_stopping_rounds=early_stopping_rounds
                )
            else:
                self.model = lgb.train(
                    self.model_params,
                    train_data,
                    num_boost_round=boost_rounds,
                    valid_sets=[train_data]
                                                            )
        except TypeError:
            # Fallback for older LightGBM versions
            logging.warning(
                "LightGBM Unsupported kwarg early_stopping_rounds. "
                "Consider upgrading LightGBM. "
                "Falling back to callbacks API")

            if use_validation:
                self.model = lgb.train(
                    self.model_params,
                    train_data,
                    num_boost_round=boost_rounds,
                    valid_sets=[train_data, val_data],
                    valid_names=["train", "valid"],
                    callbacks=[lgb.early_stopping(
                        stopping_rounds=early_stopping_rounds)]
                )
            else:
                self.model = lgb.train(
                    self.model_params,
                    train_data,
                    num_boost_round=boost_rounds,
                    valid_sets=[train_data]
                )

        # Log feature importance
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

        feature_cols = fset.FeatureSetManager.get_columns(self.feature_set)

        # Drop polluting non-feature columns BEFORE selecting feature columns
        drop_cols = ['date', 'timestamp']
        df = df.drop(columns=[col for col in drop_cols if col in df.columns])

        # Always slice the DataFrame cleanly
        x_predict = df[feature_cols].copy()
        y_pred = self.model.predict(x_predict)
        probabilities = self.model.predict(x_predict, raw_score=False)
        predictions = (y_pred >= self.min_confidence).astype(int)

        logging.debug("ON confidence threshold is: %.2f", self.min_confidence)
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

            if df_schedules.empty:
                logging.warning("No schedule accuracy data found. "
                                "Proceeding with activity data only.")
                # Create a dummy schedules dataframe
                df_schedules = pd.DataFrame(columns=[
                    "date", "interval_number", "was_correct",
                    "false_positive", "false_negative", "confidence",
                    "recency"])

            if ConfigLoader().synth_days:
                # Generate synthetic days to fill gaps in activity data
                df_synthetic = generate_synthetic_days(
                    start_date=df_intervals["date"].min(),
                    end_date=df_intervals["date"].max(),
                    db=self.db,
                    target_columns=list(df_intervals.columns),
                    activity_only=True)

                if not df_synthetic.empty:
                    df_intervals = pd.concat([df_intervals, df_synthetic],
                                             ignore_index=True, axis=0)
                    logging.info("Added %d synthetic intervals for %d "
                                 "missing days.", len(df_synthetic),
                                 df_synthetic["date"].nunique())
                    logging.debug("Synthetic dates generated: %s",
                                  [d.isoformat() for d in
                                  sorted(df_synthetic["date"].unique())])

            logging.info(f"Training set: {len(df_intervals)} intervals, "
                         f"{sum(df_intervals['activity_pin'])} with activity")

        except Exception as e:
            logging.error("Error retrieving training data: %s", e,
                          exc_info=True)
            raise

        # Return the complete dataset
        return df_intervals, df_schedules

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
        all_data = []
        current_date = start.date()
        while current_date <= end.date():
            df = self.db.load_activity_for_date(current_date)
            if not df.empty:
                converted = pd.to_datetime(df["timestamp"], errors="coerce")
                invalid_count = converted.isna().sum()
                if invalid_count > 0:
                    logging.warning("Dropped %d rows with invalid timestamps"
                                    " on %s", invalid_count, current_date)
                df = df[converted.notna()].copy()
                df["timestamp"] = converted[converted.notna()]
                all_data.append(df)
            current_date += dt.timedelta(days=1)

        if not all_data:
            # If there is nothing, return an empty list
            return []

        df_all = pd.concat(all_data, ignore_index=True)
        # Filter to exact start/end (full days are retrieved)
        return df_all.loc[(df_all["timestamp"] >= start) &
                          (df_all["timestamp"] < end), "timestamp"
                          ].tolist()

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
        df['was_correct'] = df['was_correct'].astype(float)
        df['confidence'] = df['confidence'].astype(float)
        df['false_positive'] = df['false_positive'].astype('Int64')
        df['false_negative'] = df['false_negative'].astype('Int64')

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
