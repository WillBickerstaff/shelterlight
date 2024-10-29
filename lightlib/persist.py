import json
import datetime as dt
from typing import Union, Optional, List
import logging
from lib.config import ConfigLoader


class DataStoreError(Exception):
    """Base class for exceptions in the GPSDataStore."""
    pass


class DataStorageError(DataStoreError):
    """Raised when storing data in the JSON file fails."""
    pass


class DataRetrievalError(DataStoreError):
    """Raised when retrieving data from the JSON file fails."""
    pass


class GPSDataStore:
    """Class for storing GPS and time data in JSON format to persist across 
       power cycles.

    Manages the storage and retrieval of GPS data, including latitude, 
    longitude, maximum time to obtain a fix, and sunrise and sunset times for 
    today and the next seven days.
    """

    def __init__(self, file_path: str = "gps_data.json"):
        """Initialize the GPSDataStore with a JSON file.

        Args:
            file_path (str): Path to the JSON file for data storage.

        Raises:
            DataStorageError: If the JSON file cannot be initialized.
        """
        self._initialize_file()

    def _initialize_file(self) -> None:
        """Initialize the JSON file if it doesn't exist, creating an empty 
           data structure."""
        try:
            # Create a basic structure if the JSON file does not exist
            with open(ConfigLoader().JSON_persistent_data, 'a+') as file:
                file.seek(0)
                if file.read().strip() == "":
                    empty_data = {
                        "max_fix_time": None,
                        "latitude": None,
                        "longitude": None,
                        "sunrise_times": [],
                        "sunset_times": [],
                        "last_updated": None
                    }
                    json.dump(empty_data, file)
                    logging.info("GPSDataStore JSON file initialized at %s", 
                                 ConfigLoader().JSON_persistent_data)
        except IOError as e:
            logging.error("Failed to initialize GPSDataStore JSON file: %s", e)
            raise DataStorageError("Failed to initialize JSON file.") from e

    def store_data(self, max_fix_time: int, latitude: float, longitude: float,
                   sunrise_times: List[dt.datetime], 
                   sunset_times: List[dt.datetime]) -> None:
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
                "max_fix_time": max_fix_time,
                "latitude": latitude,
                "longitude": longitude,
                "sunrise_times": [t.isoformat() for t in sunrise_times],
                "sunset_times": [t.isoformat() for t in sunset_times],
                "last_updated": dt.datetime.now().isoformat()
            }
            with open(ConfigLoader().JSON_persistent_data, 'w') as file:
                json.dump(data, file)
            logging.info("GPS data stored successfully in JSON file.")
        except IOError as e:
            logging.error("Failed to store GPS data in JSON: %s", e)
            raise DataStorageError("Failed to store data in JSON.") from e

    @property
    def max_fix_time(self) -> Optional[int]:
        """Retrieve the maximum time to obtain a GPS fix."""
        return self._fetch_data("max_fix_time")

    @property
    def latitude(self) -> Optional[float]:
        """Retrieve the stored latitude."""
        return self._fetch_data("latitude")

    @property
    def longitude(self) -> Optional[float]:
        """Retrieve the stored longitude."""
        return self._fetch_data("longitude")

    @property
    def sunrise_times(self) -> Optional[List[dt.datetime]]:
        """Retrieve the list of stored sunrise times."""
        return self._fetch_datetime_list("sunrise_times")

    @property
    def sunset_times(self) -> Optional[List[dt.datetime]]:
        """Retrieve the list of stored sunset times."""
        return self._fetch_datetime_list("sunset_times")

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
            with open(ConfigLoader().JSON_persistent_data, 'r') as file:
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
