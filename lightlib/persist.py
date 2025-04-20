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
from typing import Union, Optional, List
from threading import Lock
import logging
from lightlib.config import ConfigLoader
from lightlib.common import iso_to_datetime, datetime_to_iso, DATE_TODAY, \
    DATE_TOMORROW


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
        self._current_latitude = None
        self._current_longitude = None
        self._current_altitude = None
        self._initialize_file()
        # Mark as initialized
        self._populate_locals_from_file()
        self.__initialized = True

    def _initialize_file(self) -> None:
        """Init JSON file if doesn't exist, create an empty data structure."""
        try:
            # Create a basic structure if the JSON file does not exist
            logging.debug(
                "JSON: Attempting to initialize data storage file %s",
                ConfigLoader().persistent_data_json)
            with open(ConfigLoader().persistent_data_json, 'a+') as file:
                file.seek(0)
                if file.read().strip() == "":
                    empty_data = {
                        "last_latitude": None,
                        "last_longitude": None,
                        "altitude": None,
                        "sunrise_times": [],
                        "sunset_times": [],
                        "last_updated": None
                    }
                    json.dump(empty_data, file)
                    logging.info("GPSDataStore JSON file initialized at %s",
                                 ConfigLoader().persistent_data_json)
        except IOError as e:
            logging.error("Failed to initialize GPSDataStore JSON file: %s", e)
            raise DataStorageError("Failed to initialize JSON file.") from e

    def store_data(self) -> None:
        """Store the latest GPS data in the JSON file, overwrite existing.

        Raises
        ------
            DataStorageError: If storing data in the JSON file fails.
        """
        try:
            data = {
                "latitude": self.current_latitude,
                "longitude": self.current_longitude,
                "altitude": self.current_altitude,
                "sunrise_times": [datetime_to_iso(t) for
                                  t in self._sunrise_times],
                "sunset_times": [datetime_to_iso(t) for
                                 t in self._sunset_times],
                "last_updated": datetime_to_iso(dt.datetime.now())
            }
            with open(ConfigLoader().persistent_data_json, 'w') as file:
                json.dump(data, file)
            logging.info("GPS data stored successfully in JSON file.")
        except IOError as e:
            logging.error("Failed to store GPS data in JSON: %s", e)
            raise DataStorageError("Failed to store data in JSON.") from e

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
        if getattr(self, flag_attr) != DATE_TODAY:
            logging.error(message, datetime_to_iso(missing_date))
            setattr(self, flag_attr, DATE_TODAY)

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

    @property
    def current_longitude(self) -> float:
        """GPS Longitude from persistent data."""
        return self._current_longitude

    @current_longitude.setter
    def current_longitude(self, lng: float) -> None:
        self._current_longitude = lng

    @property
    def sunrise_times(self) -> List[dt.datetime]:
        """Datetime object List of sunrise times from persistent data."""
        return self._sunrise_times

    @property
    def sunset_times(self) -> List[dt.datetime]:
        """Datetime object list of sunset times from persistent data."""
        return self._sunrise_times

    @property
    def sunrise_today(self) -> Optional[dt.datetime]:
        """Today's sunrise time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=DATE_TODAY,
                                                 dates_list=self.sunrise_times)
        except DataRetrievalError:
            self._warn_once("_sr_today", DATE_TODAY,
                            "%s not found in persistent data sunrise times")
            return None

    @property
    def sunset_today(self) -> Optional[dt.datetime]:
        """Today's sunset time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=DATE_TODAY,
                                                 dates_list=self.sunset_times)
        except DataRetrievalError:
            self._warn_once("_ss_today", DATE_TODAY,
                            "%s not found in persistent data sunset times")
            return None

    @property
    def sunrise_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows sunrise time from persistent."""
        try:
            return PersistentData._date_in_dates(check_date=DATE_TOMORROW,
                                                 dates_list=self.sunrise_times)
        except DataRetrievalError:
            self._warn_once("_sr_tmrw", DATE_TOMORROW,
                            "%s not found in persistent data sunrise times")
            return None

    @property
    def sunset_tomorrow(self) -> Optional[dt.datetime]:
        """Tomorrows sunset time from persistent data."""
        try:
            return PersistentData._date_in_dates(check_date=DATE_TOMORROW,
                                                 dates_list=self.sunset_times)
        except DataRetrievalError:
            self._warn_once("_ss_tmrw", DATE_TOMORROW,
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

    def _add_date(self, dt_obj: dt.datetime, is_sunrise: bool = False) -> None:
        # Remove any outdated datetimes before adding new ones
        self._clear_past_times()
        if is_sunrise:
            self._sunrise_times.append(dt_obj)
        else:
            self._sunset_times.append(dt_obj)

    def add_sunrise_time(self, datetime_instance: dt.datetime) -> None:
        """Add a sunrise time to persistent data."""
        self._add_date(dt_obj=datetime_instance, is_sunrise=True)

    def add_sunset_time(self, datetime_instance: dt.date) -> None:
        """Add a sunset time to persistent data."""
        self._add_date(dt_obj=datetime_instance, is_sunrise=False)

    def _populate_times_from_local(self, iso_datetimes: List[str],
                                   is_sunrise: bool = True) -> None:
        sr_ss_str = "sunrise" if is_sunrise else "sunset"
        logging.debug("JSON: Retrieved %s times: %s",
                      sr_ss_str, iso_datetimes)
        for srt in iso_datetimes:
            self._add_date(dt_obj=iso_to_datetime(srt),
                           is_sunrise=is_sunrise)
        logging.debug("JSON: Converted %s times to date.datetimes: \n  %s",
                      sr_ss_str, self._sunrise_times)

    def _clear_past_times(self) -> None:
        """Remove any sunrise or sunset times that are in the past."""
        today = DATE_TODAY
        # Filter out times from previous days
        self._sunrise_times = [time for time in self._sunrise_times
                               if time.date() >= today]
        self._sunset_times = [time for time in self._sunset_times
                              if time.date() >= today]
        logging.debug("Past sunrise and sunset times cleared.")

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

                # Populate sunrise and sunset times if they are empty
                if not self._sunrise_times:
                    key = "sunrise_times"
                    self._populate_times_from_local(
                        iso_datetimes=data.get(key, []),
                        is_sunrise=True
                    )

                if not self._sunset_times:
                    key = "sunset_times"
                    self._populate_times_from_local(
                        iso_datetimes=data.get(key, []),
                        is_sunrise=False
                    )

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
