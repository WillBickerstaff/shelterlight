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
import time
from enum import Enum
from threading import Lock
from lightlib.common import get_now
from lightlib.config import ConfigLoader
from lightlib.activitydb import Activity
from scheduler.Schedule import LightScheduler
from shelterGPS.Helio import SunTimes, PolarDayError, PolarNightError, \
    PolarEvent


class OnReason(Enum):
    NOT_ON = 0
    ACTIVITY = 1
    SCHEDULE = 2

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
        self._off_logged = False
        self._on_logged = False
        self._holding_logged = False
        self._on_time = 0.0
        self.turn_off()  # Start with lights off
        self.on_reason = OnReason.NOT_ON

    def update(self):
        """Update system state: check inputs and control lights."""
        self.activity_monitor.update()
        self.set_lights()

    @property
    def lights_are_on(self) -> bool:
        """Return True if any light output is on."""
        if self._gpio_handle is not None:
            return any(
                lgpio.gpio_read(self._gpio_handle, pin) == 1
                for pin in self._lights_output)

        return False

    def _is_dark_now(self) -> bool:
        """Determine if it is dark now to enable activity to react.

        Returns
        -------
            bool: True if it is dark now, otherwise false
        """
        try:
            sunt = SunTimes()
            light_start = sunt.UTC_sunrise_today
            light_end = sunt.UTC_sunset_today
        except PolarDayError:
            return False
        except PolarNightError:
            return True

        except Exception as e:
            logging.error("An error occured while attempting to determine if "
                          "it is dark now, failing safe (True): %s", e,
                          exc_info=True)
            return True
        finally:
            if light_start is None or light_end is None:
                logging.warning("Unable to determine if it is dark now\n"
                                "\tSunrise today is:\t%s\n"
                                "\tSunset today is:\t%s\n"
                                "Failing safe (True)",
                                light_start, light_end)
                return True

        return not (light_start <= get_now() < light_end)

    def set_lights(self) -> bool:
        """Set the light output.

        Determines if lights should be on either scheduled or activity is
        detected within darkness hours.

        Returns
        -------
            bool: True if lights are on otherwise False
        """
        schedule_on = self.schedule.should_light_be_on()
        activity_on = self.activity_monitor.activity_detected()
        is_dark = self._is_dark_now()

        if not is_dark:
            self.turn_off()
            if not self._off_logged:
                logging.info("Lights switched --OFF--.")
                self._off_logged = True
                self._on_logged = False
                self._holding_logged = False
            return False

        if schedule_on:
            self.on_reason = OnReason.SCHEDULE
        elif activity_on:
            self.on_reason = OnReason.ACTIVITY
        if schedule_on or activity_on:
            self.turn_on()
            if not self._on_logged:
                logging.info("Lights switched --ON-- : %s in darkness",
                             self.on_reason.name)
                self._on_logged = True
                self._off_logged = False
                self._holding_logged = False
            return True
        else:
            if time.monotonic() - self._on_time >= \
               ConfigLoader().min_activity_on:
                self.turn_off()
                if not self._off_logged:
                    logging.info("Lights switched --OFF--")
                    self._off_logged = True
                    self._on_logged = False
                    self._holding_logged = False
                    return False
            else:
                if not self._holding_logged:
                    logging.info("Lights staying --ON-- "
                                 "(Minimum duration not achieved)")
                    self._holding_logged = True
                    self._on_logged = False
                return True

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
        self._on_time = time.monotonic()
        self._set_lights(1)

    def turn_off(self):
        """Turn off lights."""
        self._set_lights(0)
        self.on_reason = OnReason.NOT_ON

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
