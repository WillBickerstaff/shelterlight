"""scheduler.evaluation.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Schedule accuracy evaluation for predicted light intervals,
             comparing scheduled activations with actual activity and
             updating performance metrics.

Author: Will Bickerstaff
Version: 0.1
"""
import logging
import datetime as dt
from lightlib.common import get_now
from scheduler.base import SchedulerComponent


class ScheduleEvaluator(SchedulerComponent):
    """Evaluate and update the accuracy of generated lighting schedules.

    Compares scheduled light intervals with recorded activity data
    to determine prediction correctness. It identifies:
    - True positives (correctly predicted activity)
    - False positives (light on without activity)
    - False negatives (missed activity without light)

    Results are written back to the database for use in model retraining.

    Inherits from SchedulerComponent to access shared config and database.
    """

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
                now = get_now()
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
