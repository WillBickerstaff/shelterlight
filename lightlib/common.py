import datetime as dt
from typing import Union

EPOCH_DATETIME = dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)

def strftime(dt: dt.datetime) -> str:
    """Format a datetime object's time component as HH:MM:SS"""
    return dt.strftime("%H:%M:%S")

def strfdate(dt: Union[dt.date, dt.datetime]) -> str:
    """Format a date or datetime object as dd-mmm-yyyy"""
    return dt.strftime("%d-%b-%Y")

def strfdt(dt: dt.datetime) -> str:
    """Format a datetime object as dd-mmm-yyyy HH:MM:SS"""
    dt_str = "{} {}".format(strfdate(dt), strftime(dt))
    return dt_str

def iso_to_datetime(iso_str: str) -> dt.datetime:
        return dt.datetime.fromisoformat(iso_str)

def datetime_to_iso(dt_obj: dt.datetime) -> str:
    return dt_obj.isoformat()