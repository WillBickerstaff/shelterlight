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
        self.local_tz = pytz.timezone(PersistentData().local_timezone or "UTC")

    def generate_schedule(self, date: dt.date) -> dict[int, dict]:
        """Return a fallback schedule for the given date."""
        df = self._load_schedule_dataframe(date)
        if df.empty:
            logging.warning("No fallback schedule entries found for %s",
                            date)
            return {}

        on_intervals = self._expand_rows_to_intervals(df, date)
        return self._build_full_schedule(on_intervals, date)

    def _load_schedule_dataframe(self, date: dt.date) -> pd.DataFrame:
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
        """Convert on_time + duration blocks to interval numbers."""
        on_intervals = set()
        interval_minutes = self.interval_minutes

        for _, row in df.iterrows():
            try:
                on_time = dt.datetime.strptime(row["on_time"].strip(),
                                               "%H:%M").time()
                duration_parts = row["duration"].strip().split(":")
                duration = dt.timedelta(hours=int(duration_parts[0]),
                                        minutes=int(duration_parts[1]))
                local_start = dt.datetime.combine(date, on_time)
                start_dt = self.local_tz.localize(
                    local_start).astimezone(dt.timezone.utc)
                end_dt = start_dt + duration

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
        """Build a complete schedule for the day with ON/OFF states."""
        schedule = {}
        interval_minutes = self.interval_minutes
        total_intervals = 1440 // interval_minutes

        for i in range(total_intervals):
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
        """Return the most accurate past schedule for the same weekday."""
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
        from collections import defaultdict
        interval_minutes = self.interval_minutes
        stats = defaultdict(
            lambda: {"fp": 0, "fn": 0, "correct": 0, "total": 0})
        schedules = defaultdict(dict)

        for sched_date, interval, was_correct, fp, fn in rows:
            if sched_date.weekday() != target_weekday:
                continue
            stat = stats[sched_date]
            stat["fp"] += int(fp)
            stat["fn"] += int(fn)
            stat["correct"] += int(was_correct)
            stat["total"] += 1

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
        if not stats:
            return None
        return max(
            stats.items(),
            key=lambda item: item[1]["correct"] / item[1]["total"]
            if item[1]["total"] else 0
        )[0]
