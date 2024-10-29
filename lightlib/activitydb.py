import logging
import datetime as dt
import threading
from typing import List, Dict, Union
from enum import Enum

import psycopg2
from psycopg2 import sql
import RPi.GPIO as GPIO  # type: ignore

from lightlib.db import DB, ConfigLoader

class PinStatus(Enum):
    """Enumeration for pin statuses and states."""
    OK = True
    FAULT = False
    HIGH = True
    LOW = False

class PinFaultHigh(Exception):
    """Exception raised when a GPIO pin remains high beyond the fault threshold.
    """
    def __init__(self, pin: int, duration: float):
        self.pin = pin
        self.duration = duration
        super().__init__(
            f"Pin {pin} has remained high for {duration} seconds, "
            "exceeding the threshold."
        )

class Activity:
    """
    Class to monitor GPIO activity inputs, log events to a PostgreSQL database, 
    and detect excessive high duration for each input, updating pin statuses as 
    OK or FAULT and current state as HIGH or LOW.

    Attributes:
        _db (DB): Database instance for logging activity events.
        _activity_inputs (List[int]): List of GPIO pins to monitor for activity.
        _start_times (Dict[int, dt.datetime]): Dictionary to store start times
                                               for each monitored GPIO pin.
        _pin_status (Dict[int, Dict[str, Union[PinStatus, str]]]): Dictionary to 
            store both the status ('OK' or 'FAULT') and the state ('HIGH' or 
            'LOW') for each pin.
        _fault_threshold (float): Threshold in seconds for a high state duration 
                                  considered faulty.
        _health_check_interval (float): Interval in seconds between each fault 
                                        check cycle.
    """

    def __init__(self):
        """
        Initialize the Activity class, setting up the database connection, GPIO 
        inputs, and the fault detection timer.
        
        Raises:
            Exception: If GPIO setup or database connection fails.
        """
        # Load PostgreSQL connection settings
        self._db = DB("ACTIVITY_DB")
        self._activity_inputs: List[int] = \
            ConfigLoader().activity_digital_inputs
        self._start_times: Dict[int, dt.datetime] = {}  
        self._pin_status: Dict[int, Dict[str, Union[PinStatus, str]]] = {
            pin: {"status": PinStatus.OK, "state": PinStatus.LOW}
            for pin in self._activity_inputs
        }  # Track status and state of each pin
        self._setup_activity_inputs()
        self._start_fault_detection()  # Start periodic fault checking
        self._fault_threshold = ConfigLoader().max_activity_time
        self._health_check_interval = ConfigLoader().health_check_interval
        
    def _setup_activity_inputs(self) -> None:
        """ 
        Set up GPIO for monitoring activity on specified pins.
         
        Configures each GPIO pin to trigger `_start_activity_event` on a 
        low-to-high transition (RISING edge) and `_end_activity_event` on a 
        high-to-low transition (FALLING edge).
        """
        GPIO.setmode(GPIO.BOARD)
        for pin in self._activity_inputs:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            # Detect rising edge to mark start of activity
            GPIO.add_event_detect(
                pin,
                GPIO.RISING,
                callback=self._start_activity_event,
                bouncetime=300
            )
            # Detect falling edge to mark end of activity
            GPIO.add_event_detect(
                pin,
                GPIO.FALLING,
                callback=self._end_activity_event,
                bouncetime=300
            )
        logging.info(
            "Activity monitoring initialized on GPIO pins: %s", 
            self._activity_inputs
        )

    def _start_activity_event(self, pin: int) -> None:
        """
        Record the start time and set pin state to HIGH when the specified GPIO 
        pin goes high.
        
        Args:
            pin (int): The GPIO pin that triggered the rising edge event.
        """
        # Record start time
        self._start_times[pin] = dt.datetime.now(dt.timezone.utc)  
        self._pin_status[pin]["status"] = PinStatus.OK  # Set status to OK
        self._pin_status[pin]["state"] = PinStatus.HIGH  # Set state to HIGH
        logging.info(
            f"Activity started for pin {pin} at {self._start_times[pin]}"
        )

    def _end_activity_event(self, pin: int) -> None:
        """
        Log an activity event to the database with date, time, and duration 
        information when the specified GPIO pin goes low. Resets the pin status
        to OK if it was in a FAULT state, and sets the pin state to LOW.

        Args:
            pin (int): The GPIO pin that triggered the falling edge event.

        Raises:
            psycopg2.DatabaseError: If there is an error executing the database 
                                    query.
        """
        end_time = dt.datetime.now(dt.timezone.utc)  # Current timestamp
        start_time = self._start_times.pop(pin, None)  # Retrieve start time
        if start_time is None:
            logging.warning(f"No start time found for pin {pin}, skipping log.")
            return
        duration = (end_time - start_time).total_seconds()  # Calculate duration
        day_of_week = end_time.strftime('%A')
        month = end_time.month
        year = end_time.year

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
                f"Activity event logged for pin {pin} at {end_time} with "
                f"duration {duration} seconds."
            )
            self._pin_status[pin]["status"] = PinStatus.OK  # Reset status to OK
            self._pin_status[pin]["state"] = PinStatus.LOW  # Set state to LOW
        except psycopg2.DatabaseError as e:
            logging.error("Failed to log activity event for pin %s: %s", pin, e)

    def _start_fault_detection(self) -> None:
        """
        Start a periodic check to detect if any monitored input has remained 
        high beyond the fault threshold.
        """
        def fault_check():
            for pin, start_time in list(self._start_times.items()):
                duration = (
                    dt.datetime.now(dt.timezone.utc) - start_time
                ).total_seconds()
                if duration > self._fault_threshold:
                    # Set FAULT
                    self._pin_status[pin]["status"] = PinStatus.FAULT  
                    logging.warning(
                        f"Pin {pin} is in FAULT status, high for {duration} "
                        "seconds."
                    )
                else:
                    self._pin_status[pin]["status"] = PinStatus.OK  # Set OK
            threading.Timer(
                self._health_check_interval, fault_check
            ).start()  # Re-run check
        
        fault_check()

    def get_pin_status(self, pin: int) -> Dict[str, PinStatus]:
        """
        Retrieve the current status and state of a specific GPIO pin.
        
        Args:
            pin (int): The GPIO pin number to check.

        Returns:
            Dict[str, PinStatus]: The 'status' and 'state' of the pin.
        """
        return self._pin_status.get(
            pin, {"status": PinStatus.FAULT, "state": PinStatus.LOW}
        )

    def get_all_pin_statuses(self) -> Dict[int, Dict[str, PinStatus]]:
        """
        Retrieve the current status and state of all monitored GPIO pins.
        
        Returns:
            Dict[int, Dict[str, PinStatus]]: Dictionary with pin numbers as keys 
            and dictionaries containing 'status' and 'state' keys with 
            PinStatus values.
        """
        return self._pin_status

    def close(self) -> None:
        """
        Clean up GPIO resources and close the database connection.
        """
        GPIO.cleanup(self._activity_inputs)
        if self._db:
            self._db.close_connection()
            logging.info(
                "Database connection closed and GPIO cleanup completed.")
