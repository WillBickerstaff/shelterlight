"""shelterlight.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Command line option handling.
Author: Will Bickerstaff
Version: 0.1
"""

import argparse
import logging
import traceback
import time
import datetime as dt
from scheduler.Schedule import LightScheduler, schedule_tostr
from .exceptions import ExitAfter
from .common import sec_to_hms_str


def parse_args():
    """Argument parser setup."""
    parser = argparse.ArgumentParser(description="Lighting Control System")
    parser.add_argument('--log_level', type=str,
                        help='Set the logging level (e.g., DEBUG, INFO)')
    parser.add_argument('--re-eval', action="store_true",
                        help='Re-evaluate all historical schedules.')
    parser.add_argument('--force-eval', action="store_true",
                        help='Force re-evalution even if already marked.')
    parser.add_argument('--retrain', action="store_true",
                        help="Retrain the model and store the schedule.")
    parser.add_argument('--backfill', nargs="?", const=-1, type=int,
                        default=None,
                        help="Regenerate past schedules using all data upto"
                        "N days back. Default will back fill to the earliest"
                        "activity record")
    return parser.parse_args()


def arg_handler(args: argparse.Namespace) -> None:
    """Handle passed cli options."""
    if args.retrain:
        logging.info("Manual model retraining triggered via CLI.")
        scheduler = LightScheduler()
        scheduler.update_daily_schedule()
        logging.info("Model retraining and schedule generation complete.")
        raise ExitAfter()

    if args.re_eval:
        re_eval_history(force=args.force_eval)
        raise ExitAfter()

    if args.backfill:
        backfill_schedules(backfill_days=args.backfill)
        raise ExitAfter()


def re_eval_history(force: bool = False):
    """Re-evaluate schedules and exit."""
    from scheduler.evaluation import ScheduleEvaluator
    from lightlib.db import DB

    msg="Manual history re-evaluation triggered via CLI."
    logging.info(msg)
    print(msg)

    db = DB()
    evaluator = ScheduleEvaluator()
    evaluator.set_config(db=db)
    evaluator.re_eval_all_schedules(force=force)
    logging.info("History re-evaluation complete.")
    return


def backfill_schedules(backfill_days=-1):
    """Backfill schedules using 30 days activity data."""
    from lightlib.db import DB
    db = DB()
    scheduler = LightScheduler()
    scheduler.set_db_connection(db)

    with db.conn.cursor() as cur:
        cur.execute("""
            SELECT MIN(DATE(timestamp)), MAX(DATE(timestamp))
            FROM activity_log;
        """)
        min_date, max_date = cur.fetchone()

    if not min_date or not max_date:
        print("No activity found in database")
        return

    activity_dates = [min_date + dt.timedelta(days=i) for i in range(
        (max_date - min_date).days + 1)]

    if backfill_days > 0:
        activity_dates = [d for d in activity_dates if d >= (
            max_date - dt.timedelta(days=backfill_days - 1))]

    print("Generating historic schedules for the last "
          f"{len(activity_dates)} days...")

    training_days = LightScheduler.progressive_history()
    for idx, target_date in enumerate(activity_dates):
        start_time = time.monotonic()
        try:
            print(f"Processing {idx + 1}/{len(activity_dates)}: {target_date}"
                  "...", end=" ", flush=True)

            # Evaluate previous days schedule if it exists
            previous_date = target_date - dt.timedelta(days=1)
            if has_schedule_for_date(db, previous_date):
                scheduler.evaluator.evaluate_previous_schedule(previous_date)

            # Train the model using all data available
            scheduler.model_engine.train_model(days_history=training_days)
            if scheduler.model_engine.model is None:
                print(f"No model trained for {target_date}. "
                      "Skipping schedule generation.", flush=True)
                continue
            # Generate the schedule
            scheduler.generate_daily_schedule(target_date.isoformat())
            gen_time = time.monotonic() - start_time
            gen_time_str = sec_to_hms_str(gen_time)
            print(f"Done. Took {gen_time}s ({gen_time_str})", flush=True)
        except Exception as e:
            print(f"Error processing {target_date}: {e}")
            traceback.print_exc()

    print("Historic schedule generation complete")


def has_schedule_for_date(db, date):
    """Check for a schedule on a date."""
    with db.conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM light_schedules
            WHERE date = %s LIMIT 1;
        """, (date,))
        return cur.fetchone() is not None
