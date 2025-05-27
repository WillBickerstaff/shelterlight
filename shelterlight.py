"""shelterlight.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: A self learning autonomous light system with integrated scheduler.
Author: Will Bickerstaff
Version: 0.1
"""

import atexit
import argparse
import logging
import socket
import threading
import datetime as dt
import time
import traceback
from shelterGPS.Helio import SunTimes
from lightlib import USBManager
from scheduler.Schedule import LightScheduler
from lightlib.smartlight import init_log
from lightlib.config import ConfigLoader
from lightlib.common import ConfigReloaded, get_now
from lightlib.lightcontrol import LightController

class ExitAfter(Exception):
    """Raised to force a program halt."""

    pass


def cleanup_resources(gps: SunTimes, light_control: LightController) -> None:
    """Perform resource cleanup for GPS, GPIO, and logging."""
    logging.info("Performing resource cleanup...")
    gps.cleanup()  # Stops GPS fix process thread, if any
    light_control.cleanup()  # Clean up light output GPIO
    logging.info("Resources cleaned up successfully.")


def usb_listener(usb_manager, gps, stop_event: threading.Event,
                 host="localhost", port=9999):
    """Listen for USB insert events via socket and trigger config reload."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen(1)
        server_socket.settimeout(1)  # Allow periodic stop_event checking
        logging.info(f"Listening for USB insert events on {host}:{port}...")

        while not stop_event.is_set():
            try:
                conn, _ = server_socket.accept()
            except socket.timeout:
                continue  # Periodically check for stop_event

            with conn:
                logging.info("USB insertion detected via socket signal")
                try:
                    usb_manager.usb_check()
                except ConfigReloaded:
                    cleanup_resources(gps, LightController())
                    raise  # Propagate to restart main loop in main program


def light_loop(light_control: LightController,
               stop_event: threading.Event):
    """Run light control updates in a tight polling loop."""
    try:
        start_tick = time.monotonic()
        heartbeat = ConfigLoader().heartbeat_interval
        while not stop_event.is_set():
            light_control.update()
            time.sleep(1)
            if heartbeat > 0:
                tick_now = time.monotonic()
                if tick_now >= start_tick + heartbeat:
                    logging.info("[LOOP] Heartbeat tick lights are %s",
                                 f"ON ({light_control.on_reason.name})"
                                 if light_control.lights_are_on else "OFF",)
                    start_tick = tick_now
    except Exception as e:
        logging.exception("Light control loop encountered an error: %s", e,
                          exc_info=True)
    finally:
        logging.info("Light loop exited")


def gps_loop(gps: SunTimes, stop_event: threading.Event):
    """Run periodic GPS fix attempts on a configurable interval."""
    try:
        while not stop_event.is_set():
            if not gps.fixed_today and gps.in_fix_window:
                gps.start_gps_fix_process()
            time.sleep(ConfigLoader().cycle_time)
    except Exception as e:
        logging.exception("GPS control loop encountered an error: %s", e,
                          exc_info=True)
    finally:
        logging.info("GPS loop exited")


def has_schedule_for_date(db, date):
    with db.conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM light_schedules
            WHERE date = %s LIMIT 1;
        """, (date,))
        return cur.fetchone() is not None

def backfill_schedules(backfill_days=-1):
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
        (max_date - min_date).days + 1 )]

    if backfill_days > 0:
        activity_dates = [d for d in activity_dates if d >= (
            max_date - dt.timedelta(days=backfill_days - 1))]

    print("Generating historic schedules for the last "
          f"{len(activity_dates)} days...")

    training_days = 30  # ConfigLoader().training_days_history
    for idx, target_date in enumerate(activity_dates):
        try:
            print(f"Processing {idx + 1}/{len(activity_dates)}: {target_date}")

            # Evaluate previous days schedule if it exists
            previous_date = target_date - dt.timedelta(days=1)
            if has_schedule_for_date(db, previous_date):
                scheduler.evaluator.evaluate_previous_schedule(previous_date)

            # Train the model using all data available
            scheduler.model_engine.train_model(days_history=training_days)
            if scheduler.model_engine.model is None:
                print(f"No model trained for {target_date}. "
                      "Skipping schedule generation.")
                continue
            # Generate the schedule
            scheduler.generate_daily_schedule(target_date.isoformat())
        except Exception as e:
            print(f"Error processing {target_date}: {e}")
            traceback.print_exc()

    print("Historic schedule generation complete")

def daily_schedule_generation(stop_event: threading.Event,
                              scheduler: LightScheduler,
                              solar_times: SunTimes):
    """Generate the daily schedule 1 hour after sunrise."""
    while not stop_event.is_set():
        now = get_now()

        # Wait until solar times are available, if 1 is set, all are set
        sr_today = solar_times.UTC_sunrise_today
        if sr_today:
            generation_time = sr_today + dt.timedelta(hours=1)
            sleep_duration = (generation_time - now).total_seconds()

            if sleep_duration > 0:
                logging.info("Schedule will be generated at %s.",
                             generation_time.time())
                stop_event.wait(timeout=sleep_duration)
                if stop_event.is_set():
                    return

            logging.info("Generating daily schedule.")
            scheduler.update_daily_schedule()

            # Wait until tomorrows generation time
            sr_tomorrow = solar_times.UTC_sunrise_tomorrow
            next_run = sr_tomorrow + dt.timedelta(hours=1)
            sleep_duration = (next_run - get_now()).total_seconds()

            if sleep_duration > 0:
                logging.info("Next Schedule generation will be at %s, on %s.",
                             next_run.time(), next_run.date())
                stop_event.wait(timeout=sleep_duration)

        else:
            retry_at = now + dt.timedelta(minutes=5)
            logging.warning("Sunrise time not available. "
                            "retrying in 5 minutes at %s.", retry_at.time())
            stop_event.wait((retry_at - now).total_seconds())


def re_eval_history(force: bool = False):
    """Re-evaluate schedules and exit."""
    from scheduler.evaluation import ScheduleEvaluator
    from lightlib.db import DB

    logging.info("Manual history re-evaluation triggered via CLI.")
    db = DB()
    evaluator = ScheduleEvaluator()
    evaluator.set_config(db=db)
    evaluator.re_eval_all_schedules(force=force)
    logging.info("History re-evaluation complete.")
    return


def main_loop():
    """Continual Main loop entry point."""
    while True:
        stop_event = threading.Event()
        try:
            main(stop_event)
        except KeyboardInterrupt:
            logging.info("Program interrupted by user.")
            stop_event.set()
            break
        except ConfigReloaded:
            logging.info("Configuration reloaded; restarting main loop.")
            stop_event.set()
            continue  # Restart the main loop
        except ExitAfter:
            logging.info("Re-evaluated all historic schedules")
            stop_event.set()
            break
        except Exception as e:
            logging.error("Fatal error: %s", e, exc_info=True)
            stop_event.set()
            break
        finally:
            # Let systemd handle restarting to avoid zombie process
            logging.info("\n%s\n%sMAIN LOOP ENDED\n%s", "-"*79, " "*32, "-"*79)


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


def main(stop_event: threading.Event):
    """Program entry point."""
    args = parse_args()
    arg_handler(args)
    init_log(args.log_level)

    # Initialize USB manager, configuration, and logging
    usb_manager = USBManager.USBFileManager()
    gps = SunTimes()  # Initialize GPS/SunTimes instance
    light_control = LightController()  # Singleton managing light output logic

    # Make sure cleanup happens after sys.exit() or systemd shutdown
    atexit.register(lambda: cleanup_resources(gps, light_control))

    # Start USB listener in a separate thread to handle USB insert signals
    usb_thread = threading.Thread(target=usb_listener,
                                  args=(usb_manager, gps, stop_event),
                                  daemon=True)
    usb_thread.start()  # Begin listening for USB-based config reloads

    # Start schedule generation in background
    scheduler = light_control.schedule
    scheduler_thread = threading.Thread(target=daily_schedule_generation,
                                        args=(stop_event, scheduler, gps),
                                        daemon=True)
    scheduler_thread.start()

    # Start GPS fix loop in background
    gps_thread = threading.Thread(target=gps_loop,
                                  args=(gps, stop_event),
                                  daemon=True)
    gps_thread.start()

    # Start light control loop in background
    light_thread = threading.Thread(target=light_loop,
                                    args=(light_control, stop_event),
                                    daemon=True)
    light_thread.start()

    try:
        while True:
            # Control CPU usage in main loop
            time.sleep(10)

    except ConfigReloaded:
        cleanup_resources(gps, light_control)  # Cleanup Resources
        pass  # Handle by restarting the loop in `main_loop()`
    finally:
        stop_event.set()
        scheduler_thread.join()
        cleanup_resources(gps, light_control)


if __name__ == "__main__":
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    main_loop()
