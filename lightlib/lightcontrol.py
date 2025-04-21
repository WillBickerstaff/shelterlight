"""lightlib.lightcontrol.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Control the light outputs, generate schedules & monitor activity.
Author: Will Bickerstaff
Version: 0.1
"""

import logging
from threading import Lock
from lightlib.config import ConfigLoader
from lightlib.activitydb import Activity
from scheduler.Schedule import LightScheduler
from RPi import GPIO
from datetime import datetime as dt


class LightController:
    """Manage light on status, activity recording and schedule generation."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Ensure only one instance of LightController exists."""
        with cls._lock:  # Thread-safe instance creation
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        self.schedule = LightScheduler()
        self.activity_monitor = Activity()
        self._lights_output = ConfigLoader().lights_output

        GPIO.setup(self._lights_output, GPIO.OUT)

    def _is_dark_now(self) -> bool:
        """Determine if it is dark now to enable activity to react.

        Returns
        -------
            bool: True if it is dark now, otherwise false
        """
        now = dt.datetime.now(dt.timezone.utc).time()
        darkness_start, darkness_end = self.schedule._get_darkness_times()

        if darkness_start < darkness_end:
            return darkness_start <= now <= darkness_end
        else:
            # darkness spans midnight
            return now >= darkness_start or now <= darkness_end

    def set_lights(self) -> bool:
        """Set the light output.

        Determines if lights should be on either scheduled or activity is
        detected within darkness hours.

        Returns
        -------
            bool: True if lights are on otherwise False
        """
        schedule_on = self.schedule.should_light_be_on()
        activity_on = (self.activity_monitor.activity_detected() and
                       self._is_dark_now())
        if schedule_on or activity_on:
            logging.info("Lights switched on (%s)",
                         "Schedule" if schedule_on else "Activity")
            self.turn_on()
            return True
        else:
            self.turn_off()
            return False

    def turn_on(self):
        """Turn on lights."""
        GPIO.output(self._lights_output, GPIO.HIGH)

    def turn_off(self):
        """Turn off lights."""
        GPIO.output(self._lights_output, GPIO.LOW)

    def cleanup(self):
        """Cleanup GPIO resources."""
        if GPIO.getmode() is not None:
            GPIO.cleanup(self._lights_output)
        self.activity_monitor.cleanup()
        logging.info("LightController GPIO cleaned up.")
