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
import RPi.GPIO as GPIO
from shelterGPS.Helio import SunTimes
from lightlib import USBManager
from scheduler.Schedule import LightScheduler
from lightlib.smartlight import init_log
from lightlib.config import ConfigLoader
from lightlib.common import ConfigReloaded, gpio_init, gpio_cleanup
from lightlib.lightcontrol import LightController


def cleanup_resources(gps: SunTimes, light_control: LightController) -> None:
    """Perform resource cleanup for GPS, GPIO, and logging."""
    logging.info("Performing resource cleanup...")
    gps.cleanup()  # Stops GPS fix process thread, if any
    light_control.cleanup()  # Clean up light output GPIO
    gpio_cleanup()
    logging.info("Resources cleaned up successfully.")


def usb_listener(usb_manager, gps, host="localhost", port=9999):
    """Listen for USB insert events via socket and trigger config reload."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen(1)
        logging.info(f"Listening for USB insert events on {host}:{port}...")

        while True:
            conn, _ = server_socket.accept()
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
        while not stop_event.is_set():
            light_control.set_lights()
            time.sleep(1)
    except Exception as e:
        logging.exception("Light control loop encountered an error: %s", e)
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
        logging.exception("GPS control loop encountered an error: %s", e)
    finally:
        logging.info("GPS loop exited")


def daily_schedule_generation(stop_event: threading.Event,
                              scheduler: LightScheduler,
                              solar_times: SunTimes):
    """Generate the daily schedule 1 hour after sunrise."""
    while not stop_event.is_set():
        now = dt.datetime.now(dt.timezone.utc)

        # Check if today's sunrise time is available
        if solar_times.UTC_sunrise_today:
            # Set generation time to 1 hour after sunrise
            generation_time = solar_times.UTC_sunrise_today + \
                dt.timedelta(hours=1)

            # Calculate the time to wait until schedule generation
            sleep_duration = (generation_time - now).total_seconds()

            if sleep_duration > 0:
                logging.info(
                    f"Waiting {sleep_duration / 3600:.2f} hours"
                    " for schedule generation.")
                stop_event.wait(timeout=sleep_duration)

            if stop_event.is_set():
                break

            logging.info("Generating daily schedule.")
            scheduler.update_daily_schedule()

            # Wait until the next day's schedule generation time
            next_run = generation_time + dt.timedelta(days=1)
            sleep_duration = (
                next_run - dt.datetime.now(dt.timezone.utc)).total_seconds()
            if sleep_duration > 0:
                stop_event.wait(timeout=sleep_duration)
        else:
            logging.warning("Sunrise time not available. Retrying in 1 hour.")
            stop_event.wait(timeout=3600)


def main_loop():
    """Continual Main loop entry point."""
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logging.info("Program interrupted by user.")
            break
        except ConfigReloaded:
            logging.info("Configuration reloaded; restarting main loop.")
            continue  # Restart the main loop
        except Exception as e:
            logging.error(f"Fatal error: {e}")
            break
        finally:
            # Let systemd handle restarting to avoid zombie process
            GPIO.cleanup()
            logging.info("GPIO cleanup complete. Exiting.")


def main():
    """Program entry point."""
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Lighting Control System")
    parser.add_argument('--log_level', type=str,
                        help='Set the logging level (e.g., DEBUG, INFO)')
    args = parser.parse_args()
    init_log(args.log_level)
    stop_event = threading.Event()
    gpio_init()  # Set GPIO mode globally if not already set

    # Initialize USB manager, configuration, and logging
    usb_manager = USBManager.USBFileManager()
    gps = SunTimes()  # Initialize GPS/SunTimes instance
    light_control = LightController()  # Singleton managing light output logic

    # Make sure cleanup happens after sys.exit() or systemd shutdown
    atexit.register(lambda: cleanup_resources(gps, light_control))

    # Start USB listener in a separate thread to handle USB insert signals
    usb_thread = threading.Thread(target=usb_listener,
                                  args=(usb_manager, gps), daemon=True)
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
