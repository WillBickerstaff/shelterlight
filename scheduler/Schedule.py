"""scheduler.schedule.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Generate daily schedules, train the learning model
Author: Will Bickerstaff
Version: 0.2
"""

import psycopg2
import pandas as pd
import datetime as dt
import logging
import time
from threading import Lock
from typing import Optional
from collections import OrderedDict
from lightlib.common import get_today, get_tomorrow, get_now, get_yesterday
from lightlib.common import sec_to_hms_str
from lightlib.db import DB
from lightlib.config import ConfigLoader
from scheduler.features import FeatureEngineer
from scheduler.model import LightModel
from scheduler.evaluation import ScheduleEvaluator
from scheduler.store import ScheduleStore
from scheduler.fallback import Fallback

def schedule_tostr(schedule_date: Optional[dt.date] = None) -> str:
    """Format a schedule for the given date.

    Generates a string formatted table representing the prediction
    sechdule for the given date

    Arguments
    ---------
    schedule_date: Optional[dt.date]
         the date the table is required for. Defaults to today
    """
    if schedule_date is None:
        schedule_date = get_today()

    db = DB()
    query = """
        SELECT date, start_time, end_time, prediction, confidence
        FROM light_schedules
        WHERE date = %(date)s
    """

    engine = db.get_alchemy_engine()
    schedule = pd.read_sql_query(
        query, engine, params={'date': schedule_date.isoformat()})
    sorted = schedule.sort_values(by=['start_time'])
    # Table heading
    lines = [
        f"UTC Schedule generated for {schedule_date.isoformat()}:\n",
        "Sched Date  | Start    | End      | State | Confidence",
        "-" * 59
    ]

    for r in sorted.itertuples():
        state = "ON" if r.prediction else "OFF"
        lines.append(
            f" {r.date.strftime('%Y-%m-%d')} |"
            f" {r.start_time.strftime('%H:%M')}    |"
            f" {r.end_time.strftime('%H:%M')}    |"
            f" {state:^5} | {r.confidence:.2f}"
        )

    return("\n" + "\n".join(lines))


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
        if hasattr(self, 'initialized'):
            return

        self.initialized = True

        # Core state
        self.model = None
        self.interval_minutes = 10
        self.min_confidence = ConfigLoader().confidence_threshold
        self.schedule_cache = OrderedDict()
        self.db = None
        self._warned_missing = None
        self.days_history = ConfigLoader().training_days_history

        self._initialize_components()

    def _initialize_components(self):
        self.set_db_connection()

        self.features = FeatureEngineer()
        self.model_engine = LightModel()
        self.evaluator = ScheduleEvaluator()
        self.store = ScheduleStore()
        self._apply_shared_config()

    def _apply_shared_config(self):
        shared = {
            "db": self.db,
            "interval_minutes": self.interval_minutes,
            "min_confidence": self.min_confidence,
            "schedule_cache": self.schedule_cache,
            "features": self.features
        }
        self.features.set_config(**shared)
        self.model_engine.set_config(**shared)
        self.evaluator.set_config(**shared)
        self.store.set_config(**shared)

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

    @staticmethod
    def progressive_history(max_days: Optional[int] = None) -> int:
        """Return the maximum available number of days for training.

        Allow the model to adjust its training history dynamically based on
        how much data is available in the activity log. Starts small and
        grows progressively up to a maximum.

        Returns
        -------
        int
            The number of days to use for training, capped at MAX_DAYS_HISTORY.
        """
        MAX_DAYS_HISTORY = max_days or ConfigLoader().training_days_history
        MIN_DAYS_HISTORY = 2    # Minimum to avoid meaningless tiny training

        try:
            # Check database connection
            db = DB()

            # Query for the oldest timestamp in activity_log
            query = "SELECT MIN(timestamp) FROM activity_log;"
            with db.conn.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                oldest_timestamp = result[0]

            if oldest_timestamp is None:
                # No data at all yet
                logging.warning(
                    "0 activity records found. Using minimum training window.")
                return MIN_DAYS_HISTORY

            today = get_now()
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

    def generate_daily_schedule(self, date):
        """Generate a light schedule for a date based on model predictions.

        Create a daily schedule of when lights should be turned on,
        make sure predictions only fall within darkness hours.

        Args
        ----
            date (str): The date for which the schedule is
                        generated (YYYY-MM-DD).

        Returns
        -------
            dict: A dictionary mapping time intervals to predicted activity.
        """
        # Validate input parameters
        try:
            schedule_date = dt.datetime.strptime(
                date, "%Y-%m-%d").date()
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
                minute=(i * self.interval_minutes) % 60),
                                tzinfo=dt.timezone.utc)
            for i in range(num_intervals)
        ]

        # Compute necessary features (includes interval_number correctly)
        df = self.features._create_base_features(df)

        if self.model_engine.model is None:
            logging.error("No trained model found. Cannot generate schedule.")
            return {}

        predictions, probabilities = self.model_engine._predict_schedule(df)

        return self._apply_fallback(schedule_date, df,
                                    predictions, probabilities)

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
            training_start = time.monotonic()
            date_tomorrow = get_tomorrow()
            with self._lock:
                # Evaluate yesterday's schedule accuracy
                self.evaluator.evaluate_previous_schedule(get_yesterday())
                # Retrain the model using updated accuracy data
                self.model_engine.train_model(
                    days_history=LightScheduler.progressive_history())
                training_end = time.monotonic()
                # Generate a new schedule for tomorrow
                new_schedule = self.generate_daily_schedule(
                    date_tomorrow.strftime("%Y-%m-%d"))
                # Storage of the generated schedule in the database & cache
                # is completed by `self.generate_daily_schedule' with its
                # final call to `self.store_schedule'
                if not new_schedule:
                    # Empty schedule
                    logging.warning("Empty schedule generated for %s",
                                    date_tomorrow)
                else:
                    # Log the successful update and return the new schedule
                    logging.info("Successfully updated schedule for %s",
                                 date_tomorrow)
                    self._log_schedule(date_tomorrow)

                final_time = time.monotonic()
                training_duration = training_end - training_start
                schedule_duration = final_time - training_end
                total_duration = final_time - training_start
                time_str = sec_to_hms_str(total_duration)

                logging.info(f"Training and schedule generation completed.\n"
                             f"\t{time_str}\n"
                             f"\t           Training duration: "
                             f"{int(training_duration)}s\n"
                             f"\tSchedule Generation duration: "
                             f"{int(schedule_duration)}s\n"
                             f"\t-----------------------------------\n"
                             f"\t                  Total time: "
                             f"{int(total_duration)}s\n")

                return new_schedule

        except Exception as e:
            logging.error("Failed to update daily schedule: %s", e)
            raise e
            return None

    def should_light_be_on(
            self, check_time: Optional[dt.datetime] = None) -> bool:
        """Determine if the lights should be on at a given moment.

        Args
        ----
            check_time (Optional[dt.datetime]):
                Defaults to current UTC time if not provided.
                If the check time is outside the current schedule window,
                a direct DB query is used to avoid polluting the cache.

        Returns
        -------
            bool: True if lights should be ON, False otherwise.

        Loads both yesterday's and today's schedules to ensure
        correct detection of early-morning lighting intervals.
        """
        now = check_time or get_now()
        interval_number = (now.hour * 60 + now.minute) // self.interval_minutes
        sched_date = now.date()
        if sched_date in {get_yesterday(), get_today(), get_tomorrow()}:
            schedule = self.store.get_current_schedule()
        else:
            schedule = self.store.get_schedule(sched_date)

        key = (sched_date, interval_number)
        return schedule.get(key, {}).get("prediction", 0) == 1

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

    def _log_schedule(self, schedule_date: dt.date) -> None:
        """Log the generated UTC schedule as a fomatted table (DEBUG only).

        Logs each scheduled interval where the light is predicted to be ON,
        along with its start and end time and associated confidence score.
        The output is formatted as a table and sorted chronologically by ON
        time.

        Logging only occurs if the active log level is INFO. If the schedule
        is empty, a warning is logged instead.

        Args
        ----
        schedule_date : datetime.date
            The date of the schedule required.
        """
        if not logging.getLogger().isEnabledFor(logging.INFO):
            return  # Skip formatting unless info level is enabled

        logging.info(schedule_tostr(schedule_date))

    def _calculate_confidence_coverage(self,
                                       probabilities: list[float]) -> float:
        """Calculate the fraction of intervals which are confident.

        Confidence is defined by the configuration option certainty_range:
            - Confidently OFF: prediction <= certainty_range
            - Confidently ON: prediction >= 1.0 - certainty_range

        Parameters
        ----------
        probabilities : list[float]
            Model output probabilities for each interval.

        Returns
        -------
        float
            The fraction of confident intervals.
        """
        certainty_range = ConfigLoader().fallback_certainty_range
        lower_bound = certainty_range
        upper_bound = 1.0 - certainty_range

        confident_intervals = sum(
            (p <= lower_bound) or (p >= upper_bound) for p in probabilities)
        coverage = confident_intervals / len(probabilities)
        logging.info("Schedule contains %d confident intervals",
                     confident_intervals)
        return coverage

    def _apply_fallback(self,
                        schedule_date: dt.date,
                        df: pd.DataFrame,
                        predictions: list[int],
                        probabilities: list[float]
                        ) -> dict[int, dict]:
        """
        Evaluate model prediction confidence and apply fallback strategy.

        This method compares the model's output probabilities against the
        configured minimum confidence threshold. If none of the predictions
        exceed the threshold, it applies a fallback strategy based on the
        `[FALLBACK]` configuration.

        The fallback resolution order depends on `fallback_action`:
            - "history": Try the most accurate past schedule for the same
                         weekday, falling back to the configured schedule file
                         if not found.
            - "schedule": Use the configured fallback schedule file directly.
            - "none": Always use the model output, even if confidence is low.

        If all fallback methods fail, the low-confidence model output is
        used as-is.

        Parameters
        ----------
        schedule_date : datetime.date
            The target date for the schedule being generated.

        df : pandas.DataFrame
            The feature DataFrame used during prediction.

        predictions : list[int]
            Binary predictions from the model for each interval.

        probabilities : list[float]
            Corresponding prediction confidences (0.0–1.0) for each interval.

        Returns
        -------
        dict[int, dict]
            The final schedule, either stored from model predictions or
            fallback.
        """
        min_coverage = ConfigLoader().fallback_min_coverage
        coverage = self._calculate_confidence_coverage(probabilities)
        logging.info("Model confident interval coverage: %.3f, "
                     "minimum is: %.3f", coverage, min_coverage)
        confidence_ok = coverage >= min_coverage
        fallback_mode = ConfigLoader().fallback_action

        if confidence_ok or fallback_mode == "none":
            return self.store.store_schedule(schedule_date, df,
                                             predictions, probabilities)

        logging.warning("Model confidence coverage is too low. "
                        "Applying fallback strategy: %s",
                        fallback_mode)

        # Instantiate fallback helper locally
        fallback = Fallback()
        fallback.set_config(
            db=self.db,
            interval_minutes=self.interval_minutes,
            schedule_cache=self.schedule_cache,
            features=self.features
        )

        fallback_schedule = None
        if fallback_mode == "history":
            fallback_schedule = fallback.best_historic_method(schedule_date)
            if not fallback_schedule:
                fallback_schedule = fallback.generate_schedule(schedule_date)

        elif fallback_mode == "schedule":
            fallback_schedule = fallback.generate_schedule(schedule_date)

        if fallback_schedule:
            return self.store.store_fallback(schedule_date, fallback_schedule)

        logging.warning(
            "Fallback failed. Using low-confidence model schedule.")
        return self.store.store_schedule(schedule_date, df,
                                         predictions, probabilities)
