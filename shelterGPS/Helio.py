# Standard library imports
import datetime as dt
import threading
import time
import subprocess
import logging
from enum import Enum
from typing import Optional, Tuple, Dict

# Third-party imports
from timezonefinder import TimezoneFinder
import pytz
from astral import sun, Observer

# Local application/library-specific imports
import sys
import os
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))
import shelterGPS.Position as pos
from shelterGPS.common import GPSNoFix
from lightlib.config import ConfigLoader
from lightlib.common import EPOCH_DATETIME, strftime, strfdate, strfdt
from lightlib.persist import PersistentData
from geocode.local import Location, InvalidLocationError
class SolarEvent(Enum):
    """Enumeration of key solar events for sun position calculations."""
    SUNRISE = "sunrise"
    SUNSET = "sunset"
    NOON = "noon"
    DAWN = "dawn"
    DUSK = "dusk"

class SunTimes:
    def __init__(self) -> None:
        self.sunrise_offset: int = ConfigLoader().sunrise_offset
        self.sunset_offset: int = ConfigLoader().sunset_offset
        self._init_dt()
        self._fix_err_day: int = 0
        self._fixed_today: bool = False
        self._gps_fix_running: threading.Event = threading.Event()
        self._gps_fix_thread: Optional[threading.Thread] = None
        logging.info(
            "SunTimes initialized with sunrise offset: %s minutes, sunset "
            "offset: %s minutes.", self.sunrise_offset, self.sunset_offset)

    def _init_dt(self):
        """Init all datetime vars to 01 jan 1970"""
        self._gps: pos.GPS = pos.GPS()
        self._sr_today = self._ss_today = EPOCH_DATETIME
        self._sr_tomorrow = self._ss_tomorrow = EPOCH_DATETIME
        self._fix_window: dict[str, dt.datetime] = {"start": EPOCH_DATETIME,
                                                    "end": EPOCH_DATETIME}
        self._local_tz = pytz.timezone('UTC')

    @property
    def gps_fix_is_running(self) -> bool:
        """Check if the GPS fix process is currently running.

        Returns:
            bool: `True` if the GPS fix process is actively running in a
            background thread; `False` otherwise.
        """
        return self._gps_fix_running.is_set()

    @property
    def UTC_sunrise_today(self) -> Optional[dt.datetime]:
        """Date and time of today's sunrise (UTC).

        Returns:
            dt.datetime: UTC date and time for today's sunrise
                         if set, otherwise None
        """
        return None if self._sr_today == EPOCH_DATETIME else self._sr_today

    @property
    def UTC_sunset_today(self) -> Optional[dt.datetime]:
        """Date and time of today's sunset (UTC).

        Returns:
            dt.datetime: UTC date and time for today's sunset
                         if set, otherwise None
        """
        return None if self._ss_today == EPOCH_DATETIME else self._ss_today

    @property
    def UTC_sunrise_tomorrow(self) -> Optional[dt.datetime]:
        """Date and time of tomorrows's sunrise (UTC).

        Returns:
            dt.datetime: UTC date and time for tomorrow's sunrise
                         if set, otherwise None
        """
        return None if self._sr_tomorrow == EPOCH_DATETIME else self._sr_tomorrow

    @property
    def UTC_sunset_tomorrow(self) -> Optional[dt.datetime]:
        """Date and time of tomorrows's sunset (UTC).

        Returns:
            dt.datetime: UTC date and time for tomorrows's sunset
                         if set, otherwise None
        """
        return None if self._ss_tomorrow == EPOCH_DATETIME else self._ss_tomorrow

    @property
    def local_tz(self) -> pytz.timezone:
        """Get the local timezone for the current GPS or configured location.

        Returns:
            timezone: A `pytz.timezone` object representing the local timezone,
            typically based on the GPS coordinates or configuration.
        """
        return self._local_tz

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
        return self._fixed_today == dt.datetime.now().date()

    @property
    def in_fix_window(self) -> bool:
        """Determine if the current time is within the defined GPS fixing window.

        This property checks if the current time falls within either today's or
        tomorrow's fixing window, as defined by the calculated solar event times
        (e.g., sunrise and sunset) with configurable offsets.

        Returns:
            bool: `True` if the current time is within today's or tomorrow's
            fixing window; `False` otherwise.
        """
        dt_now = dt.datetime.now()
        return ((self._fix_window["start_today"] <= dt_now <= \
                                             self._fix_window["end_today"]) or
            (self._fix_window["start_tomorrow"] <= dt_now <= \
                                             self._fix_window["end_tomorrow"]))
    def todays_window_is_set(self) -> bool:
        """Check if today's fixing window has been set."""
        return self._fix_window["start_today"].date() == dt.date.today()

    def start_gps_fix_process(self) -> None:
        """Start the GPS fix process in a separate thread if not already
        running.

        This method serves as the single entry point for the class, initiating a
        new background thread for GPS fixing to allow the rest of the program to
        continue operation.

        If a GPS fix process is already running or a fix has already been
        established today, the method will not restart the process. Otherwise,
        it will begin the GPS fix process.

        After a successful GPS fix, the system time is updated with the GPS
        time, and solar event times (sunrise, sunset) along with the fix_window
        for today and tomorrow are recalculated.

        The GPS fix position (latitude, longitude, altitude) along with solar
        event times for today and tomorrow are then saved to a local file.
        This data is stored for future use if a GPS fix cannot be obtained.

        If the GPS fix process cannot establish a fix, stored location data is
        used to calculate solar events, and the current system time is assumed
        accurate (No way of verifying).

        If no prior fix data exists and no location data is stored persistently,
        a fallback latitude and longitude are determined from the country and
        place name specified in the configuration file."""
        if not self.gps_fix_is_running:
            self._gps_fix_thread = threading.Thread(
                target=self._gps_fix_process, daemon=True)
            self._gps_fix_thread.start()
            logging.info("GPS fix process started in a separate thread.")

    def stop_gps_fix_process(self) -> None:
        """Stop the GPS fix process if it is running."""
        if self.gps_fix_is_running:
            self._gps_fix_running.clear()
            if self._gps_fix_thread:
                self._gps_fix_thread.join()
                logging.info("GPS fix process stopped.")

    def _attempt_fix_for_today(self) -> None:
        if self.fixed_today and self.todays_window_is_set():
            logging.debug("GPS fix and solar times already set for today.")
            return

        try:
            self._perform_gps_fix_attempts()
            self._set_solar_times_and_fix_window()
        except GPSNoFix:
            logging.warning("GPS fixing failed; reverting to local geo data.")
            self._use_local_geo()
            self._set_solar_times_and_fix_window()

    @staticmethod
    def calculate_solar_times(observer: Observer,
                              date: dt.date) -> Dict[str, dt.datetime]:
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
        """
        try:
            solar_times = {
            "sunrise": sun.sunrise(observer, date),
            "sunset": sun.sunset(observer, date)
            }
            logging.info("Calculated solar times at location "
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

    def _set_solar_times_and_fix_window(self) -> None:
        """
        Calculate and set solar times and fix windows for today and tomorrow
        based on the current geographic coordinates, updating local timezone.

        This method retrieves the current geographic coordinates, either from an
        active GPS fix or locally stored information. It then creates an
        `Observer` instance for calculating solar events and invokes
        `_set_solar_times` and `_set_fix_window` to establish the sunrise,
        unset, and GPS fix windows for today and tomorrow.

        Additionally, this method determines and sets the local timezone based
        on latitude and longitude.

        Returns:
            None
        """
        # Use the updated coordinates or fallback coordinates
        lat, lng, alt = self._get_coordinates()
        observer = Observer(latitude=lat, longitude=lng, elevation=alt)

        self._set_solar_times(observer)
        self._set_fix_window()

        # Determine the local timezone:
        tz_finder = TimezoneFinder()
        self._local_tz = pytz.timezone(
            tz_finder.timezone_at(lng = lng, lat = lat))

    def _set_solar_times(self, observer:Observer) -> None:
        """ Calculate and update UTC sunrise and sunset times for today and
        tomorrow based on the provided geographic position (observer).

        This method computes and stores solar event times (sunrise and sunset)
        for today and tomorrow using the `Observer` instance's geographic
        location (latitude, longitude, and optionally altitude). The calculated
        times are stored in attributes `_sr_today`, `_ss_today`, `_sr_tomorrow`, and
        `_ss_tomorrow` accessible through the properties `UTC_sunrise_today',
        `UTC_sunset_today`, `UTC_sunrise_tomorrow` and `UT_sunset_tomorrow` for
        future access.

        Args:
            observer (Observer): An instance of `Observer` containing the
                                 latitude, longitude, and optionally altitude
                                 for solar event calculation.

        Returns:
            None
        """
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)

        # Calculate today's solar times
        solar_times_today = SunTimes.calculate_solar_times(observer, today)
        self._sr_today = solar_times_today["sunrise"]
        self._ss_today = solar_times_today["sunset"]

        # Calculate tomorrow's solar times
        solar_times_tomorrow = SunTimes.calculate_solar_times(observer,
                                                              tomorrow)
        self._sr_tomorrow = solar_times_tomorrow["sunrise"]
        self._ss_tomorrow = solar_times_tomorrow["sunset"]

        logging.info("Updated solar events :\n"
                     "     Today: Sunrise: %s, Sunset: %s\n"
                     "  Tomorrow: Sunrise: %s, Sunset: %s",
                     strfdt(self._sr_today), strfdt(self._ss_today),
                     strfdt(self._sr_tomorrow), strfdt(self._ss_tomorrow))

    def _set_fix_window(self) -> None:
        """"Calculate and set the GPS fix windows for today and tomorrow based
        on sunrise and sunset times with configurable offsets.

        This method uses the UTC sunrise and sunset times for today and
        tomorrow, accessible through the `UTC_sunrise_today`,
        `UTC_sunset_today`, `UTC_sunrise_tomorrow`, and `UTC_sunset_tomorrow`
        properties. It applies the configurable `sunrise_offset` and
        `sunset_offset` (in minutes) to define the start and end times for GPS
        fix attempts on each day.

        The resulting fixing windows are stored in the `_fix_window` dictionary with
        the following keys:
            - `start_today`: Start time for today's fixing window
            - `end_today`: End time for today's fixing window
            - `start_tomorrow`: Start time for tomorrow's fixing window
            - `end_tomorrow`: End time for tomorrow's fixing window
        Determining if the current time is within the calculated fix window is
        achieved by accessing the boolean property `in_fix_window`

        Returns:
            None
        """
        # Define today's fixing window
        self._fix_window["start_today"] = self.UTC_sunrise_today + \
                                      dt.timedelta(minutes=self.sunrise_offset)
        self._fix_window["end_today"] = self.UTC_sunset_today + \
                                      dt.timedelta(minutes=self.sunset_offset)
        # Define tomorrow's fixing window
        self._fix_window["start_tomorrow"] = self.UTC_sunrise_tomorrow + \
                                      dt.timedelta(minutes=self.sunrise_offset)
        self._fix_window["end_tomorrow"] = self.UTC_sunset_tomorrow + \
                                      dt.timedelta(minutes=self.sunset_offset)

        logging.info("Updated fixing window :\n"
                     "   Today:     Start: %s,    End: %s\n"
                     "Tomorrow:     Start: %s,    End: %s",
                     strfdt(self._fix_window["start_today"]),
                     strfdt(self._fix_window["end_today"]),
                     strfdt(self._fix_window["start_tomorrow"]),
                     strfdt(self._fix_window["end_tomorrow"]))

    def _perform_gps_fix_attempts(self) -> None:
        """Attempt to obtain a GPS fix within the defined fixing window.

        This method attempts to obtain a GPS fix, retrying at intervals
        specified in the configuration if unsuccessful. The attempts are only
        made within a defined fixing window, and the method tracks consecutive
        failed attempts, halting after a configurable maximum failure
        threshold is reached.
        """
        max_fix_errors = ConfigLoader().gps_failed_fix_days
        while True:
            try:
                logging.info("Attempting GPS fix.")
                self._gps.get_fix()

                if self._gps.datetime_established and \
                   self._gps.position_established:
                    self._set_system_time()
                    self._fixed_today = dt.datetime.now().date
                    self._set_solar_times_and_fix_window()
                    self._store_persistent_data()
                    break
            except pos.GPSInvalid:
                self._fix_err_day += 1
                if self._fix_err_day >= max_fix_errors:
                    logging.error("Failed to fix for %s days.", max_fix_errors)
                    raise GPSNoFix(
                        f"Unable to obtain GPS fix for {max_fix_errors} days.")
            finally:
                self._gps.pwr_off()
            time.sleep(ConfigLoader().gps_fix_retry_interval)

    def _get_coordinates(self) -> Tuple[float, float, float]:
        """ Retrieve the geographic position, prioritizing GPS data if
        available, and falling back to locally stored information if GPS data
        is not established.

        This method checks if a GPS position is currently established. If so,
        it returns the GPS-provided latitude, longitude, and altitude. If a GPS
        position is not available, it falls back on locally stored or
        configuration-based data.

        Returns:
            Tuple[float, float, float]: A tuple containing latitude, longitude,
                                       and altitude.
        """
        if self._gps.position_established:
            return self._gps.latitude, self._gps.longitude, self._gps.altitude
        else:
            return self._use_local_geo()

def _use_local_geo(self) -> Tuple[float, float, float]:
    """
    Retrieve geographic coordinates and timezone from local persistent data
    or default configuration.

    This method first attempts to retrieve latitude, longitude, and altitude
    from locally stored persistent data. If these values are unavailable, it
    falls back to the default location data in the configuration.
    Additionally, it assigns `self._local_tz` to the timezone of the
    retrieved location.

    Raises:
        InvalidLocationError: If both persistent data and the configuration
                              lack valid location data.

    Returns:
        Tuple[float, float, float]: A tuple containing latitude, longitude,
                                    and altitude.
    """
    lat = PersistentData().current_latitude or Location().latitude
    lng = PersistentData().current_longitude or Location().longitude
    alt = PersistentData().current_altitude or 0.0

    # Validate that we have valid location data
    if lat is None or lng is None:
        logging.error("No valid location data available")
        raise InvalidLocationError("No valid location data available.")

    # Determine local timezone based on the coordinates
    tz_finder = TimezoneFinder()
    timezone_str = tz_finder.timezone_at(lat=lat, lng=lng)
    self._local_tz = pytz.timezone(timezone_str) if timezone_str else pytz.UTC

    return lat, lng, alt

    def _store_persistent_data(self) -> None:
        """Store the current GPS location and solar event times persistently.

        This method saves the current latitude, longitude, and altitude from
        the GPS data, along with sunrise and sunset times for today and
        tomorrow. This data is stored persistently for future reference,
        allowing fallback use if GPS fix is unavailable.

        Returns:
            None
        """
        # Save GPS location data
        PersistentData().current_latitude = self._gps.latitude
        PersistentData().current_longitude = self._gps.longitude
        PersistentData().current_altitude = self._gps.altitude

        # Save today's and tomorrow's solar event times
        PersistentData().add_sunrise_time(self.UTC_sunrise_today)
        PersistentData().add_sunrise_time(self.UTC_sunrise_tomorrow)
        PersistentData().add_sunset_time(self.UTC_sunset_today)

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
        self._gps_fix_running.set()  # Signal that the process is active
        try:
            while self._gps_fix_running.is_set():
                try:
                    self._attempt_fix_for_today()
                except Exception as e:
                    logging.error("An error occurred during GPS fixing: %s", e)
                # Wait for retry interval
                time.sleep(ConfigLoader().gps_fix_retry_interval)
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