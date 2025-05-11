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
    """Optional mode: re-evaluate schedules and exit."""
    from scheduler.evaluation import ScheduleEvaluator
    from lightlib.db import DB

    db = DB()
    evaluator = ScheduleEvaluator()
    evaluator.set_config(db=db)
    evaluator.re_eval_all_schedules(force=force)
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
        except ExitAfter as e:
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


def main(stop_event: threading.Event):
    """Program entry point."""
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Lighting Control System")
    parser.add_argument('--log_level', type=str,
                        help='Set the logging level (e.g., DEBUG, INFO)')
    parser.add_argument('--re-eval', action="store_true",
                        help='Re-evaluate all historical schedules.')
    parser.add_argument('--force-eval', action="store_true",
                        help='Force re-evalution even if already marked.')
    parser.add_argument('--retrain', action="store_true",
                        help="Retrain the model and store the schedule.")
    args = parser.parse_args()
    init_log(args.log_level)

    if args.retrain:
        logging.info("Manual model retraining triggered via CLI.")
        scheduler = LightScheduler()
        scheduler.update_daily_schedule()
        logging.info("Model retraining and schedule generation complete.")
        raise ExitAfter()

    if args.re_eval:
        logging.info("Manual history re-evaluation triggered via CLI.")
        re_eval_history(force=args.force_eval)
        logging.info("History re-evaluation complete.")
        raise ExitAfter()  # Exit immediately after re-evaluation

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
