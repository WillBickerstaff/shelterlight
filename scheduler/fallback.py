"""scheduler.fallback.py.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Fallback schedule generator for use
             when model confidence is weak.
Author: Will Bickerstaff
Version: 0.1
"""

import os
import logging
import pytz
import pandas as pd
import datetime as dt
from typing import Optional
from scheduler.base import SchedulerComponent
from lightlib.config import ConfigLoader
from lightlib.persist import PersistentData


class Fallback(SchedulerComponent):
    """Fallback schedule generator using a CSV time block definition."""

    def __init__(self):
        super().__init__()
        self.local_tz = pytz.timezone(
            PersistentData().local_timezone_zone or "UTC")

    def generate_schedule(self, date: dt.date) -> dict[int, dict]:
        """Generate a full fallback schedule for the given date.

        Reads the fallback schedule file (CSV) and applies any matching blocks
        (either for the specific weekday or ANY). Time blocks defined in local
        time are converted to UTC. Matching intervals are marked as ON, others
        as OFF.

        Parameters
        ----------
        date : datetime.date
            The date for which to generate the fallback schedule.

        Returns
        -------
        dict[int, dict]
            A dictionary of interval number -> {start, end, prediction}
            where prediction is 1 (ON) or 0 (OFF).
        """
        df = self._load_schedule_dataframe(date)
        if df.empty:
            logging.warning("No fallback schedule entries found for %s",
                            date)
            return {}

        on_intervals = self._expand_rows_to_intervals(df, date)
        return self._build_full_schedule(on_intervals, date)

    def _load_schedule_dataframe(self, date: dt.date) -> pd.DataFrame:
        """Load the fallback schedule CSV and filter for matching weekdays.

        Parameters
        ----------
        date : datetime.date
            The target date used to match against the 'day' column in the CSV.

        Returns
        -------
        pd.DataFrame
            A filtered DataFrame containing only rows where the day is 'ANY' or
            matches the target weekday (e.g. 'Monday').
        """
        fallback_file = ConfigLoader().fallback_schedule_file
        if not os.path.exists(fallback_file):
            logging.error("Fallback schedule file not found: %s",
                          fallback_file)
            return pd.DataFrame()

        df = pd.read_csv(fallback_file, skipinitialspace=True)
        weekday = date.strftime("%A")
        return df[df["day"].str.strip().isin(["ANY", weekday])]

    def _expand_rows_to_intervals(self, df: pd.DataFrame,
                                  date: dt.date) -> set[int]:
        """Convert each local on_time + duration block to UTC interval numbers.

        For each matching row in the fallback CSV, this method:
            - Parses the on_time and duration
            - Constructs the local datetime block
            - Converts to UTC using the persisted local timezone
            - Identifies all intervals covered by that block
            - Returns a set of those interval indices

        Parameters
        ----------
        df : pd.DataFrame
            The filtered fallback schedule DataFrame (rows for this date).
            date : datetime.date
            The target schedule date.

        Returns
        -------
        set[int]
            A set of interval indices where the light should be ON.
        """
        on_intervals = set()
        interval_minutes = self.interval_minutes

        for _, row in df.iterrows():
            try:
                # Parse on_time as local time (HH:MM)
                on_time = dt.datetime.strptime(row["on_time"].strip(),
                                               "%H:%M").time()

                # Parse duration into timedelta
                duration_parts = row["duration"].strip().split(":")
                duration = dt.timedelta(hours=int(duration_parts[0]),
                                        minutes=int(duration_parts[1]))

                # Combine date and on_time, then localize to correct timezone
                local_start = dt.datetime.combine(date, on_time)
                start_dt = self.local_tz.localize(
                    local_start).astimezone(dt.timezone.utc)
                end_dt = start_dt + duration

                # Walk through each interval the block spans and mark as active
                current = start_dt
                while current < end_dt:
                    interval = (current.hour * 60 +
                                current.minute) // interval_minutes
                    on_intervals.add(interval)
                    current += dt.timedelta(minutes=interval_minutes)
            except Exception as e:
                logging.error("Invalid fallback row %s: %s", row, e)

        return on_intervals

    def _build_full_schedule(self, on_intervals: set[int],
                             date: dt.date) -> dict[int, dict]:
        """Construct a full-day UTC schedule by marking intervals as ON or OFF.

        Builds a complete 24-hour schedule by generating all interval blocks
        (based on the configured interval length) and marking each as either ON
        (prediction=1) or OFF (prediction=0), depending on whether the interval
        is in the `on_intervals` set.

        Parameters
        ----------
        on_intervals : set[int]
            Set of interval indices where the light should be ON.
            date : datetime.date
            The schedule date (used to calculate each interval's timestamp).

        Returns
        -------
        dict[int, dict]
            A dictionary mapping interval number -> {
                "start": datetime (UTC),
                "end": datetime (UTC),
                "prediction": 1 if ON, else 0
                }
        """
        schedule = {}
        interval_minutes = self.interval_minutes
        total_intervals = 1440 // interval_minutes

        for i in range(total_intervals):
            # Calculate the interval UTC start & end time.
            start = dt.datetime.combine(
                date, dt.time(0, 0), tzinfo=dt.timezone.utc) + \
                dt.timedelta(minutes=i * interval_minutes)
            end = start + dt.timedelta(minutes=interval_minutes)

            schedule[i] = {
                "start": start,
                "end": end,
                "prediction": 1 if i in on_intervals else 0
            }

        logging.info("Generated fallback schedule for %s with "
                     "%d ON intervals.",
                     date.isoformat(), len(on_intervals))
        return schedule

    def best_historic_method(self, date: dt.date) -> Optional[dict[int, dict]]:
        """Retrieve the most accurate past schedule for the same weekday.

        Searches back over the configured number of fallback history days to
        find previous schedules that occurred on the same weekday as the given
        `date`. It then evaluates their accuracy based on prediction
        correctness and selects the best-performing day.

        If no prior schedules exist or none match the weekday, returns None.

        Parameters
        ----------
        date : datetime.date
            The date we want to generate a fallback for. Its weekday is used
            to match against historical schedules.

        Returns
        -------
        Optional[dict[int, dict]]
            The best schedule (in interval format) for the matched weekday,
            or None if no valid fallback could be found.
        """
        history_days = ConfigLoader().fallback_history_days
        start = date - dt.timedelta(days=history_days)
        end = date

        rows = self._query_historic_schedule_rows(start, end)
        if not rows:
            return None

        stats, schedules = self._aggregate_schedule_stats(rows, date.weekday())
        best_day = self._select_best_day(stats)

        if not best_day:
            logging.info("No suitable historic schedule found for weekday %s",
                         date.strftime("%A"))
            return None

        logging.info("Using fallback from %s with %.1f%% accuracy",
                     best_day,
                     100 * stats[best_day]["correct"]
                     / stats[best_day]["total"])

        return schedules[best_day]

    def _query_historic_schedule_rows(self,
                                      start: dt.date, end: dt.date) -> list:
        """Query the db for light schedule performance data over a date range.

        Retrieves all interval-level schedule entries from the light_schedules
        table between the specified start and end dates. These rows include
        correctness and error flags used for later accuracy evaluation.

        Parameters
        ----------
        start : datetime.date
            The start date (inclusive) of the query range.
        end : datetime.date
            The end date (exclusive) of the query range.

        Returns
        -------
        list
            A list of rows, where each row is:
                (date, interval_number, was_correct, false_positive,
                 false_negative)

        Notes
        -----
        If the query fails or no data exists, returns an empty list.
        """
        query = """
            SELECT date, interval_number, was_correct,
                false_positive, false_negative
            FROM light_schedules
            WHERE date >= %s AND date < %s
        """
        try:
            with self.db.conn.cursor() as cur:
                cur.execute(query, (start, end))
                return cur.fetchall()
        except Exception as e:
            logging.error("Failed to query historic schedules: %s", e)
            return []

    def _aggregate_schedule_stats(self, rows: list, target_weekday: int
                                  ) -> tuple[dict, dict]:
        """Summarize past schedule performance by date for the target weekday.

        Filters the provided schedule rows to only include entries from the
        same weekday (e.g., Tuesday). It then:
            - Aggregates false positives, false negatives, and correct
              predictions per date
            - Reconstructs the full interval-level schedule for each day

        This data is used to identify the most reliable past day for fallback.

        Parameters
        ----------
        rows : list
            A list of tuples from the database containing:
                (date, interval_number, was_correct, false_positive,
                 false_negative)

        target_weekday : int
            The weekday to match against (0=Monday, 6=Sunday).

        Returns
        -------
        tuple[dict, dict]
            - stats: {date -> {'fp', 'fn', 'correct', 'total'}}
            - schedules: {date -> {interval_number -> {start, end,
                                                       prediction}}}
        """
        from collections import defaultdict
        interval_minutes = self.interval_minutes
        stats = defaultdict(
            lambda: {"fp": 0, "fn": 0, "correct": 0, "total": 0})
        schedules = defaultdict(dict)

        for sched_date, interval, was_correct, fp, fn in rows:
            if sched_date.weekday() != target_weekday:
                continue

            # Update performance stats
            stat = stats[sched_date]
            stat["fp"] += int(fp)
            stat["fn"] += int(fn)
            stat["correct"] += int(was_correct)
            stat["total"] += 1

            # Reconstruct the schedule structure for fallback use
            start_dt = dt.datetime.combine(
                sched_date, dt.time(0, 0), tzinfo=dt.timezone.utc
            ) + dt.timedelta(minutes=interval * interval_minutes)

            schedules[sched_date][interval] = {
                "start": start_dt,
                "end": start_dt + dt.timedelta(minutes=interval_minutes),
                "prediction": 1 if was_correct else 0
            }

        return stats, schedules

    def _select_best_day(self, stats: dict) -> Optional[dt.date]:
        """Identify the day with the highest accuracy from aggregated stats.

        Selects the date with the highest (correct / total) ratio.
        If no data is available, returns None.

        Parameters
        ----------
        stats : dict
            Dictionary of date -> performance summary, where each value
                includes: 'correct', 'fp', 'fn', 'total'

        Returns
        -------
        Optional[datetime.date]
            The date with the best overall prediction accuracy, or None if
            stats is empty.
        """
        if not stats:
            return None
        return max(
            stats.items(),
            key=lambda item: item[1]["correct"] / item[1]["total"]
            if item[1]["total"] else 0
        )[0]
