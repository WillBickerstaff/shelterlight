"""shelterGPS.Helio.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Solar event determination
Author: Will Bickerstaff
Version: 0.1
"""

import datetime as dt
import threading
import time
import logging
import pytz
from timezonefinder import TimezoneFinder
from enum import Enum
from typing import Optional, Tuple, Dict, Union
from astral import sun, Observer
from lightlib.config import ConfigLoader
from lightlib.common import EPOCH_DATETIME
from lightlib.common import strfdt, get_today, get_tomorrow, get_now
from lightlib.persist import PersistentData
from shelterGPS.common import GPSNoFix, NoSolarEventError, InvalidObserverError
import shelterGPS.Position as pos
from geocode.local import Location, InvalidLocationError


class SolarEvent(Enum):
    """Enumeration of key solar events for sun position calculations."""

    SUNRISE = "sunrise"
    SUNSET = "sunset"
    NOON = "noon"
    DAWN = "dawn"
    DUSK = "dusk"


class PolarNightError(Exception):
    """Raised when the sun is always below the horizon."""

    pass


class PolarDayError(Exception):
    """Raised when the sun is always above the horizon."""

    pass


class PolarEvent(Enum):
    """Enumeration that identifies polar extremes."""

    NO = 0
    POLARDAY = 1
    POLARNIGHT = 2


class SunTimes:
    """Mange solar events."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of SunTimes is created.

        This method implements the Singleton pattern for the `GPS`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns
        -------
            GPS: A single instance of the `GPS` class.
        """
        if not cls._instance:
            with cls._lock:  # Thread-safe check and assignment
                if not cls._instance:
                    cls._instance = super(SunTimes, cls).__new__(cls)
                    cls._instance.__initialized = False

        return cls._instance

    def __init__(self) -> None:
        """Init SunTimes with config for solar offsets and GPS tracking."""
        if getattr(self, '_initialized', False):
            return

        self.sunrise_offset: int = ConfigLoader().sunrise_offset
        self.sunset_offset: int = ConfigLoader().sunset_offset
        self.__observer = None
        self._init_dt()
        self._fix_err_day: int = PersistentData().missed_fix_days
        self._fixed_today: bool = False
        self._gps_fix_running: threading.Event = threading.Event()
        self._gps_fix_thread: Optional[threading.Thread] = None
        self._polar = PolarEvent.NO
        self._initialized = True
        logging.debug(
            "SunTimes initialized with sunrise offset: %s minutes, sunset "
            "offset: %s minutes.", self.sunrise_offset, self.sunset_offset)

        # Try to set the fix window from local data on system startup
        if self._attempt_initial_fix_window():
            logging.info("Fix window established from local data on startup.")
        else:
            logging.warning(
                "No local data available. GPS fix process will start.")
            self.start_gps_fix_process()

    def _init_dt(self) -> None:
        """Init all datetime vars to 01 jan 1970."""
        self._gps: pos.GPS = pos.GPS()
        self._sr_today = self._ss_today = EPOCH_DATETIME
        self._sr_tomorrow = self._ss_tomorrow = EPOCH_DATETIME
        self._sr_next_day = self._ss_next_day = EPOCH_DATETIME
        self._fix_window: dict[str, dt.datetime] = {"start": EPOCH_DATETIME,
                                                    "end": EPOCH_DATETIME}
        self._local_tz = pytz.timezone('UTC')

    # ------------------------- Public Properties -----------------------------

    @property
    def gps_fix_is_running(self) -> bool:
        """Check if the GPS fix process is currently running.

        Returns
        -------
            bool: `True` if the GPS fix process is actively running in a
            background thread; `False` otherwise.
        """
        return self._gps_fix_running.is_set()

    @property
    def UTC_sunrise_today(self) -> Optional[dt.datetime]:
        """Date and time of today's sunrise (UTC).

        This will return the determined sunrise for today provided a valid
        lat & lng can be established which requires either a GPS fix to
        have been obtained, valid coordinates in persist.json or a valid
        location in the config file. If not set calling this property will
        attempt to populate the lat & lng first from persist.json then from
        the configured location in config.ini

        Returns
        -------
            dt.datetime: UTC date and time for today's sunrise. if not yet
            calculated the value from if it can be determined otherwise None.
        """
        # if not set try and get something in there
        if self._sr_today == EPOCH_DATETIME:
            # This first trys to determine a location through _get_coordinates
            # or _use_local_geo
            self._set_solar_times(self.local_observer)

        # Should be set, if not we are getting None from PersistentData
        return PersistentData().sunrise_today if  \
            self._sr_today == EPOCH_DATETIME else self._sr_today

    @property
    def UTC_sunset_today(self) -> Optional[dt.datetime]:
        """Date and time of today's sunset (UTC).

        This will return the determined sunset for today provided a valid
        lat & lng can be established which requires either a GPS fix to
        have been obtained, valid coordinates in persist.json or a valid
        location in the config file. If not set calling this property will
        attempt to populate the lat & lng first from persist.json then from
        the configured location in config.ini

        Returns
        -------
            dt.datetime: UTC date and time for today's sunset. if not yet
            calculated the value from if it can be determined otherwise None.
        """
        # if not set try and get something in there
        if self._ss_today == EPOCH_DATETIME:
            # This first trys to determine a location through _get_coordinates
            # or _use_local_geo
            self._set_solar_times(self.local_observer)

        # Should be set, if not we are getting None from PersistentData
        return PersistentData().sunrise_today if  \
            self._ss_today == EPOCH_DATETIME else self._ss_today

    @property
    def UTC_sunrise_tomorrow(self) -> Optional[dt.datetime]:
        """Date and time of tomorrow's sunrise (UTC).

        This will return the determined sunrise for tomorrow provided a valid
        lat & lng can be established which requires either a GPS fix to
        have been obtained, valid coordinates in persist.json or a valid
        location in the config file. If not set calling this property will
        attempt to populate the lat & lng first from persist.json then from
        the configured location in config.ini

        Returns
        -------
            dt.datetime: UTC date and time for tomorrow's sunrise. if not yet
            calculated the value from if it can be determined otherwise None.
        """
        # if not set try and get something in there
        if self._sr_tomorrow == EPOCH_DATETIME:
            # This first trys to determine a location through _get_coordinates
            # or _use_local_geo
            self._set_solar_times(self.local_observer)

        # Should be set, if not we are getting None from PersistentData
        return PersistentData().sunrise_today if  \
            self._sr_tomorrow == EPOCH_DATETIME else self._sr_tomorrow

    @property
    def UTC_sunset_tomorrow(self) -> Optional[dt.datetime]:
        """Date and time of tomorrow's sunset (UTC).

        This will return the determined sunset for tomorrow provided a valid
        lat & lng can be established which requires either a GPS fix to
        have been obtained, valid coordinates in persist.json or a valid
        location in the config file. If not set calling this property will
        attempt to populate the lat & lng first from persist.json then from
        the configured location in config.ini

        Returns
        -------
            dt.datetime: UTC date and time for tomorrow's sunset. if not yet
            calculated the value from if it can be determined otherwise None.
        """
        # if not set try and get something in there
        if self._ss_tomorrow == EPOCH_DATETIME:
            # This first trys to determine a location through _get_coordinates
            # or _use_local_geo
            self._set_solar_times(self.local_observer)

        # Should be set, if not we are getting None from PersistentData
        return PersistentData().sunrise_today if  \
            self._ss_tomorrow == EPOCH_DATETIME else self._ss_tomorrow

    @property
    def local_tz(self) -> pytz.timezone:
        """Get the local timezone for the current GPS or configured location.

        Returns
        -------
            timezone: A `pytz.timezone` object representing the local timezone,
            typically based on the GPS coordinates or configuration.
        """
        return self._local_tz

    @property
    def failed_fix_days(self) -> int:
        """Number of consecutive days with failed GPS fix attempts.

        Returns
        -------
            int: Count of consecutive failed GPS fix days.
        """
        return self._fix_err_day

    @failed_fix_days.setter
    def failed_fix_days(self, value: int = 0) -> None:
        """Reset the counter for consecutive failed GPS fix attempts.

        Args
        ----
            value (int): The value to set to, Default is zero, which will reset
            the counter.
        """
        logging.info("GPS: Resetting failed_fix_days to %s.", value)
        self._fix_err_day = value

    @property
    def fixed_today(self) -> bool:
        """Indicate if a GPS fix has been obtained for the current date.

        Returns
        -------
            bool: `True` if a GPS fix was successfully obtained today, `False`
            otherwise.
        """
        return self._fixed_today == get_today()

    @property
    def todays_window_is_set(self) -> bool:
        """Return True if today's solar fix window is set."""
        return (self.UTC_sunrise_today is not None and
                self.UTC_sunset_today is not None)

    @property
    def in_fix_window(self) -> bool:
        """Determine if the current time is within the GPS fixing window.

        This property checks if the current time falls within either today's or
        tomorrow's fixing window, defined by the calculated solar event times
        (e.g., sunrise and sunset) with configurable offsets.

        Returns
        -------
            bool: `True` if the current time is within today's or tomorrow's
            fixing window; `False` otherwise.
        """
        if ConfigLoader().bypass_fix_window:
            logging.warning(
                "Bypassing GPS fix window (bypass_fix_window=True)")
            return True

        dt_now = get_now()
        return ((self._fix_window["start_today"] <= dt_now <=
                 self._fix_window["end_today"]) or
                (self._fix_window["start_tomorrow"] <= dt_now <=
                 self._fix_window["end_tomorrow"]))

    @property
    def local_observer(self) -> Observer:
        """Get an astral.Observer for use in position and solar calcs.

        Returns
        -------
        astral.Observer - Containing the current latitude, longitude and
                          altitude if known, otherwis None
        """
        if self.__observer is not None:
            return self.__observer
        try:
            lat, lng, alt = self._get_coordinates()
            self.__observer = Observer(latitude=lat, longitude=lng,
                                       elevation=alt)
            return self.__observer
        except InvalidLocationError:
            logging.error("Observer can not be created")
            return None

    @property
    def is_polar_event(self) -> PolarEvent:
        """Return if the current data is a Polar day or Polar Night.

        Returns
        -------
        Enum(PolarEvent) - Any of POLARDAY, POLARNIGHT or NO
        """
        return self._polar

    # --------------------- Core Methods for GPS Fixing -----------------------

    def start_gps_fix_process(self) -> None:
        """Start the GPS fix process in a separate thread if not running.

        Serves as the single entry point for the class, initiating a
        new background thread for GPS fixing to allow the rest of the program
        to continue operation.

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

        If no prior fix data exists and no location data is stored
        persistently, a fallback latitude and longitude are determined from
        the country and place name specified in the configuration file.
        """
        if not self.gps_fix_is_running:
            self._gps_fix_thread = threading.Thread(
                target=self._gps_fix_process, daemon=True)
            self._gps_fix_thread.start()

    def stop_gps_fix_process(self) -> None:
        """Stop the GPS fix process if it is running."""
        if self.gps_fix_is_running:
            self._gps_fix_running.clear()
            if self._gps_fix_thread:
                self._gps_fix_thread.join()

    def _gps_fix_process(self) -> None:
        """Periodically attempt a GPS fix within a fix attempt window.

        This method runs in a loop, attempting a GPS fix within each interval
        specified by `ConfigLoader().fix_retry_interval`. It checks the
        `_gps_fix_running` flag to determine if the loop should continue,
        allowing for controlled shutdown.

        Raises
        ------
            Exception: Logs any unexpected errors that occur during the GPS
                       fixing process.
        """
        self._gps_fix_running.set()  # Signal that the process is active
        try:
            while self._gps_fix_running.is_set():
                try:
                    self._attempt_fix_for_today()
                except Exception as e:
                    logging.error("An error occurred during GPS fixing: %s",
                                  e, exc_info=True)
                # Wait for retry interval
                time.sleep(ConfigLoader().gps_fix_retry_interval)
        finally:
            # Clear the running flag to indicate the process has stopped
            self._gps_fix_running.clear()

    def _attempt_fix_for_today(self) -> None:
        """Attempt GPS fix if not already fixed for today."""
        if self.fixed_today and self.todays_window_is_set:
            logging.debug("GPS fix and solar times already set for today.")
            return

        try:
            self._perform_gps_fix_attempts()
        except GPSNoFix:
            logging.warning("GPS fixing failed; reverting to locally "
                            "configured geographic information.")
            self._use_local_geo()
            self._set_solar_times_and_fix_window()

        except NoSolarEventError:
            # A polar condition (either no sunrise or no sunset) has occurred.
            # If this is a polar day (sun never sets), we skip light scheduling
            # entirely — no darkness period exists.
            # If it's a polar night (sun never rises),
            #     we still generate a schedule,
            # as darkness persists throughout the day.
            # In both cases, we clear the fix window to prevent retries
            #     and log the event.
            logging.warning("Polar day/night condition detected. "
                            "Proceeding with appropriate handling.")
            self._fix_window = {
                "start_today": dt.datetime.min,
                "end_today": dt.datetime.min,
                "start_tomorrow": dt.datetime.min,
                "end_tomorrow": dt.datetime.min
            }

    def _perform_gps_fix_attempts(self) -> None:
        """Attempt to obtain a GPS fix within the defined fixing window.

        This method attempts to obtain a GPS fix, retrying at intervals
        specified in the configuration if unsuccessful. The attempts are only
        made within a defined fixing window, and the method tracks consecutive
        failed attempts, halting after a configurable maximum failure
        threshold is reached.
        """
        max_fix_errors = ConfigLoader().gps_failed_fix_days
        wait_time = ConfigLoader().gps_pwr_up_time
        fix_start_time = time.monotonic()
        while True:
            try:
                logging.info("Attempting GPS fix.")
                # Wait for gps to power up
                self._gps.get_fix(pwr_up_wait=wait_time)

                if self._gps.datetime_established and \
                        self._gps.position_established:
                    # End fix timing and store duration
                    PersistentData().time_to_fix = (
                        fix_start_time, time.monotonic())
                    self._fixed_today = get_now().date()
                    logging.info("GPS Fix succeeded, position & "
                                 "time established")
                    #  Update solar times and fix window based on GPS
                    #  coordinates
                    self._set_solar_times_and_fix_window()
                    self._store_persistent_data()
                    break

            except pos.GPSInvalid:
                self._fix_err_day += 1
                logging.debug("GPS failed to fix:\n\t"
                              "GPS Position: %s\tEstabilshed: %s\n\t"
                              "GPS Datetime: %s\tEstablished: %s",
                              self._gps.position_str,
                              self._gps.position_established,
                              self._gps.datetime,
                              self._gps.datetime_established)
                if self._fix_err_day >= max_fix_errors:
                    logging.error("Failed to fix for %s days.", max_fix_errors)
                    raise GPSNoFix(
                        f"Unable to obtain GPS fix for {max_fix_errors} days.")
            logging.debug("No fix on this attempt:\n\t"
                          "GPS Position: %s\tEstablished: %s\n\t"
                          "GPS Datetime: %s\tEstablished: %s\n",
                          self._gps.position_str,
                          self._gps.position_established,
                          self._gps.datetime,
                          self._gps.datetime_established)
            time.sleep(ConfigLoader().gps_fix_retry_interval)

    # -------------------- Solar Times and Fix Window Setup -------------------

    def _attempt_initial_fix_window(self) -> bool:
        """Set initial solar times and fix window.

        Attempts to set the initial solar times and fix window from locally
        stored data. Returns True if successful, False otherwise.
        """
        try:
            self._set_solar_times(self.local_observer)
            self._set_fix_window()
            return True
        except InvalidLocationError:
            logging.warning("No valid local location data available.")
            return False

    def _set_solar_times_and_fix_window(self) -> None:
        """Calculate solar events and fix window.

        Calculate and set solar times and fix windows for today and tomorrow
        based on the current geographic coordinates, updating local timezone.

        Retrieves the current geographic coordinates, either from an
        active GPS fix or locally stored information. It then creates an
        `Observer` instance for calculating solar events and invokes
        `_set_solar_times` and `_set_fix_window` to establish the sunrise,
        unset, and GPS fix windows for today and tomorrow.

        Also determines and sets the local timezone based
        on latitude and longitude.

        Returns
        -------
            None
        """
        self._set_solar_times(self.local_observer)
        self._set_fix_window()

    def _set_solar_times(self, observer: Observer) -> None:
        """Calculate and update UTC sunrise and sunset times.

        For today and tomorrow and the following day based on the provided
        geographic position (observer).

        This method computes and stores solar event times (sunrise and sunset)
        for today and the next 2 days using the `Observer` instance's
        geographic location (latitude, longitude, and optionally altitude).
        The calculated times stored in attributes `_sr_today`, `_ss_today`,
        `_sr_tomorrow`, and `_ss_tomorrow` accessible through the properties
        `UTC_sunrise_today', `UTC_sunset_today`, `UTC_sunrise_tomorrow` and
        `UTC_sunset_tomorrow` for future access.

        Args
        ----
            observer (Observer): An instance of `Observer` containing the
                                 latitude, longitude, and optionally altitude
                                 for solar event calculation.

        Returns
        -------
            None
        """
        today = get_today()
        tomorrow = get_tomorrow()
        next_day = get_tomorrow() + dt.timedelta(days=1)

        # Calculate today's solar times
        try:
            solar_times_today = SunTimes.calculate_solar_times(observer, today)
        except PolarDayError:
            self._polar = PolarEvent.POLARDAY
        except PolarNightError:
            self._polar = PolarEvent.POLARNIGHT

        self._sr_today = solar_times_today["sunrise"]
        self._ss_today = solar_times_today["sunset"]

        # Calculate tomorrow's solar times
        try:
            solar_times_tomorrow = SunTimes.calculate_solar_times(observer,
                                                                  tomorrow)
        except (PolarDayError, PolarNightError):
            pass
        self._sr_tomorrow = solar_times_tomorrow["sunrise"]
        self._ss_tomorrow = solar_times_tomorrow["sunset"]

        # Calculate the same events in 2 days time
        try:
            solar_times_next_day = SunTimes.calculate_solar_times(observer,
                                                                  next_day)
        except (PolarDayError, PolarNightError):
            pass
        self._sr_next_day = solar_times_next_day["sunrise"]
        self._ss_next_day = solar_times_next_day["sunset"]

        self._store_persistent_data()

        logging.info("Updated solar events:\n"
                     "     Today: Sunrise: %s, Sunset: %s\n"
                     "  Tomorrow: Sunrise: %s, Sunset: %s\n"
                     " Day after: Sunrise: %s, Sunset: %s",
                     strfdt(self._sr_today), strfdt(self._ss_today),
                     strfdt(self._sr_tomorrow), strfdt(self._ss_tomorrow),
                     strfdt(self._sr_next_day), strfdt(self._ss_next_day))

    def _set_fix_window(self) -> None:
        """Calculate and set the GPS fix windows.

        For today and tomorrow based on sunrise and sunset times with
        configurable offsets.

        This method uses the UTC sunrise and sunset times for today and
        tomorrow, accessible through the `UTC_sunrise_today`,
        `UTC_sunset_today`, `UTC_sunrise_tomorrow`, and `UTC_sunset_tomorrow`
        properties. It applies the configurable `sunrise_offset` and
        `sunset_offset` (in minutes) to define the start and end times for GPS
        fix attempts on each day.

        The resulting fixing windows are stored in the `_fix_window` dictionary
        with the following keys:
            - `start_today`: Start time for today's fixing window
            - `end_today`: End time for today's fixing window
            - `start_tomorrow`: Start time for tomorrow's fixing window
            - `end_tomorrow`: End time for tomorrow's fixing window
        Determining if the current time is within the calculated fix window is
        achieved by accessing the boolean property `in_fix_window`

        Returns
        -------
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

        logging.debug("Updated fixing window :\n"
                      "   Today:     Start: %s,    End: %s\n"
                      "Tomorrow:     Start: %s,    End: %s",
                      strfdt(self._fix_window["start_today"]),
                      strfdt(self._fix_window["end_today"]),
                      strfdt(self._fix_window["start_tomorrow"]),
                      strfdt(self._fix_window["end_tomorrow"]))

    # ---------------------- Coordinate and System Helpers --------------------

    def _get_coordinates(self) -> Tuple[float, float, float]:
        """Retrieve the geographic position.

        Prioritize GPS data if available,
        Fall back to locally stored information if GPS data
        is not established.

        This method checks if a GPS position is currently established. If so,
        it returns the GPS-provided latitude, longitude, and altitude. If a GPS
        position is not available, it falls back on locally stored or
        configuration-based data.

        Returns
        -------
            Tuple[float, float, float]: A tuple containing latitude, longitude,
            and altitude.
        """
        if self._gps.position_established:
            return self._gps.latitude, self._gps.longitude, self._gps.altitude
        else:
            return self._use_local_geo()

    def _use_local_geo(self) -> Tuple[float, float, float]:
        """Get coordinates and tz from persitent data.

        Retrieve geographic coordinates and timezone from local persistent data
        or default configuration.

        First attempts to retrieve latitude, longitude, and altitude
        from locally stored persistent data. If unavailable, it
        falls back to the default location data in the configuration.
        Additionally, it assigns `self._local_tz` to the timezone of the
        retrieved location.

        Raises
        ------
            InvalidLocationError: If both persistent data and the configuration
                                lack valid location data.

        Returns
        -------
            Tuple[float, float, float]: A tuple containing latitude, longitude,
                                        and altitude.
        """
        # Prefer persistent data over config defined location as this
        # pobably contains an actual GPS fix
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
        self._local_tz = pytz.timezone(timezone_str) if timezone_str \
            else pytz.UTC

        return lat, lng, alt

    def _store_persistent_data(self) -> None:
        """Store the current GPS location and solar event times persistently.

        This method saves the current latitude, longitude, and altitude from
        the GPS data, along with sunrise and sunset times for today and
        tomorrow. This data is stored persistently for future reference,
        allowing fallback use if GPS fix is unavailable.

        Returns
        -------
            None
        """
        logging.debug("Populating persistent Data for JSON storage")
        persist = PersistentData()
        # Save GPS location data
        persist.current_latitude = self._gps.latitude
        persist.current_longitude = self._gps.longitude
        persist.current_altitude = self._gps.altitude
        persist.missed_fix_days = self.failed_fix_days

        # Save today's and tomorrow's solar event times
        persist.add_sunrise_time(self.UTC_sunrise_today)
        persist.add_sunrise_time(self.UTC_sunrise_tomorrow)
        persist.add_sunrise_time(self._sr_next_day)
        persist.add_sunset_time(self.UTC_sunset_today)
        persist.add_sunset_time(self.UTC_sunset_tomorrow)
        persist.add_sunset_time(self._ss_next_day)
        persist.store_data()

    @staticmethod
    def calculate_solar_times(
            observer: Observer,
            date: dt.date) -> Dict[str, Union[dt.datetime, PolarEvent]]:
        """Calculate the solar event times for an observer, location and date.

        This method calculates UTC sunrise and sunset times for a given date
        and observer. It handles polar conditions (e.g. no sunrise or sunset)
        by assigning fallback times and raising appropriate exceptions while
        still returning usable values for schedule calculation.

        If polar conditions are detected:
        - PolarNightError is raised when there is no sunrise (permanent night).
        - PolarDayError is raised when there is no sunset (permanent day).

        Returns
        -------
        Dict[str, Union[datetime.datetime, PolarEvent]]
            A dictionary with the following keys:
            - "sunrise": datetime.datetime
                The calculated (or fallback) UTC time of sunrise.
            - "sunset": datetime.datetime
                The calculated (or fallback) UTC time of sunset.
            - "polar": PolarEvent
                Enum indicating whether this is a normal day, polar day, or
                polar night.

        Raises
        ------
        PolarDayError
            If the sun does not set (permanent day).
        PolarNightError
            If the sun does not rise (permanent night).
        InvalidObserverError
            If the observer data is invalid or unusable.
        """
        logging.debug("Calculate solar events for location %s, %s on date %s",
                      round(observer.latitude, 2),
                      round(observer.longitude, 2),
                      date.isoformat())
        polar = PolarEvent.NO
        try:
            # Default to actual sunrise/sunset values
            try:
                sunrise = sun.sunrise(observer, date)
            except ValueError as ve:
                msg = str(ve)
                if "Sun is always below the horizon" in msg or \
                        "Unable to find a sunrise time" in msg:
                    sunrise = dt.datetime.combine(
                        date, dt.time(11, 59, 59), dt.timezone.utc)
                    sunset = dt.datetime.combine(
                        date, dt.time(12, 0, 0), dt.timezone.utc)
                    logging.warning("Polar night (no sunrise): %s", msg)
                    polar = PolarEvent.POLARNIGHT
                    raise PolarNightError("Polar night: no sunrise.") from ve
                elif "Sun is always above the horizon" in msg:
                    sunrise = dt.datetime.combine(
                        date, dt.time(0, 0, 1), dt.timezone.utc)
                    sunset = dt.datetime.combine(
                        date, dt.time(23, 59, 59), dt.timezone.utc)
                    logging.warning("Polar day (no sunrise): %s", msg)
                    polar = PolarEvent.POLARDAY
                    raise PolarDayError("Polar day: no sunrise.") from ve
                else:
                    raise

            try:
                sunset = sun.sunset(observer, date)
            except ValueError as ve:
                msg = str(ve)
                if "Sun is always above the horizon" in msg or \
                        "Unable to find a sunset time" in msg:
                    sunrise = dt.datetime.combine(
                        date, dt.time(0, 0, 1), dt.timezone.utc)
                    sunset = dt.datetime.combine(
                        date, dt.time(23, 59, 59), dt.timezone.utc)
                    logging.warning("Polar day (no sunset): %s", msg)
                    polar = PolarEvent.POLARDAY
                    raise PolarDayError("Polar day: no sunset.") from ve
                elif "Sun is always below the horizon" in msg:
                    sunrise = dt.datetime.combine(
                        date, dt.time(11, 59, 59), dt.timezone.utc)
                    sunset = dt.datetime.combine(
                        date, dt.time(12, 0, 0), dt.timezone.utc)
                    logging.warning("Polar night (no sunset): %s", msg)
                    polar = PolarEvent.POLARNIGHT
                    raise PolarNightError("Polar night: no sunset.") from ve
                else:
                    raise

            solar_times = {"sunrise": sunrise, "sunset": sunset,
                           "polar": polar}
            logging.debug("Calculated solar times at location %s, %s"
                          "\n\tfor     : %s"
                          "\n\tSunrise : %s"
                          "\n\tSunset  : %s"
                          "\n\tPolar Event: %s ",
                          round(observer.latitude, 2),
                          round(observer.longitude, 2),
                          date, sunrise.isoformat(),
                          sunset.isoformat(), polar.name)
            return solar_times

        except InvalidObserverError as ioe:
            logging.error("Invalid location (Bad Observer) using default day "
                          "for sunrise and sunset : %s", ioe)
            # Fallback to default day if location totally broken
            sunrise = dt.datetime.combine(
                date, dt.time(10, 0, 0), dt.timezone.utc)
            sunset = dt.datetime.combine(
                date, dt.time(16, 0, 0), dt.timezone.utc)
            return {"sunrise": sunrise, "sunset": sunset,
                    "polar": PolarEvent.NO}

        except (PolarDayError, PolarNightError):
            # Let known polar errors propagate for specific handling
            raise

        except Exception as ex:
            logging.error("Unexpected error in solar time calculation: %s",
                          ex, exc_info=True)
            raise InvalidObserverError(f"Unexpected failure: {ex}") from ex

    def cleanup(self):
        """Stop fix thread and clean up GPS."""
        self.stop_gps_fix_process()
        self._gps.cleanup()
