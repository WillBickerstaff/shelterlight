"""lightlib.lightcontrol.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Control the light outputs, generate schedules & monitor activity.
Author: Will Bickerstaff
Version: 0.1
"""

import logging
import lgpio
from threading import Lock
from lightlib.common import DT_NOW
from lightlib.config import ConfigLoader
from lightlib.activitydb import Activity
from scheduler.Schedule import LightScheduler
from shelterGPS.Helio import SunTimes


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

        # Open gpiochip0 handle for light output
        self._gpio_handle = lgpio.gpiochip_open(0)
        for out_pin in self._lights_output:
            lgpio.gpio_claim_output(self._gpio_handle, out_pin)
        self.turn_off()  # Start with lights off

    def update(self):
        """Update system state: check inputs and control lights."""
        self.activity_monitor.update()
        self.set_lights()

    def _is_dark_now(self) -> bool:
        """Determine if it is dark now to enable activity to react.

        Returns
        -------
            bool: True if it is dark now, otherwise false
        """
        sunt = SunTimes()
        return sunt.UTC_sunset_today < DT_NOW < sunt.UTC_sunrise_tomorrow

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

    def _set_lights(self, status: int):
        """Set all light outputs to a given status.

        Args
        ----
            status (int): Set all off (0) or all on (1)
        """
        if self._gpio_handle is not None:
            for out_pin in self._lights_output:
                lgpio.gpio_write(self._gpio_handle, out_pin, status)

    def turn_on(self):
        """Turn on lights."""
        self._set_lights(1)

    def turn_off(self):
        """Turn off lights."""
        self._set_lights(0)

    def cleanup(self):
        """Cleanup GPIO resources."""
        if hasattr(self, "_gpio_handle") and self._gpio_handle is not None:
            try:
                self.turn_off()
                lgpio.gpiochip_close(self._gpio_handle)
                logging.info("LightController GPIO handle closed.")
            except lgpio.error as e:
                logging.warning("LightController GPIO cleanup failed: %s", e)
            self._gpio_handle = None
        self.activity_monitor.cleanup()
        logging.info("LightController cleanup complete.")
