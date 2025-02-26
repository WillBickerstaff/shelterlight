import logging
import datetime as dt
import threading
from typing import List, Dict, Union
from enum import Enum

import psycopg2
from psycopg2 import sql
import RPi.GPIO as GPIO

from lightlib.db import DB, ConfigLoader

class schedule:
    def __init__(self):
        self._db = DB("ACTIVITY_DB")
        self._control_out: int = ConfigLoader().lights_output

    def _init_sched_db(self):
        """ Check for an sqlLite Schedule database, create if non existent,
        and define a connection. If the db exists, jus define the connection"""

    def _db_connect(self):
        """Initialize the scedule database connection"""

    def clear_db(self):
        """clear out past schedules from the database."""

    def check_on(self):
        """Check if lights should be on according to the schedule"""

    def generate_schedule(self):
        """Generate a schedule for the next 24 hours, first remove any 
        schedule entry that is after now to prevent overlaps"""

    def _after_now(self):
        """Clear out any schedule after now to prevent any overlaps in 
        scheduling"""

    def _fetch_history(self):
        """Fetxh a history from the activity DB to determine future scheduling
        this method will call several other to ad in determining a schedule. 
        Yesterday, last week, this week last year etc"""

    def _fetch_yesterday(self):
        """Get activity information for yesterday"""

    def _fetch_last_week(self):
        """Get activity information for last week"""

    def _fatch_week_last_year(self):
        """Get activity information for this week last year"""