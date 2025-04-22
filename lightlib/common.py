"""lightlib.common.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Common methods
Author: Will Bickerstaff
Version: 0.1
"""

import datetime as dt
import logging
import RPi.GPIO as GPIO
from typing import Union
from typing import Optional

EPOCH_DATETIME = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)


def get_today():
    """Return today's date."""
    return dt.datetime.now().date()


def get_tomorrow():
    """Return tomorrows date."""
    return DATE_TODAY + dt.timedelta(days=1)


DATE_TODAY = get_today()
DATE_TOMORROW = get_tomorrow()


class ConfigReloaded(Exception):
    """Raise when config reloaded, to trigger a re-read of config."""

    pass


def strftime(dt: dt.datetime) -> str:
    """Format a datetime object's time component as HH:MM:SS."""
    return dt.strftime("%H:%M:%S")


def strfdate(dt: Union[dt.date, dt.datetime]) -> str:
    """Format a date or datetime object as dd-mmm-yyyy."""
    return dt.strftime("%d-%b-%Y")


def strfdt(dt: dt.datetime) -> str:
    """Format a datetime object as dd-mmm-yyyy HH:MM:SS."""
    dt_str = "{} {}".format(strfdate(dt), strftime(dt))
    return dt_str


def iso_to_datetime(iso_str: str) -> dt.datetime:
    """Convert an ISO formatted datetime string into a dt object."""
    return dt.datetime.fromisoformat(iso_str)


def datetime_to_iso(dt_obj: dt.datetime) -> str:
    """Convert a dt object into an ISO formatted datetime string."""
    return dt_obj.isoformat()


def gpio_init(mode: Optional[int] = GPIO.BCM) -> None:
    """Set the global GPIO mode to BOARD, unless already set correctly.

    Safely initialize GPIO pin numbering mode for consistency across the
    application. Allows GPIO mode to be set once, and prevents runtime errors
    from conflicting mode assignments.

    Args
    ----
    mode : int, optional
        The desired GPIO numbering mode, either GPIO.BOARD (default) or
        GPIO.BCM.

    Raises
    ------
    RuntimeError
        If the GPIO mode is already set and differs from the requested mode.
    """
    current_mode = GPIO.getmode()

    mode_names = {
        None: "None",
        GPIO.BOARD: "BOARD",
        GPIO.BCM: "BCM"
    }

    logging.debug("GPIO Mode currently set to: %s",
                  mode_names.get(current_mode, str(current_mode)))

    if current_mode is None:
        GPIO.setmode(mode)
        logging.info("GPIO Mode initialized to: %s",
                     mode_names.get(mode, str(mode)))
    elif current_mode != mode:
        raise RuntimeError(
            "GPIO mode already set to "
            f"{mode_names.get(current_mode, str(current_mode))}, "
            f"expected {mode_names.get(mode, str(mode))}."
        )


def gpio_cleanup():
    """Global GPIO cleanup."""
    try:
        if GPIO.getmode() is not None:
            GPIO.cleanup()
            logging.debug("GPIO Resources cleaned up")
        else:
            logging.debug("GPIO cleanup skipped: GPIO mode not set.")
    except RuntimeError as e:
        logging.warning("GPIO cleanup failed: %s", e)

def valid_smallint(value):
    """Check a value can fit within smallint."""
    if -32768 <= value <= 32767:
        return True
    else:
        raise ValueError
