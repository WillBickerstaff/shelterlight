"""lightlib.common.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Common methods
Author: Will Bickerstaff
Version: 0.1
"""

import datetime as dt
from typing import Union

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
