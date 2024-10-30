import argparse
import logging
import time
import RPi.GPIO as GPIO  # type: ignore
from shelterGPS.Helio import SunTimes
from lightlib import USBManager
from lightlib.smartlight import init_log
from lightlib.config import ConfigLoader

class ConfigReloaded(Exception):
    pass

def cleanup_resources(gps: SunTimes) -> None:
    """Perform resource cleanup for GPS, GPIO, and logging."""
    logging.info("Performing resource cleanup...")
    gps.cleanup()  # Stops GPS fix process thread, if any
    GPIO.cleanup()  # Reset all GPIO pins
    logging.info("Resources cleaned up successfully.")


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

    try:
        while True:
            # Check for USB config and trigger reload if detected
            if usb_manager.usb_check():
                logging.info("USB config copied. Preparing to restart main.")
                cleanup_resources(gps)                
                raise ConfigReloaded  # Raise custom exception for loop restart

            # Start GPS fix if within the fixing window
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