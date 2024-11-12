import argparse
import logging
import socket
import threading
import time
import RPi.GPIO as GPIO
from shelterGPS.Helio import SunTimes
from lightlib import USBManager
from lightlib.smartlight import init_log
from lightlib.config import ConfigLoader
from lightlib.common import ConfigReloaded


def cleanup_resources(gps: SunTimes) -> None:
    """Perform resource cleanup for GPS, GPIO, and logging."""
    logging.info("Performing resource cleanup...")
    gps.cleanup()  # Stops GPS fix process thread, if any
    GPIO.cleanup()  # Reset all GPIO pins
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
                    cleanup_resources(gps)
                    raise  # Propagate to restart main loop in main program

def main_loop():
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logging.info("Program interrupted by user.")
            break
        except ConfigReloaded:
            logging.info("Configuration reloaded; restarting main loop.")
            continue  # Restart the main loop
        finally:
            GPIO.cleanup()
            logging.info("Cleanup complete. Exiting.")

def main():
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Lighting Control System")
    parser.add_argument('--log_level', type=str,
                        help='Set the logging level (e.g., DEBUG, INFO)')
    args = parser.parse_args()

    # Set GPIO mode for RPi GPIO pins
    GPIO.setmode(GPIO.BOARD)

    # Initialize USB manager, configuration, and logging
    usb_manager = USBManager.USBFileManager()
    init_log(args.log_level)
    config_loader = ConfigLoader()  # Initialize the singleton config loader
    gps = SunTimes()  # Initialize GPS/SunTimes instance

    # Start USB listener in a separate thread to handle USB insert signals
    usb_thread = threading.Thread(target=usb_listener, args=(usb_manager, gps))
    usb_thread.daemon = True
    usb_thread.start()

    try:
        while True:
            if not gps.fixed_today and gps.in_fix_window:
                gps.start_gps_fix_process()

            # Control CPU usage in main loop
            time.sleep(config_loader.cycle_time)

    except ConfigReloaded:
        pass  # Handle by restarting the loop in `main_loop()`
    finally:
        cleanup_resources(gps)

if __name__ == "__main__":
    main_loop()