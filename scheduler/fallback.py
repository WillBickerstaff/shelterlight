"""scheduler.fallback
7
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
import pandas as pd
import datetime as dt
from scheduler.base import SchedulerComponent
from lightlib.config import ConfigLoader

class Fallback(SchedulerComponent):
    """Fallback schedule generator using a CSV time block definition."""

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
                start_dt = dt.datetime.combine(date, on_time,
                                               tzinfo=dt.timezone.utc)
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
                date, dt.time(0, 0), tzinfo=dt.timezone.utc) +
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
