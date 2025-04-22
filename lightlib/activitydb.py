"""lightlib.activitydb.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Record activity detected on a GPIO pin into a SQL Database.
Author: Will Bickerstaff
Version: 0.1
"""

import logging
import datetime as dt
import threading
from typing import List, Dict, Union
from enum import Enum

import psycopg2
from psycopg2 import sql
import lgpio

from lightlib.db import DB, ConfigLoader
from lightlib.common import valid_smallint


class PinHealth(Enum):
    """Enumeration for pin statuses."""

    OK = True
    FAULT = False


class PinLevel(Enum):
    """Enumeration for pin states."""

    HIGH = True
    LOW = False


class PinFaultHigh(Exception):
    """Raised when a GPIO pin remains high beyond the fault threshold."""

    def __init__(self, pin: int, duration: float):
        self.pin = pin
        self.duration = duration
        super().__init__(
            f"Pin {pin} has remained high for {duration} seconds, "
            "exceeding the threshold."
        )


class Activity:
    """Class to monitor GPIO activity inputs.

    Log events to a PostgreSQL database,
    and detect excessive high duration for each input, updating pin statuses as
    OK or FAULT and current state as HIGH or LOW.

    Attributes
    ----------
        _db (DB): Database instance for logging activity events.

        _activity_inputs (List[int]): List of GPIO pins to
        monitor for activity.

        _start_times (Dict[int, dt.datetime]): Dictionary to store start times
                                               for each monitored GPIO pin.

        _pin_status (Dict[int, Dict[str, Union[PinHealth, PinLevel]]]):
            Dictionary mapping each GPIO pin to its current 'status'
            (PinHealth.OK or .FAULT) and 'state' (PinLevel.HIGH or .LOW).

        _fault_threshold (float): Threshold in seconds for a high state
        duration considered faulty.

        _health_check_interval (float): Interval in seconds between each fault
                                        check cycle.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Ensure only one instance of Activity exists (Singleton pattern)."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize class, set up db conn, GPIO & fault detection timer.

        Raises
        ------
            Exception: If GPIO setup or database connection fails.
        """
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # Load PostgreSQL connection settings
        self._db = DB("ACTIVITY_DB")
        self._activity_inputs: List[int] = \
            ConfigLoader().activity_digital_inputs
        self._start_times: Dict[int, dt.datetime] = {}
        self._pin_status: Dict[int, Dict[str, Union[PinHealth, PinLevel]]] = {
            pin: {"status": PinHealth.OK, "state": PinLevel.LOW}
            for pin in self._activity_inputs
        }  # Track status and state of each pin
        self._gpio_handle = lgpio.gpiochip_open(0)
        self._setup_activity_inputs()
        self._fault_threshold = ConfigLoader().max_activity_time
        self._health_check_interval = ConfigLoader().health_check_interval
        self._start_fault_detection()  # Start periodic fault checking

    def _setup_activity_inputs(self) -> None:
        """
        Set up GPIO for monitoring activity on specified pins.

        Configures each GPIO pin to trigger `_start_activity_event` on a
        low-to-high transition (RISING edge) and `_end_activity_event` on a
        high-to-low transition (FALLING edge).
        """
        for pin in self._activity_inputs:
            try:
                lgpio.gpio_claim_input(self._gpio_handle, pin,
                                       lgpio.SET_PULL_DOWN)
                logging.info("GPIO pin %s setup as INPUT, PULL DOWN", pin)
                # Detect rising edge to mark start of activity
                logging.debug("Adding edge detection to pin %s", pin)
                logging.debug("pin is type %s", type(pin))
                # Register callbacks for both rising and falling edges
                lgpio.callback(self._gpio_handle, pin, lgpio.BOTH_EDGES,
                               self._activity_event_handler)
                logging.info(
                    "Activity monitoring initialized on GPIO pins: %s",
                    self._activity_inputs
                )
            except RuntimeError as e:
                logging.error("Failed to set edge detection for pin %s: %s",
                              pin, e)

    def _activity_event_handler(
            self, chip: int, pin: int, level: int, tick: int) -> None:
        """Direct Rising & Falling events to the correct method.

        Each GPIO pin is only permitted to have one event handler registered
        (GPIO Limitation). As both rising and falling events are required,
        activity pins register both rising and falling edge callbacks using
        lgpio.callback() in _setup_activity_inputs.

        Either a rising or falling edge directs execution here where the
        decision is made on what action to take.

        Args
        ----
            chip : int
                The GPIO chip descriptor (usually 0).
            gpio : int
                The GPIO pin number.
            level : int
                Edge level: 1 = rising, 0 = falling.
            tick : int
                Timestamp in microseconds (unused).
        """
        if level == 1:    # High after Risng edge
            self._start_activity_event(pin)
        elif level == 0:  # Low after Falling edge
            self._end_activity_event(pin)

    def _start_activity_event(self, pin: int) -> None:
        """Record start time and set pin state HIGH for GPIO pin high.

        Args
        ----
            pin (int): The GPIO pin that triggered the rising edge event.
        """
        # Record start time
        self._start_times[pin] = dt.datetime.now(dt.timezone.utc)
        self._pin_status[pin]["status"] = PinHealth.OK  # Set status to OK
        self._pin_status[pin]["state"] = PinLevel.HIGH  # Set state to HIGH
        logging.info(
            f"Activity started on pin {pin} at {self._start_times[pin]}"
        )
        logging.debug("Pin %i: Status = %s, State = %s", pin,
                      self._pin_status[pin]["status"].name,
                      self._pin_status[pin]["state"].name)

    def _end_activity_event(self, pin: int) -> None:
        """Log activity to DB.

        Log an activity event to the database with date, time, and duration
        information when the specified GPIO pin goes low. Resets the pin status
        to OK if it was in a FAULT state, and sets the pin state to LOW.

        Args
        ----
            pin (int): The GPIO pin that triggered the falling edge event.

        Raises
        ------
            psycopg2.DatabaseError: If there is an error executing the database
                                    query.
        """
        if (self._pin_status[pin]["status"] == PinHealth.FAULT):
            logging.warning("Pin %i fault cleared", pin)
        self._pin_status[pin]["status"] = PinHealth.OK  # Reset status to OK
        self._pin_status[pin]["state"] = PinLevel.LOW  # Set state to LOW
        start_time = self._start_times.pop(pin, None)  # Retrieve start time
        if start_time is None:
            logging.warning(
                f"No start time found for pin {pin}, skipping log.")
            return
        try:
            duration = int((dt.datetime.now(dt.timezone.utc) -
                            start_time).total_seconds())  # Calc duration
            valid_smallint(duration)
            if duration > self._fault_threshold:
                logging.warning(
                    f"Skipping log: activity duration {duration}s exceeded "
                    f"max_activity_time ({self._fault_threshold}).")
                return

        except ValueError:
            logging.error(f"Will not log an activity duration of {duration}s, "
                          "duration must be <= 32767s (9h 6m)")
            return

        day_of_week = int(start_time.strftime('%w'))
        month = start_time.month
        year = start_time.year

        insert_query = sql.SQL(
            """
            INSERT INTO activity_log (
                timestamp, day_of_week, month, year, activity_pin, duration
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """
        )

        try:
            self._db.query(
                query=insert_query,
                params=(start_time, day_of_week, month, year, pin, duration)
            )
            logging.info(
                f"Activity event logged for pin {pin} "
                f"beginning at {start_time}"
                f" with a duration of {duration} seconds."
            )
        except psycopg2.DatabaseError as e:
            logging.error(
                "Failed to log activity event for pin %s: %s", pin, e)

    def _run_fault_check_cycle(self) -> None:
        """Run one fault detection cycle."""
        for pin, start_time in list(self._start_times.items()):
            duration = int((dt.datetime.now(dt.timezone.utc) - start_time)
                           .total_seconds())
            if duration > self._fault_threshold and \
                    self._pin_status[pin]["state"] == PinLevel.HIGH:
                self._pin_status[pin]["status"] = PinHealth.FAULT
                logging.warning(
                    f"Pin {pin} set to FAULT status, high for {duration} "
                    "seconds."
                )
            else:
                self._pin_status[pin]["status"] = PinHealth.OK  # Set OK

    def _start_fault_detection(self) -> None:
        """Periodic fault check.

        Start a periodic check to detect if any monitored input has remained
        high beyond the fault threshold.
        """
        def fault_check():
            self._run_fault_check_cycle()
            t = threading.Timer(self._health_check_interval, fault_check)
            t.daemon = True
            t.start()  # Re-run check

        fault_check()

    def get_pin_status(self, pin: int) -> Dict[str, PinHealth]:
        """Retrieve the current status and state of a specific GPIO pin.

        Args
        ----
            pin (int): The GPIO pin number to check.

        Returns
        -------
            Dict[str, PinHealth]: The 'status' and 'state' of the pin.
        """
        return self._pin_status.get(
            pin, {"status": PinHealth.FAULT, "state": PinLevel.LOW}
        )

    def get_all_pin_statuses(self) -> Dict[int, Dict[str, Union[PinHealth,
                                                                PinLevel]]]:
        """Retrieve the current status and state of all monitored GPIO pins.

        Returns
        -------
            Dict[int, Dict[str, Union[PinHealth, PinLevel]]]:
                Dictionary with pin numbers as keys and dictionaries containing
                'status' and 'state' keys with PinHealth & PinLevel values.
        """
        return self._pin_status

    def activity_detected(self) -> bool:
        """Return True if any activity input is currently HIGH.

        Returns
        -------
            Bool: True if activity is detected.
        """
        return any(
            status["state"] == PinLevel.HIGH
            for status in self._pin_status.values()
        )

    def should_lights_be_on(self) -> bool:
        """Return True if activity is current and lights should be on.

        Returns
        -------
            Bool: True if any activity is current and lights should be on.
        """
        return self.is_activity_detected()

    def close(self) -> None:
        """Clean up GPIO resources and close the database connection."""
        self.cleanup()
        if self._db:
            self._db.close_connection()
            logging.info(
                "Database connection closed and GPIO cleanup completed.")

    def cleanup(self):
        """Clean up GPIO activity pins."""
        try:
            if hasattr(self, "_gpio_handle") and self._gpio_handle is not None:
                lgpio.gpiochip_close(self._gpio_handle)
                logging.info("Activity GPIO cleanup complete.")
                self._gpio_handle = None
        except lgpio.error as e:
            logging.warning("Activity GPIO cleanup failed: %s", e)
