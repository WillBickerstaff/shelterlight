# Standard library imports
import datetime as dt
import threading
import time
import subprocess
from timezonefinder import TimezoneFinder
import logging
import pytz
from enum import Enum
from typing import Optional, Tuple, Dict

# Third-party imports
from astral import sun, Observer

# Local application/library-specific imports
import sys, os
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))
import shelterGPS.Position as pos
from lightlib.config import ConfigLoader
from lightlib.common import EPOCH_DATETIME, strftime,strfdate,strfdt
from lightlib.persist import GPSDataStore
class SolarEvent(Enum):
    """Enumeration of key solar events for sun position calculations."""
    SUNRISE = "sunrise"
    SUNSET = "sunset"
    NOON = "noon"
    DAWN = "dawn"
    DUSK = "dusk"

class SunTimes:
    def __init__(self) -> None:
        """Initializes SunTimes with GPS data, sunrise/sunset offsets,
        and tracking of solar event timestamps and GPS fixes.

        Initializes the `SunTimes` class with values related to GPS fixes
        and solar events. Configuration values for sunrise and sunset
        offsets are acquired from the configuration file. Internal attributes
        for sunrise and sunset timestamps, GPS fix status, and window are
        initialized.

        Attributes:
            sunrise_offset (int): Offset in seconds after sunrise to begin
                GPS fixing attempts. Fetched from configuration file.
            sunset_offset (int): Offset in seconds before sunset to end
                GPS fixing attempts. Fetched from configuration file.
            _gps (GPS): Instance of the `GPS` class for managing GPS data
                and fixes.
            _sr_today (float): UTC timestamp for today's sunrise event.
            _ss_today (float): UTC timestamp for today's sunset event.
            _sr_tomorrow (float): UTC timestamp for tomorrow's sunrise event.
            _ss_tomorrow (float): UTC timestamp for tomorrow's sunset event.
            _fix_err_day (int): Count of consecutive days GPS fixing has
                failed.
            _fixed_today (Optional[dt.date]): Date of the last successful
                GPS fix; `None` if no fix was obtained for the current day.
            _fix_window (list[float]): Start and end timestamps for the
                current GPS fixing window, adjusted by sunrise/sunset offsets.
            _gps_fix_running (threading.Event): Threading event flag for
                managing GPS fix process status.
            _gps_fix_thread (Optional[threading.Thread]): Thread to run the
                GPS fix process. `None` if the thread is inactive.
        """
        # Offsets are validated and set via the property methods
        self.sunrise_offset: int = ConfigLoader().sunrise_offset
        self.sunset_offset: int = ConfigLoader().sunset_offset
        self._observer: Observer = None
        self._init_dt()
        self._fix_err_day: int = 0
        self._fixed_today: bool = False

        # Initialize threading components for GPS fix status management
        self._gps_fix_running: threading.Event = threading.Event()
        self._gps_fix_thread: Optional[threading.Thread] = None

        # Log successful initialization with validated offset values
        logging.info(
            "SunTimes initialized with sunrise offset: %s minutes, "
            "sunset offset: %s minutes.",
            self.sunrise_offset, self.sunset_offset)

    def __del__(self) -> None:
        """Destructor to ensure resources are cleaned up."""
        self._stop_gps_fix_process()
        logging.info("SunTimes resources cleaned up upon deletion.")

    def _init_dt(self):
        # Initialize GPS, solar event timestamps, GPS fix tracking
        self._gps: pos.GPS = pos.GPS()
        self._sr_today: dt.datetime = EPOCH_DATETIME
        self._ss_today: dt.datetime = EPOCH_DATETIME
        self._sr_tomorrow: dt.datetime = EPOCH_DATETIME
        self._ss_tomorrow: dt.datetime = EPOCH_DATETIME
        # [start_time, end_time]
        self._fix_window: dict[str, dt.datetime] = {"start": EPOCH_DATETIME,
                                                      "end": EPOCH_DATETIME}
        # Until we know better from a GPS fix use UTC
        self._local_tz = pytz.timezone('UTC')

    @property
    def gps_fix_is_running(self) -> bool:
        """Indicates if the GPS fix process is currently running.

        Returns:
            bool: `True` if the GPS fix process is active, `False` otherwise.
        """
        return self._gps_fix_running.is_set()

    @property
    def UTC_sunrise_today(self) -> dt.datetime:
        """Date and time of today's sunrise (UTC).

        Returns:
            dt.datetime: UTC date and time for today's sunrise
        """
        return self._sr_today

    @property
    def local_sunrise_today(self) -> dt.datetime:
        """Date and time of today's sunrise (Local time).

        Returns:
            dt.datetime: Local date and time for today's sunrise
        """
        return self.UTC_to_local(self.UTC_sunrise_today)

    @property
    def UTC_sunset_today(self) -> dt.datetime:
        """Date and time of today's sunset (UTC).

        Returns:
            dt.datetime: UTC date and time for today's sunset
        """
        return self._ss_today

    @property
    def local_sunset_today(self) -> dt.datetime:
        """Date and time of today's sunset (Local time).

        Returns:
            dt.datetime: Local date and time for today's sunset
        """
        return self.UTC_to_local(self.UTC_sunset_today)

    @property
    def UTC_sunrise_tomorrow(self) -> dt.datetime:
        """Date and time of tomorrows's sunrise (UTC).

        Returns:
            dt.datetime: UTC date and time for tomorrow's sunrise
        """
        return self._sr_tomorrow

    @property
    def local_sunrise_tomorrow(self) -> dt.datetime:
        """Date and time of tomorrow's sunrise (Local time).

        Returns:
            dt.datetime: Local date and time for tomorrow's sunrise
        """
        return self.UTC_to_local(self.UTC_sunrise_tomorrow)

    @property
    def UTC_sunset_tomorrow(self) -> dt.datetime:
        """Date and time of tomorrows's sunset (UTC).

        Returns:
            dt.datetime: UTC date and time for tomorrows's sunset
        """
        return self._ss_tomorrow

    @property
    def local_sunset_tomorrow(self) -> dt.datetime:
        """Date and time of tomorrow's sunset (Local time).

        Returns:
            dt.datetime: Local date and time for tomorrow's sunset
        """
        return self.UTC_to_local(self.UTC_sunset_tomorrow)

    @property
    def failed_fix_days(self) -> int:
        """Number of consecutive days with failed GPS fix attempts.

        Returns:
            int: Count of consecutive failed GPS fix days.
        """
        return self._fix_err_day

    @failed_fix_days.setter
    def failed_fix_days(self, value: int = 0) -> None:
        """Resets the counter for consecutive failed GPS fix attempts.

        Args:
            value (int): The value to set to, Default is zero, which will
                         resets the counter.
        """
        logging.info("GPS: Resetting failed_fix_days to %s.", value)
        self._fix_err_day = value

    @property
    def fixed_today(self) -> bool:
        """Indicates if a GPS fix has been obtained for the current date.

        Returns:
            bool: `True` if a GPS fix was successfully obtained today, `False`
            otherwise.
        """
        return self._fixed_today

    @property
    def sunrise_offset(self) -> int:
        """Offset in seconds for sunrise calculations.

        Returns:
            int: The number of seconds after sunrise to begin GPS fixing.
        """
        return self._sunrise_offset

    @sunrise_offset.setter
    def sunrise_offset(self, offset: int) -> None:
        """Sets sunrise offset in minutes, with validation.

        Args:
            offset (int): Number of minutes for sunrise offset.

        Raises:
            ValueError: If offset exceeds reasonable bounds.
        """
        if -60 <= offset <= 60:
            self._sunrise_offset = offset
            logging.info("GPS: sunrise_offset set to %s minutes", offset)
            return
        logging.error("SUNT: Invalid sunrise offset. Offset out of allowed "
                        "range: %s", offset)
        raise ValueError("Offset must be within ±60 minutes.")

    @property
    def sunset_offset(self) -> int:
        """Returns sunset offset in seconds."""
        return self._sunset_offset

    @sunset_offset.setter
    def sunset_offset(self, offset: int) -> None:
        """Sets sunset offset in minutes, with validation.

        Args:
            offset (int): Number of minutes for sunset offset.

        Raises:
            ValueError: If offset exceeds reasonable bounds.
        """
        if -60 <= offset <= 60:
            self._sunset_offset = offset
            logging.info("GPS: sunset_offset set to %s seconds", offset)
            return
        logging.error("SUNT: Invalid sunset offset. Offset out of allowed "
                        "range: %s", offset)
        raise ValueError("Offset must be within ±60 minutes.")

    @property
    def fix_window_open(self) -> dt.datetime:
        """Returns the opening time of the GPS fixing window."""
        return self._fix_window['start']

    @property
    def fix_window_close(self) -> dt.datetime:
        """Returns the closing time of the GPS fixing window."""
        return self._fix_window['end']

    @property
    def in_fix_window(self) -> bool:
        """Checks if the current time falls within the GPS fixing window.

        This method checks if the current time is within the defined fix window.
        if either the start or end points of the window are not set this method
        will return True """
        if EPOCH_DATETIME in self._fix_window.values(): return True
        return self.fix_window_open < dt.datetime.now() < self.fix_window_close

    def UTC_to_local(self, UTC_time: dt.datetime) -> dt.datetime:
        """ Convert a UTC time to local time.

        This method takes a UTC datetime and converts to the local time. Local
        timezone is automatically determined using the GPS fix location.

        Arguments:
            UTC_time (dt.datetime): A datetime.datetime instance containing the
                UTC time to convert

        Returns:
            dt.datetime: The provided dattime converted from UTC to local time
        """

        localT = UTC_time.astimezone(pytz.timezone(self._local_tz))
        logging.info("GPS: Converted UTC time %s to local time %s (%s)",
                     UTC_time,localT,self._local_tz)
        return localT

    @staticmethod
    def calculate_solar_times(
        observer: Observer, date: dt.date) -> Dict[str, dt.datetime]:
        """Calculates the solar event times (e.g., sunrise, sunset) for a
           specified observer location and date.

        This method uses the `astral.sun` function to determine key solar
        events based on the observer's latitude, longitude, and elevation. It
        calculates times for events like sunrise, sunset, noon, dawn, and dusk
        in UTC.

        Args:
            observer (Observer): An instance of `astral.Observer` containing
                                 the observer's location data
                                 (latitude, longitude, and elevation).
            date (dt.date): The date for which to calculate solar event times.

        Returns:
            Dict[str, dt.datetime]: A dictionary where keys represent solar
            events (e.g., "sunrise", "sunset") and values are the UTC datetime
            objects for each event.

        Raises:
            ValueError: If the observer data or date is invalid (e.g.,
                        out-of-bounds coordinates).
            RuntimeError: For unexpected errors during solar time calculations.
        """
        try:
            # Calculate solar events based on observer location and specified
            # date
            solar_times = {
            "sunrise": sun.sunrise(observer, date),
            "sunset": sun.sunset(observer, date)
            }
            logging.info("SUNT: Calculated solar times at location "
                         "%s, %s\n  for     : %s\n  Sunrise : %s"
                         "\n  Sunset  : %s",
                         round(observer.latitude,2),
                         round(observer.longitude,2),
                         strfdate(date),
                         strftime(solar_times['sunrise']),
                         strftime(solar_times["sunset"]))
            return solar_times

        except ValueError as ve:
            logging.error("Invalid observer data or date: %s", ve)
            raise ValueError("Invalid observer location or date.") from ve

        except Exception as e:
            logging.error("Unexpected error calculating solar times: %s", e)
            raise RuntimeError(
                "Unexpected error in solar time calculation.") from e

    def cleanup(self) -> None:
        """Explicit method to stop GPS fix process and release resources."""
        self._stop_gps_fix_process()
        logging.info("SUNT: Cleanup. Resources released.")

    def start_gps_fix_process(self) -> None:
        """Start the GPS fix process in a separate thread if it is not already
           running.

        This method ensures only one GPS fix thread is active at a time by
        checking the `gps_fix_is_running` property. If not running, it starts
        `gps_fix_process` in a daemon thread, which will terminate if the main
        program exits. Threading will allow the rest of the program to
        continue while the GPS fix is obtained
        """
        if not self.gps_fix_is_running:
            # Start the GPS fix process in a new daemon thread
            self._gps_fix_thread = threading.Thread(
                target=self._gps_fix_process, daemon=True
            )
            self._gps_fix_thread.start()
            logging.info("SUNT: GPS fix process started.")
        else:
            logging.debug("SUNT:GPS fix process already running.")

    def update_solar_times(self) -> None:
        """Calculate and update solar event times for today and tomorrow.

        This method uses the GPS coordinates to calculate the sunrise and sunset
        times for the current and next day, updating the attributes:
        `_sr_today`, `_ss_today`, `_sr_tomorrow`, and `_ss_tomorrow`.
        """
        try:
            # Set up the observer location based on current GPS coordinates
            logging.debug("SUNT: Location information: "
                          "\n  lat     : %s\n  lng     : %s\n  elev    : %s",
                          self._gps.latitude_coord.to_string(),
                          self._gps.longitude_coord.to_string(),
                          self._gps.altitude)
            observer = Observer(latitude=self._gps.latitude,
                                longitude=self._gps.longitude,
                                elevation=self._gps.altitude)

            # Calculate solar times for today and tomorrow
            td = dt.date.today()
            logging.debug("SUNT: Todays date is %s", strfdt(td))

            # Update today's solar event times
            st = SunTimes.calculate_solar_times(observer, td)
            self._sr_today = st["sunrise"]
            self._ss_today = st["sunset"]

            # Update tomorrow's solar event times
            st = SunTimes.calculate_solar_times(
                observer, td + dt.timedelta(days=1))
            self._sr_tomorrow = st["sunrise"]
            self._ss_tomorrow = st["sunset"]

        except Exception as e:
            logging.error("Failed to update solar times: %s", e)

    def _set_system_time(self) -> None:
        """Sets the system time using the GPS datetime property.

        Retrieves the current UTC datetime from the GPS class instance and
        updates the system time. On non-Linux systems, this operation is
        skipped with a warning.

        Raises:
            subprocess.CalledProcessError: If the system time cannot be set,
                an error is logged, detailing the failure.
        """
        gps_datetime = EPOCH_DATETIME
        try:
            # Ensure this code only runs on Linux/Unix-like systems
            if os.name != 'posix':
                logging.warning(
                    "SUNT: System time setting skipped on non-Linux systems.")
                return
            # Access the datetime property from the GPS instance
            gps_datetime = self._gps.datetime

            # Validate that gps_datetime is a datetime instance and is set
            if not isinstance(gps_datetime, dt.datetime) or \
                gps_datetime == EPOCH_DATETIME:
                logging.error("SUNT: GPS datetime is not set or invalid. "
                              "Exiting system time update.")
                return

            # Format the datetime for compatibility with the system 'date'
            # command
            formatted_time = gps_datetime.strftime('%Y-%m-%d %H:%M:%S')

            # Run system command to set the date (requires sudo on most
            # Linux systems)
            subprocess.run(['sudo', 'date',
                            '--set', formatted_time], check=True)
            logging.info("System time set to %s based on GPS time",
                         formatted_time)

        except subprocess.CalledProcessError as e:
            logging.error("Failed to set system time: %s", e)

    def _calculate_and_define_fixing_window(self) -> None:
        """Calculate today's solar events and define the GPS fixing window.

        This method calculates sunrise and sunset times for the current day
        based on the GPS location, setting the fixing window times based on
        these events.
        """
        try:
            # Set observer location based on current GPS coordinates
            self._observer = Observer(latitude=self._gps.latitude,
                                      longitude=self._gps.longitude,
                                      elevation=self._gps.altitude)

            # Calculate solar times for today
            sun_times_today = SunTimes.calculate_solar_times(self._observer,
                                                            dt.date.today())
            # Define the fixing window based on today's solar events
            self._fix_window["start"], self._fix_window["end"] = \
                self._define_fixing_window(sun_times_today)

            # Log the calculated times for reference
            logging.info(
                "Fixing window defined for today: \n  Start : %s"
                        "\n  End    : %s",
                        strftime(self.fix_window_open),
                        strftime(self.fix_window_close))

        except Exception as e:
            logging.error(
                "Error calculating solar times/defining fixing window: %s", e)

    def attempt_fix_for_today(self) -> None:
        """Attempts to obtain a GPS fix within the defined fixing window for
           today.

        This method initiates the process to get a GPS fix within today's
        defined fixing window (between sunrise and sunset, adjusted by
        configurable offsets). It checks whether a GPS fix has already been
        completed for the day, and if not, calculates and sets the solar event
        times (sunrise and sunset) and defines the fixing window if they have
        not been set yet. The method then verifies if the current time falls
        within this fixing window and proceeds with the GPS fix attempts only
        if the time is within bounds.

        Workflow:
            1. Checks if a GPS fix has already been obtained today:
            - If `fixed_today` is `True`, logs that the GPS fix was completed
                for today and exits.
            2. Ensures the solar times and fixing window are set for today:
            - Calls `_is_window_set_for_today()` to confirm if solar times are
                already set for the current day.
            - If solar times and window are not set, calls
                `_set_solar_times_and_window()`to define today's solar events
                and fixing window.
            3. Verifies if the current time falls within the fixing window:
            - Calls `_within_fix_window()` to check if the current time is
                within the defined fixing window.
            - If the time is outside the fixing window, logs this information
                and exits.
            4. Proceeds to attempt GPS fixes within the fixing window:
            - Calls `_perform_gps_fix_attempts()` to initiate and manage GPS fix
                attempts until a successful fix is obtained or the process
                times out.

        Raises:
            Exception: If an error occurs during the setting of solar times or
            during GPS fix attempts, logs the error.
        """
        if self.fixed_today:
            logging.info("GPS fix already completed for today.")
            return

        # Ensure solar times and fixing window are set for today
        if not self._is_window_set_for_today():
            self._set_solar_times_and_window()

        # Verify current time is within the fixing window
        if not self._within_fix_window():
            logging.info("Current time is outside the fixing window.")
            return

        # Proceed to attempt GPS fix within the defined window
        self._perform_gps_fix_attempts()

    def _set_solar_times_and_window(self) -> None:
        """Calculate today's solar event times and define the GPS fixing window.

        This method calculates the solar event times for today based on the
        current GPS location (latitude, longitude, and elevation) and then
        defines the fixing window by applying configurable offsets to the
        calculated sunrise and sunset times.

        Workflow:
            1. Initializes an `Observer` with the GPS location (latitude,
                longitude, and altitude).
            2. Calls `calculate_solar_times` to get today's solar event times
                (e.g., sunrise, sunset).
            3. Defines the fixing window by applying sunrise and sunset offsets
                to the respective solar event times and updates
                `_fix_window_start` and `_fix_window_end`.

        This ensures that the fixing window is aligned with daily solar events,
        allowing GPS fix attempts only within a specific time range based on
        sunrise and sunset.

        Raises:
            Exception: Logs and raises an exception if there is an error during
            the calculation of solar times or fixing window definition.
        """
        try:
            # Set up the observer's location for solar time calculations
            self._observer = Observer(
                latitude=self._gps.latitude,
                longitude=self._gps.longitude,
                elevation=self._gps.altitude
            )

            # Calculate today's solar times (e.g., sunrise, sunset)
            sun_times_today = SunTimes.calculate_solar_times(self._observer,
                                                             dt.date.today())

            # Define the fixing window based on calculated solar times
            self._fix_window_start, self._fix_window_end = \
                self._define_fixing_window(sun_times_today)

        except Exception as e:
            logging.error("Error defining fixing window: %s", e)

    def _perform_gps_fix_attempts(self) -> None:
        """Attempt to obtain a GPS fix within the defined fixing window.

        This method attempts to obtain a GPS fix, retrying at intervals
        specified in the configuration if unsuccessful. The attempts are only
        made within a defined fixing window, and the method tracks consecutive
        failed attempts, halting after a configurable maximum failure
        threshold is reached.

        Workflow:
            1. Define `max_fix_errors` from configuration, setting the
                allowable failed attempts.
            2. Start a loop to attempt GPS fixes within the defined fixing
                window.
                - Attempt to obtain a GPS fix by calling `self._gps.get_fix()`.
                - On success, set the system time using GPS data, mark the fix
                    as obtained, update solar times, and exit the loop.
                - On failure (GPSInvalid exception), increment the failure
                    counter and check against
                `max_fix_errors`. If the limit is reached, raise a `GPSNoFix`
                    exception.
                - After each attempt (regardless of success or failure), power
                    off the GPS module to reduce power usage.
            3. If unsuccessful, wait for a retry interval specified in the
                configuration before the next attempt.

        Raises:
            pos.GPSNoFix: Raised if the maximum allowable consecutive GPS fix
                failures (`max_fix_errors`) is reached.
        """
        max_fix_errors = ConfigLoader().gps_failed_fix_days

        # Begin attempts to obtain a GPS fix within the defined fixing window
        while True:
            try:
                logging.info("SUNT: Attempting GPS fix.")
                self._gps.get_fix()  # Attempt to obtain GPS fix

                # Set system time based on GPS fix, update solar times, and
                # mark fix as obtained
                self._set_system_time()
                self._fixed_today = dt.date.today()
                self.update_solar_times()
                logging.info("SUNT: GPS fix obtained and solar times updated.")
                # Set the local timezone
                tz_finder = TimezoneFinder()
                self._local_tz =tz_finder.timezone_at(
                    lng = self._gps.longitude, lat = self._gps.latitude)
                break  # Exit loop on successful GPS fix

            except pos.GPSInvalid:
                # Increment the error counter and check against maximum allowed
                # errors
                self._fix_err_day += 1
                if self._fix_err_day >= max_fix_errors:
                    logging.error(
                        "GPS: Failed to fix for %s days.", max_fix_errors)
                    raise pos.GPSNoFix(
                        f"Unable to obtain GPS fix for {max_fix_errors} days.")

            finally:
                # Power off GPS module after each attempt
                self._gps.pwr_off()

            # Wait before retrying, as specified in configuration
            logging.info("Retrying GPS fix in %s seconds.",
                         ConfigLoader().gps_fix_retry_interval)
            time.sleep(ConfigLoader().gps_fix_retry_interval)

    def _store_persistent_data(self) -> None:
        data_store = GPSDataStore()
        data_store.store_data(
                max_fix_time = ConfigLoader().gps_max_fix_time,
                latitude = self._gps.latitude,
                longitude=self._gps.longitude,
                sunrise_times = [self.UTC_sunrise_today.isoformat(),
                                 self.UTC_sunrise_tomorrow.isoformat()],
                sunset_times=[self.UTC_sunset_today.isoformat(),
                              self.UTC_sunset_tomorrow.isoformat()])

    def _within_fix_window(self) -> bool:
        """Check if the current time falls within the GPS fixing window."""
        current_time = time.time()
        return self._fix_window_start <= current_time <= self._fix_window_end

    def _is_window_set_for_today(self) -> bool:
        """Check if the fixing window is already set for today based on
           sunrise time."""
        window_set = self.fix_window_open.date() == dt.date.today()
        logging.debug("SUNT: Fix window is %s set", "" if window_set else "")
        return window_set

    def _define_fixing_window(
          self, sun_times_today: Dict[str, dt.datetime]) -> None:
        """Defines the GPS fixing window start and end timestamps based on
           today's sunrise and sunset times.

        This method calculates the GPS fixing window using sunrise and sunset
        times from a provided solar events dictionary for today. The window is
        defined by adding the sunrise offset and sunset offset to the sunrise
        and sunset timestamps, respectively. The offsets allow for flexible
        GPS fixing windows relative to solar events.

        Args:
            sun_times_today (Dict[str, dt.datetime]): A dictionary containing
            today's solar events (such as "sunrise"
                and "sunset") and their respective UTC datetime values.

        Returns:
            Tuple[float, float]: A tuple containing the start and end
            timestamps (in seconds since the epoch) for the GPS fixing window.

        Raises:
            KeyError: If the required solar events ("sunrise" and "sunset")
            are not present in the input dictionary.
            TypeError: If the provided times are not in datetime format.
        """
        try:
            if dt.date.today() == self._sr_today.date():
                logging.debug("SUNT: Fix window already set for today")
                return
            logging.debug("\n%s\n\SUNT:\t\tDefining fix window\n%s",
                          "="*79,"-"*79)
            # Get sunrise and sunset timestamps for today's date
            self._sr_today = sun_times_today['sunrise']
            self._ss_today = sun_times_today['sunset']
            logging.debug(
                "\n  Sunrise (UTC) : %s\n  Sunset (UTC)  : %s",
                strftime(self._sr_today), strftime(self._ss_today))

            # Calculate fixing window start and end by applying offsets
            start_time = self._sr_today + dt.timedelta(
                minutes = self.sunrise_offset)
            end_time = self._ss_today + dt.timedelta(
                minutes=self.sunset_offset)
            self._fix_window["start"] = start_time,
            self._fix_window["end"] = end_time

            logging.info(
                "Fixing window defined:\n "
                "  Start         : %s\n  End                : %s",
                strftime(start_time), strftime(end_time))

            return start_time, end_time

        except KeyError as ke:
            logging.error(
                "Missing required solar event : %s", ke)
            raise KeyError(
                "Missing required solar events (sunrise or sunset).") from ke

        except TypeError as te:
            logging.error(
                "Invalid data type in: %s", te)
            raise TypeError(
                "Invalid data type for solar times; expected datetime.") from te

    def _gps_fix_process(self) -> None:
        """Thread function to periodically attempt a GPS fix within a fix
           attempt window.

        This method runs in a loop, attempting a GPS fix within each interval
        specified by `ConfigLoader().fix_retry_interval`. It checks the
        `_gps_fix_running` flag to determine if the loop should continue,
        allowing for controlled shutdown.

        Raises:
            Exception: Logs any unexpected errors that occur during the GPS
                       fixing process.
        """
        self._gps_fix_running.set()
        try:
            while self._gps_fix_running.is_set():
                self.attempt_fix_for_today()  # Attempt GPS fix for the day
                # Wait to retry
                time.sleep(ConfigLoader().gps_fix_retry_interval)

        except Exception as e:
            logging.error("An error occurred during GPS fixing: %s", e)

        finally:
            # Clear the running flag to indicate the process has stopped
            self._gps_fix_running.clear()

    def _stop_gps_fix_process(self) -> None:
        """Stop the GPS fix process gracefully if it is running.

        This method clears the `_gps_fix_running` event flag to signal
        `gps_fix_process` to exit its loop. It then joins the thread to ensure
        it stops cleanly, preventing any residual processing or resource
        locking.
        """
        if self.gps_fix_is_running:
            # Clear the flag to stop the GPS fix process
            self._gps_fix_running.clear()

            # Join the thread to ensure it terminates completely
            if self._gps_fix_thread:
                self._gps_fix_thread.join()
                logging.info("GPS fix process stopped.")