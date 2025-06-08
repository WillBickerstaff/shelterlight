"""lightlib.persist.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Persistent data manager.

Manages persistent data across power cycles. Allowing for location,
and sunrise, sunset times to be known before a GPS fix is obtained should a
power failure occur.

Author: Will Bickerstaff
Version: 0.1
"""

import json
import datetime as dt
import logging
import pytz
from typing import Union, Optional, List
from threading import Lock
from timezonefinder import TimezoneFinder
from shelterGPS.common import SolarEvent
from lightlib.config import ConfigLoader
from lightlib.common import iso_to_datetime, datetime_to_iso, get_today, \
    get_tomorrow, get_now


class DataStoreError(Exception):
    """Base class for exceptions in the GPSDataStore."""

    pass


class DataStorageError(DataStoreError):
    """Raised when storing data in the JSON file fails."""

    pass


class DataRetrievalError(DataStoreError):
    """Raised when retrieving data from the JSON file fails."""

    pass


class PersistentData:
    """Store GPS and time data in JSON format to persist across power cycles.

    Manages the storage and retrieval of GPS data, including latitude,
    longitude, maximum time to obtain a fix, and sunrise and sunset times for
    today and the next seven days.
    """

    _instance = None
    _lock = Lock()  # Thread-safe lock for instance creation

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of PersistentData is created.

        This method implements the Singleton pattern for the `PersistentData`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns
        -------
            GPS: A single instance of the `PersistentData` class.
        """
        if not cls._instance:
            with cls._lock:  # Thread-safe check and assignment
                if not cls._instance:
                    cls._instance = super(PersistentData, cls).__new__(cls)
                    cls._instance.__initialized = False
        return cls._instance

    def __init__(self, file_path: str = "persist.json"):
        """Initialize PersistentData with a JSON file.

        This class makes available data stored in the persistent data file
        defined in the config file. If the file does not exist, it is created
        and populated with any known values when `store_data` is called. If the
        data file does exist then the class properties will give direct access
        to all available values, returning `None` if they are not set.

        Args
        ----
            file_path (str): Path to the JSON file for data storage.

        Raises
        ------
            DataStorageError: If the JSON file cannot be initialized.
        """
        if self.__initialized:
            return  # Skip reinitialization for singleton pattern
        self._sunrise_times = []
        self._sunset_times = []
        self._dawn_times = []
        self._dusk_times = []
        self._current_latitude = None
        self._current_longitude = None
        self._current_altitude = None
        self._local_timezone = None
        self._missed_fixes = 0
        self._time_to_fix = None
        self._initialize_file()
        # Mark as initialized
        self._populate_locals_from_file()
        self.__initialized = True

    @staticmethod
    def _get_empty_schema(version: int = 1) -> dict:
        """Return the default empty JSON structure for persistent data."""
        match version:
            case 1:
                return {
                    "schema_version": 1,
                    "missed_fixes": 0,
                    "last_latitude": None,
                    "last_longitude": None,
                    "local_timezone": None,
                    "altitude": None,
                    "sunrise_times": [],
                    "sunset_times": [],
                    "dawn_times": [],
                    "dusk_times": [],
                    "last_updated": None,
                    "time_to_fix": 2
                }
            case _:
                logging.error("Unsupported schema version %s, falling back "
                              "to version 1", version)
                return PersistentData._get_empty_schema(1)

    def _initialize_file(self) -> None:
        """Init JSON file if doesn't exist, create an empty data structure."""
        try:
            # Create a basic structure if the JSON file does not exist
            logging.debug(
                "Attempting to initialize data storage file %s",
                ConfigLoader().persistent_data_json)
            with open(ConfigLoader().persistent_data_json, 'a+') as file:
                file.seek(0)
                if file.read().strip() == "":
                    json.dump(self._get_empty_schema(), file,
                              indent=2, sort_keys=True)
                    logging.info("JSON file initialized at %s",
                                 ConfigLoader().persistent_data_json)
        except IOError as e:
            logging.error("Failed to initialize JSON file: %s", e)
            raise DataStorageError("Failed to initialize JSON file.") from e

    def store_data(self) -> None:
        """Store the latest GPS data in the JSON file, overwrite existing.

        Raises
        ------
            DataStorageError: If storing data in the JSON file fails.
        """
        try:
            data = self._get_empty_schema()
            data.update({
                "missed_fixes": self.missed_fix_days,
                "latitude": self.current_latitude,
                "longitude": self.current_longitude,
                "altitude": self.current_altitude,
                "local_timezone": self.local_timezone_zone,
                "sunrise_times":
                    [datetime_to_iso(t) for t in self._sunrise_times],
                "sunset_times":
                    [datetime_to_iso(t) for t in self._sunset_times],
                "dawn_times":
                    [datetime_to_iso(t) for t in self._dawn_times],
                "dusk_times":
                    [datetime_to_iso(t) for t in self._dusk_times],
                "last_updated": datetime_to_iso(get_now()),
                "time_to_fix": self.time_to_fix
            })

            with open(ConfigLoader().persistent_data_json, 'w') as file:
                json.dump(data, file, indent=2, sort_keys=True)
                logging.debug("Data stored successfully in JSON file.")

            # Refresh local convenience attributes
            self._populate_locals_from_file()
        except IOError as e:
            logging.error("Failed to store Data in JSON: %s", e)
            raise DataStorageError("Failed to store data in JSON.") from e

    def _set_tz(self) -> None:
        """Determine the local timezone."""
        if not (self.current_latitude and self.current_longitude):
            return
        tz_finder = TimezoneFinder()
        self.local_timezone = pytz.timezone(tz_finder.timezone_at(
            lng=self.current_longitude, lat=self.current_latitude))
        logging.info("Local timezone set to %s", self.local_timezone)

    def _warn_once(self, flag_attr: str, missing_date: dt.date, message: str):
        """Warn only once daily for data missing from persistent data file.

        Args
        ----
            flag_attr(str): Tracking variable name.
            missing_date(dt,date): The date that is missing in persistent data.
            message(str): An associated message to include in the log entry.
        """
        if not hasattr(self, flag_attr):
            setattr(self, flag_attr, None)
        if getattr(self, flag_attr) != get_today():
            logging.error(message, missing_date)
            setattr(self, flag_attr, get_tomorrow())

    @property
    def local_timezone(self) -> Optional[pytz.tzinfo.BaseTzInfo]:
        """Local timezone of the systems location."""
        if self._local_timezone:
            return self._local_timezone
        return None

    @local_timezone.setter
    def local_timezone(self, value: Union[str, pytz.tzinfo.BaseTzInfo]):
        """Accepts a timezone name string or a pytz timezone object."""
        try:
            if value is None:
                logging.warning("No timezone known, falling back to UTC.")
                self._local_timezone = pytz.UTC
            elif isinstance(value, str):
                self._local_timezone = pytz.timezone(value)
            elif isinstance(value, pytz.tzinfo.BaseTzInfo):
                self._local_timezone = value
            else:
                raise TypeError(f"Unsupported timezone type: {type(value)}")
        except pytz.UnknownTimeZoneError:
            logging.warning("Unknown timezone '%s'. Falling back to UTC.",
                            value)
            self._local_timezone = pytz.UTC

    @property
    def local_timezone_zone(self) -> Optional[str]:
        """Local timezone zone string."""
        if self.local_timezone is not None:
            return self.local_timezone.zone
        return None

    @property
    def time_to_fix(self) -> int:
        """Duration of how long GPS previously took to establish a fix in S.

        Returns
        -------
            int|None: The time value in seconds of how long the last fix took,
                      None if nothing is stored
        """
        if isinstance(self._time_to_fix, int):
            return int(self._time_to_fix)
        return ConfigLoader().gps_pwr_up_time

    @time_to_fix.setter
    def time_to_fix(self, start_to_end: tuple[float, float]) -> None:
        fix_start, fix_end = start_to_end
        fix_dur = int(fix_end - fix_start)
        if 0 < fix_dur < 600:
            self._time_to_fix = fix_dur
            logging.info("GPS took %ds to obtain a fix.", fix_dur)
        else:
            logging.warning("%s fix duration  (%ds), "
                            "fix time of 2 minutes assumed. "
                            "Consider adjusting the the GPS antenna.",
                            "High" if fix_dur >= 600 else "Invalid", fix_dur)
            self._time_to_fix = 120

    @property
    def current_altitude(self) -> float:
        """GPS altitude from persistent data."""
        return self._current_altitude

    @current_altitude.setter
    def current_altitude(self, altitude: float) -> None:
        self._current_altitude = altitude

    @property
    def current_latitude(self) -> float:
        """GPS latitude from persistent data."""
        return self._current_latitude

    @current_latitude.setter
    def current_latitude(self, lat: float) -> None:
        self._current_latitude = lat
        self._set_tz()

    @property
    def current_longitude(self) -> float:
        """GPS Longitude from persistent data."""
        return self._current_longitude

    @current_longitude.setter
    def current_longitude(self, lng: float) -> None:
        self._current_longitude = lng
        self._set_tz()

    @property
    def missed_fix_days(self) -> int:
        """Number of days a fix has been unobtainable."""
        return self._missed_fixes

    @missed_fix_days.setter
    def missed_fix_days(self, missed_days: int) -> None:
        self._missed_fixes = missed_days

    @property
    def sunrise_times(self) -> List[dt.datetime]:
        """Datetime object List of sunrise times from persistent data."""
        return self._sunrise_times

    @property
    def sunset_times(self) -> List[dt.datetime]:
        """Datetime object list of sunset times from persistent data."""
        return self._sunset_times

    @property
    def dawn_times(self) -> List[dt.datetime]:
        """Datetime object list of dawn times from persistent data."""
        return self._dawn_times

    @property
    def dusk_times(self) -> List[dt.datetime]:
        """Datetime object list of dusk times from persistent data."""
        return self._dusk_times

    @property
    def dawn_today(self) -> Optional[dt.datetime]:
        """Today's dawn time from persistent data (first visible light)."""
        try:
            return PersistentData._date_in_dates(check_date=get_today(),
                                                 dates_list=self.dawn_times)
        except DataRetrievalError:
            self._warn_once("dawn_today", get_today(),
                            "%s not found in persistent data dawn times")
            return None

    @property
    def sunrise_today(self) -> Optional[dt.datetime]:
        """Today's sunrise time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=get_today(),
                                                 dates_list=self.sunrise_times)
        except DataRetrievalError:
            self._warn_once("sunrise_today", get_today(),
                            "%s not found in persistent data sunrise times")
            return None

    @property
    def dusk_today(self) -> Optional[dt.datetime]:
        """Today's dusk time from persistent data."" (last visible light)."""
        try:
            return PersistentData._date_in_dates(check_date=get_today(),
                                                 dates_list=self.dusk_times)
        except DataRetrievalError:
            self._warn_once("dusk_today", get_today(),
                            "%s not found in persistent data dusk times")
            return None

    @property
    def sunset_today(self) -> Optional[dt.datetime]:
        """Today's sunset time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=get_today(),
                                                 dates_list=self.sunset_times)
        except DataRetrievalError:
            self._warn_once("sunset_today", get_today(),
                            "%s not found in persistent data sunset times")
            return None

    @property
    def dawn_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows dawn time from persistent data (first visible light)."""
        try:
            return PersistentData._date_in_dates(check_date=get_tomorrow(),
                                                 dates_list=self.dawn_times)
        except DataRetrievalError:
            self._warn_once("dawn_tomorrow", get_tomorrow(),
                            "%s not found in persistent data dawn times")
            return None

    @property
    def sunrise_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows sunrise time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=get_tomorrow(),
                                                 dates_list=self.sunrise_times)
        except DataRetrievalError:
            self._warn_once("sunrise_tomorrow", get_tomorrow(),
                            "%s not found in persistent data sunrise times")
            return None

    @property
    def dusk_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows dusk time from persistent data (last visible light)."""
        try:
            return PersistentData._date_in_dates(check_date=get_tomorrow(),
                                                 dates_list=self.dusk_times)
        except DataRetrievalError:
            self._warn_once("dusk_tomorrow", get_tomorrow(),
                            "%s not found in persistent data dusk times")
            return None


    @property
    def sunset_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows sunset time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=get_tomorrow(),
                                                 dates_list=self.sunset_times)
        except DataRetrievalError:
            self._warn_once("sunset_tomorrow", get_tomorrow(),
                            "%s not found in persistent data sunset times")
            return None

    @staticmethod
    def _date_in_dates(check_date: dt.date,
                       dates_list: List[dt.datetime]) -> dt.datetime:
        """Search for a datetime with a matching date in dates_list."""
        for d in dates_list:
            if d.date() == check_date:
                return d
        raise DataRetrievalError(
            f"Date {datetime_to_iso(check_date)} not found in list")

    def _add_date(self, dt_obj: dt.datetime, event: SolarEvent) -> None:
        """Add a sunrise/sunset datetime, replace existing entries for date."""
        # Strip microseconds (don't need that accuracy)
        dt_obj = dt_obj.replace(microsecond=0)
        # Remove outdated entries
        self._clear_past_times()
        # Get date portion for comparison
        dt_date = dt_obj.date()
        # Select the correct list
        match event:
            case SolarEvent.DAWN:
                target_list = self._dawn_times
            case SolarEvent.SUNRISE:
                target_list = self._sunrise_times
            case SolarEvent.DUSK:
                target_list = self._dusk_times
            case SolarEvent.SUNSET:
                target_list = self._sunset_times
            case _:
                logging.warning("No such solar time list %s: %s",
                                event, event.value)
                return
        # Remove any entries for the same date
        target_list[:] = [d for d in target_list if d.date() != dt_date]
        # Add the new datetime
        target_list.append(dt_obj)

    def add_sunrise_time(self, datetime_instance: dt.datetime) -> None:
        """Add a sunrise time to persistent data."""
        self._add_date(dt_obj=datetime_instance, event=SolarEvent.SUNRISE)

    def add_sunset_time(self, datetime_instance: dt.datetime) -> None:
        """Add a sunset time to persistent data."""
        self._add_date(dt_obj=datetime_instance, event=SolarEvent.SUNSET)

    def add_dawn_time(self, datetime_instance: dt.datetime) -> None:
        """Add a sunrise time to persistent data."""
        self._add_date(dt_obj=datetime_instance, event=SolarEvent.DAWN)

    def add_dusk_time(self, datetime_instance: dt.datetime) -> None:
        """Add a sunset time to persistent data."""
        self._add_date(dt_obj=datetime_instance, event=SolarEvent.DUSK)

    def _populate_times_from_local(self, iso_datetimes: List[str],
                                   event: SolarEvent) -> None:
        match event:
            case SolarEvent.DAWN:
                logstr = "dawn"
                times_list = self._dawn_times
            case SolarEvent.SUNRISE:
                logstr = "sunrise"
                times_list = self._sunrise_times
            case SolarEvent.DUSK:
                logstr = "dusk"
                times_list = self._dusk_times
            case SolarEvent.SUNSET:
                logstr = "sunset"
                times_list = self._sunset_times
            case _:
                logging.warning("Unhandled solar event type in load: %s",
                                event)
                return

        logging.debug("Retrieved %s times: %s",
                      logstr, iso_datetimes)
        for srt in iso_datetimes:
            self._add_date(dt_obj=iso_to_datetime(srt), event=event)

        logging.debug("Converted %s times to date.datetimes: \n  %s",
                      logstr, times_list)

    def _clear_past_times(self) -> None:
        """Remove any sunrise or solar events that are in the past."""
        today = get_today()
        # Filter out times from previous days
        self._dawn_times = [time for time in self._dawn_times
                               if time.date() >= today]
        self._sunrise_times = [time for time in self._sunrise_times
                               if time.date() >= today]
        self._dusk_times = [time for time in self._dusk_times
                               if time.date() >= today]
        self._sunset_times = [time for time in self._sunset_times
                              if time.date() >= today]
        logging.debug("Past solar event times cleared.")

    def _populate_locals_from_file(self):
        key = ""
        try:
            with open(ConfigLoader().persistent_data_json, 'r') as file:
                data = json.load(file)

                # Populate location and altitude values if not already set
                if self._current_latitude is None:
                    key = "latitude"
                    self._current_latitude = data.get(key)

                if self._current_longitude is None:
                    key = "longitude"
                    self._current_longitude = data.get(key)

                if self._current_altitude is None:
                    key = "altitude"
                    self._current_altitude = data.get(key)

                if self.local_timezone is None:
                    key = "local_timezone"
                    self.local_timezone = data.get(key)

                if self._missed_fixes is None:
                    key = "missed_fixes"
                    self._missed_fixes = data.get(key)

                if self._time_to_fix is None:
                    key = "time_to_fix"
                    self._time_to_fix = data.get(key)

                # Populate solar event times if they are empty
                for attr, key, event in [
                    (self._dawn_times, "dawn_times", SolarEvent.DAWN),
                    (self._sunrise_times, "sunrise_times", SolarEvent.SUNRISE),
                    (self._dusk_times, "dusk_times", SolarEvent.DUSK),
                    (self._sunset_times, "sunset_times", SolarEvent.SUNSET)]:

                    if not attr:
                        self._populate_times_from_local(
                            iso_datetimes=data.get(key, []), event=event)

                logging.debug("Memory AFTER JSON load\n"
                              "\tdawn_times: %s\n"
                              "\tsunrise_times: %s\n"
                              "\tdusk_times: %s\n"
                              "\tsunset_times: %s\n",
                              self._dawn_times, self._sunrise_times,
                              self._dusk_times, self._sunset_times)
        except IOError as e:
            logging.error(
                "Failed to read persistent data from file %s : %s",
                ConfigLoader().persistent_data_json, e
            )
        except json.JSONDecodeError as e:
            logging.warning(
                "Unable to decode key [%s] in %s : %s",
                key, ConfigLoader().persistent_data_json, e
            )

    def _fetch_data(self, key: str) -> Optional[Union[int, float]]:
        """Fetch a single data item from the JSON file.

        Args
        ----
            key (str): Key name to retrieve data for.

        Returns
        -------
            Optional[Union[int, float]]: Value of key, or None if not found.

        Raises
        ------
            DataRetrievalError: If reading the JSON file or retrieving data
                                fails.
        """
        try:
            with open(ConfigLoader().persistent_data_json, 'r') as file:
                data = json.load(file)
                return data.get(key)
        except (IOError, json.JSONDecodeError) as e:
            logging.error("Failed to fetch %s from JSON: %s", key, e)
            raise DataRetrievalError(
                f"Failed to retrieve {key} from JSON.") from e

    def _fetch_datetime_list(self, key: str) -> Optional[List[dt.datetime]]:
        """Fetch a list of datetime values from the JSON file.

        Args
        ----
            key (str): Key name containing a list of ISO-format datetime
                       strings.

        Returns
        -------
            Optional[List[dt.datetime]]: List of datetime objects, or None if
            parsing fails.

        Raises
        ------
            DataRetrievalError: If reading the JSON file or parsing datetime
            values fails.
        """
        try:
            with open(ConfigLoader().JSON_persistent_data, 'r') as file:
                data = json.load(file)
                if key in data:
                    return [iso_to_datetime(d) for d in data[key]]
            return None
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logging.error(
                "Failed to fetch or parse %s datetime list: %s", key, e)
            raise DataRetrievalError(
                f"Failed to retrieve or parse {key} data.") from e
