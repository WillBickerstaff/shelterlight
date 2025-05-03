"""lightlib.common.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Common methods
Author: Will Bickerstaff
Version: 0.1
"""

import datetime as dt
import RPi.GPIO as GPIO
import logging
from typing import Union
from typing import Optional

EPOCH_DATETIME = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)


def get_now():
    """Return a datetime.datetime object representing now."""
    return dt.datetime.now(dt.timezone.utc)


DT_NOW = get_now()


def get_today():
    """Return today's date."""
    return get_now().date()


DATE_TODAY = get_today()


def get_tomorrow():
    """Return tomorrows date."""
    return get_today() + dt.timedelta(days=1)


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
    try:
        return dt.datetime.fromisoformat(iso_str)
    except Exception as e:
        logging.error("Failed to convert %s to a datetime object",
                      iso_str, e, exc_info=True)


def datetime_to_iso(dt_obj: dt.datetime) -> str:
    """Convert a dt object into an ISO formatted datetime string."""
    try:
        return dt_obj.isoformat()
    except Exception as e:
        logging.error("Failed to format %s to an ISO formatted "
                      "datetime string", dt_obj, e, exc_info=True)


def gpio_init(mode: Optional[int] = GPIO.BCM) -> None:
    """Set the global GPIO mode to BOARD."""
    pass  # no-op not required for lgpio


def gpio_cleanup():
    """Global GPIO cleanup."""
    pass  # no-op not required for lgpio


def valid_smallint(value):
    """Check a value can fit within smallint."""
    if -32768 <= value <= 32767:
        return True
    else:
        raise ValueError
