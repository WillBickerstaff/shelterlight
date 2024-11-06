import json
import datetime as dt
from typing import Union, Optional, List
import logging
from lightlib.config import ConfigLoader


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
    """Class for storing GPS and time data in JSON format to persist across
       power cycles.

    Manages the storage and retrieval of GPS data, including latitude,
    longitude, maximum time to obtain a fix, and sunrise and sunset times for
    today and the next seven days.
    """
    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of PersistentData is created.

        This method implements the Singleton pattern for the `PersistentData`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns:
            GPS: A single instance of the `PersistentData` class.
        """
        if not cls._instance:
            with cls._lock:  # Thread-safe check and assignment
                if not cls._instance:
                    cls._instance = super(PersistenetData, cls).__new__(cls)
                    cls._instance.__initialized = False
        return cls._instance

    def __init__(self, file_path: str = "persist.json"):
        """Initialize PersistentData with a JSON file.

        Args:
            file_path (str): Path to the JSON file for data storage.

        Raises:
            DataStorageError: If the JSON file cannot be initialized.
        """
        if self.__initialized:
            return  # Skip reinitialization for singleton pattern
        self._sunrise_times = []
        self._sunset_times = []
        self._initialize_file()
        self._last_lat = 0.0
        self._last_lng = 0.0
        # Mark as initialized
        self.__initialized = True

    def _initialize_file(self) -> None:
        """Initialize the JSON file if it doesn't exist, creating an empty
           data structure."""
        try:
            # Create a basic structure if the JSON file does not exist
            logging.debug("JSON: Attempting to initialize data storage file %s",
                          ConfigLoader().persistent_data_json)
            with open(ConfigLoader().persistent_data_json, 'a+') as file:
                file.seek(0)
                if file.read().strip() == "":
                    empty_data = {
                        "last_latitude": None,
                        "last_longitude": None,
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
        """Store the latest GPS data in the JSON file, overwriting existing
           data.

        Args:
            max_fix_time (int): Maximum time in seconds to obtain a GPS fix.
            latitude (float): Current latitude.
            longitude (float): Current longitude.
            sunrise_times (List[dt.datetime]): List of sunrise times for the
                next 7 days.
            sunset_times (List[dt.datetime]): List of sunset times for the
                next 7 days.

        Raises:
            DataStorageError: If storing data in the JSON file fails.
        """
        try:
            # Convert datetime objects to ISO strings for JSON compatibility
            data = {
                "latitude": self.last_latitude,
                "longitude": self.last_longitude,
                "sunrise_times": [t.isoformat() for t in self._sunrise_times],
                "sunset_times": [t.isoformat() for t in self._sunset_times],
                "last_updated": dt.datetime.now().isoformat()
            }
            with open(ConfigLoader().persistent_data_json, 'w') as file:
                json.dump(data, file)
            logging.info("GPS data stored successfully in JSON file.")
        except IOError as e:
            logging.error("Failed to store GPS data in JSON: %s", e)
            raise DataStorageError("Failed to store data in JSON.") from e

    @property
    def last_latitude(self) -> float:
        return self._last_lat

    @last_latitude.setter
    def last_latitude(self, lat: float) -> None:
        self._last_lat = lat

    @property
    def last_longitude(self) -> float:
        return self._last_lng

    @last_longitude.setter
    def last_longitude(self, lng: float) -> None:
        self._last_lng = lng

    def _add_date(self, dt_obj: str,
                 is_sunrise: Optional[bool]=False) -> None:
        if is_sunrise:
            self._sunrise_times.append(dt_obj)
        else:
            self._sunset_times.append(dt_obj)

    def add_sunrise_time(self, datetime_instance: dt.datetime) -> None:
        self._add_date(dt_obj = datetime_instance, is_sunrise = True)

    def add_sunset_time(self, datetime_instance: dt.date) -> None:
        self._add_date(dt_obj = datetime_instance,is_sunrise = False)

    def _populate_locals_from_file(self):
        key = ""
        try:
            with open(ConfigLoader().persistent_data_json, 'r') as file:
                data = json.load(file)
                self._last_lat = float(data.get("last_lattitude"))
                self._last_lng = float(data.get("last_longitude"))
                sunrise_times = data.get("sunrise_times")
                sunset_times = data.get("sunset_times")
        except (IOError) as e:
            logging.error(
                "JSON: Failed to read persistent data from file %s : %s ",
                          ConfigLoader().persistent_data_json), e
        except  (json.JSONDecodeError) as e:
            logging.WARNING(
                "JSON: Unable to read key [%s] or key does not exist in %s : e",
                key, e)

    def _fetch_data(self, key: str) -> Optional[Union[int, float]]:
        """Fetch a single data item from the JSON file.

        Args:
            key (str): Key name to retrieve data for.

        Returns:
            Optional[Union[int, float]]: Value of the key, or None if not found.

        Raises:
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

        Args:
            key (str): Key name containing a list of ISO-format datetime
                       strings.

        Returns:
            Optional[List[dt.datetime]]: List of datetime objects, or None if
            parsing fails.

        Raises:
            DataRetrievalError: If reading the JSON file or parsing datetime
            values fails.
        """
        try:
            with open(ConfigLoader().JSON_persistent_data, 'r') as file:
                data = json.load(file)
                if key in data:
                    return [dt.datetime.fromisoformat(d) for d in data[key]]
            return None
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logging.error(
                "Failed to fetch or parse %s datetime list: %s", key, e)
            raise DataRetrievalError(
                f"Failed to retrieve or parse {key} data.") from e