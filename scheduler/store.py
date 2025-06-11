"""scheduler.store.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Schedule caching and persistent storage (PostgreSQL)
             for predicted lighting intervals.

Author: Will Bickerstaff
Version: 0.1
"""

import logging
import datetime as dt
import pandas as pd
import numpy as np
import psycopg2
import lightlib.common as llc
from scheduler.base import SchedulerComponent


class ScheduleStore(SchedulerComponent):
    """Store and retrieve lighting schedules from cache and PostgreSQL.

    This component handles:
    - Storing predicted lighting schedules in the database
    - Caching schedules in memory to reduce database queries
    - Retrieving schedules on demand for decision-making
    - Updating schedules with predictions and confidence scores

    Inherits from SchedulerComponent to access shared configuration
    including database connection and interval settings.
    """

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
            start_dt = dt.datetime.combine(
                schedule_date, dt.time(0, 0), tzinfo=dt.timezone.utc) + \
                dt.timedelta(minutes=interval * self.interval_minutes)
            end_dt = start_dt + dt.timedelta(minutes=self.interval_minutes)

            schedule[interval] = {
                "start": start_dt,
                "end": end_dt,
                "prediction": bool(predictions[idx]),
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
                                                     prediction, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, interval_number) DO UPDATE
                        SET prediction = EXCLUDED.prediction,
                        confidence = EXCLUDED.confidence;
                        """, (schedule_date, int(interval), info["start"],
                              info["end"], bool(info["prediction"]),
                              float(info.get("confidence", 0.5))))

            self.db.conn.commit()  # Commit transaction
            logging.info(f"Stored schedule for {schedule_date} in database.")

        except psycopg2.DatabaseError as e:
            self.db.conn.rollback()  # Rollback on failure
            logging.error(f"Failed to store schedule for {schedule_date}: {e}")

        return schedule

    def _purge_old_cache_entries(self):
        """Keep only, yesterday, today & tomorrow in schedule cache."""
        valid_dates = {
            llc.get_yesterday(),
            llc.get_today(),
            llc.get_tomorrow()
        }

        for cached_date in list(self.schedule_cache.keys()):
            if cached_date not in valid_dates:
                del self.schedule_cache[cached_date]

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
        if target_date in self.schedule_cache:
            return self.schedule_cache[target_date]
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
                schedule[(target_date, row[0])] = {
                    "start": row[1],
                    "end": row[2],
                    "prediction": row[3],
                    "confidence": row[4] if row[4] is not None else 0.5
                }
            # If retrieved from the database, store it in cache
            self.schedule_cache[target_date] = schedule
            # Prevent the cache from infinitely growing
            self._purge_old_cache_entries()

            return schedule

        except psycopg2.DatabaseError as e:
            logging.error(
                f"Failed to retrieve schedule for {target_date}: {e}")
            return {}

    def get_current_schedule(self) -> dict:
        """Get the cached schedule or load it from the database if needed.

        Returns
        -------
            dict: Combined schedule for yesterday & today.
        """
        # We must include yesterday, depending on how intervals
        # are setup times just after midnight may be included
        # in yesterdays schedule
        sched_yesterday = self.get_schedule(llc.get_yesterday())
        sched_today = self.get_schedule(llc.get_today())

        return sched_yesterday | sched_today

    def store_fallback(self,
                       schedule_date: dt.date,
                       schedule: dict[int, dict]) -> dict[int, dict]:
        """Store a fallback schedule directly into the database.

        This version accepts a fully constructed schedule dictionary where each
        key is an interval number and the value contains start, end, and
        prediction.

        Parameters
        ----------
        schedule_date : datetime.date
            The date the schedule applies to.

        schedule : dict[int, dict]
            A dictionary of interval_number -> {start, end, prediction}

        Returns
        -------
        dict[int, dict]
            The stored schedule (same as input).
        """
        if not self.db or not self.db.conn or self.db.conn.closed:
            logging.error(
                "No valid database connection to store fallback schedule.")
            return {}

        try:
            with self.db.conn.cursor() as cur:
                for interval, entry in schedule.items():
                    cur.execute("""
                        INSERT INTO light_schedules
                            (date, interval_number, start_time, end_time,
                             prediction)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (date, interval_number) DO UPDATE
                        SET prediction = EXCLUDED.prediction;
                        """, (
                            schedule_date,
                            int(interval),
                            entry["start"],
                            entry["end"],
                            bool(entry["prediction"])
                        ))
            self.db.conn.commit()
            logging.info("Stored fallback schedule for %s with %d intervals.",
                         schedule_date, len(schedule))
            return schedule

        except Exception as e:
            logging.error("Failed to store fallback schedule: %s", e,
                          exc_info=True)
            self.db.conn.rollback()
            return {}
