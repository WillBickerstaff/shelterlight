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

    def re_eval_all_schedules(self, start_date=None, end_date=None,
                              force=False):
        """Re-evaluate all previously generated light schedules.

        Parameters
        ----------
        start_date : datetime.date or None
                     First date to re-evaluate. If None, uses oldest
                     date in light_schedules.
        end_date : datetime.date or None
                   Last date to re-evaluate. If None, uses today.
        force : bool
                 If True, re-evaluates even if was_correct is already set.
        """
        try:
            with self.db.conn.cursor() as cur:
                # Get earliest and latest schedule dates
                if start_date is None:
                    cur.execute("SELECT MIN(date) FROM light_schedules;")
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        logging.warning("No schedule data found in database.")
                        return
                    start_date = row[0]

                if end_date is None:
                    end_date = dt.date.today()

                logging.info(f"Re-evaluating schedules from {start_date} to "
                             f"{end_date} (force={force})")

                current_date = start_date
                while current_date <= end_date:
                    # Skip dates that are already evaluated unless forced
                    if not force:
                        with self.db.conn.cursor() as cur:
                            cur.execute("""
                            SELECT COUNT(*) FROM light_schedules
                            WHERE date = %s AND was_correct IS NOT NULL;
                            """, (current_date,))

                            if cur.fetchone()[0] > 0:
                                logging.debug(
                                    f"Skipping {current_date}: "
                                    "already evaluated")
                                current_date += dt.timedelta(days=1)
                                continue

                    try:
                        self.evaluate_previous_schedule(current_date)
                    except Exception as e:
                        logging.warning(
                            f"Error evaluating {current_date}: {e}")

                    current_date += dt.timedelta(days=1)

                self.db.conn.commit()
                logging.info("Re-evaluation of past schedules completed.")

        except Exception as e:
            logging.error(f"failed to re-evaluate schedules: {e}",
                          exc_info=True)

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

        try:
            with self.db.conn.cursor() as cur:
                # Fetch predicted intervals
                cur.execute(schedule_query, (date,))
                scheduled_intervals = cur.fetchall()

                # Fetch activity timestamps
                cur.execute(activity_query, (date,))
                activity_timestamps = [row[0] for row in cur.fetchall()]

            # Initialize confusion matrix counters
            true_positives = false_positives = 0
            true_negatives = false_negatives = 0
            current_time = get_now()

            for interval_number, start_time, end_time, prediction in \
                    scheduled_intervals:
                # Don't evaluate intervals that haven't ended yet
                interval_end_dt = dt.datetime.combine(
                    date, end_time, tzinfo=dt.timezone.utc)
                if interval_end_dt > current_time:
                    continue

                interval_start_dt = dt.datetime.combine(
                    date, start_time, tzinfo=dt.timezone.utc)

                # Check for any activity that occurred during this interval
                activity_in_interval = any(
                    interval_start_dt <= ts < interval_end_dt for
                    ts in activity_timestamps)

                # Classify and update based on prediction vs. actual activity
                if prediction and activity_in_interval:
                    true_positives += 1
                    was_correct, is_false_positive, is_false_negative = \
                        True, False, False
                elif prediction and not activity_in_interval:
                    false_positives += 1
                    was_correct, is_false_positive, is_false_negative = \
                        False, True, False
                elif not prediction and activity_in_interval:
                    false_negatives += 1
                    was_correct, is_false_positive, is_false_negative = \
                        False, False, True
                else:
                    true_negatives += 1
                    was_correct, is_false_positive, is_false_negative = \
                        True, False, False

                with self.db.conn.cursor() as cur:
                    cur.execute("""
                    UPDATE light_schedules
                    SET was_correct = %s,
                        false_positive = %s,
                        false_negative = %s,
                        updated_at = NOW()
                    WHERE date = %s AND interval_number = %s
                    """, (was_correct,
                          is_false_positive,
                          is_false_negative,
                          date, interval_number))

            # Calculate and log metrics
            total_intervals = true_positives + false_positives + \
                false_negatives + true_negatives
            precision = true_positives / \
                (true_positives + false_positives) if \
                (true_positives + false_positives) else 0.0
            recall = true_positives / \
                (true_positives + false_negatives) if \
                (true_positives + false_negatives) else 0.0
            accuracy = (true_positives + true_negatives) / \
                total_intervals if total_intervals else 0.0

            logging.info(
                    f"Schedule evaluation for {date}: "
                    f"TP={true_positives}, FP={false_positives}, "
                    f"FN={false_negatives}, TN={true_negatives}, "
                    f"Precision={precision:.2%}, Recall={recall:.2%}, "
                    f"Accuracy={accuracy:.2%}"
                )

            if (true_positives + false_positives) == total_intervals:
                logging.warning(f"All intervals predicted ON for {date} "
                                "— possible fallback behavior.")
            elif (true_negatives + false_negatives) == total_intervals:
                logging.warning(f"All intervals predicted OFF for {date} "
                                "— possibly under-predicting.")

            self.db.conn.commit()
            logging.debug(f"Schedule evaluation completed for {date}")

        except Exception as e:
            logging.error(f"Failed to evaluate schedule for {date}: {e}",
                          exc_info=True)

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
