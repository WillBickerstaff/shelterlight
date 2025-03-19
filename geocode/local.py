"""geocode.locals.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Allows for determining a location for a place given in the config.
Author: Will Bickerstaff
Version: 0.1
"""

from lightlib.config import ConfigLoader

import pandas as pd
import sqlite3
import logging
import sys
import os
import pytz
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

GEODB = "geocode.db"
GEOTABLE = "geocode_data"


class InvalidLocationError(Exception):
    """Raised when a given location is invalid."""

    pass


class Location():
    """Class to hold location information."""

    def __init__(self):
        self._place_name: str = None
        self._country: str = None
        self._latitude: float = None
        self._longitude: float = None
        self._tz: pytz.timezone = None
        self._db = os.path.join("geocode", GEODB)
        self._get_from_config()

    @property
    def latitude(self) -> float:
        """Return latitude of the location stored in the config file.

        Will return None if the latitude is not set
        """
        return self._latitude

    @property
    def longitude(self) -> float:
        """Return the longitude of the location stored in the config file.

        Will return None if the longitude is not set
        """
        return self._longitude

    @property
    def ISO_Country(self) -> str:
        """The 2 letter ISO country code of the location stored in the config.

        Will return None if it's not set in the config
        """
        return self._country

    @property
    def place(self) -> str:
        """The place name of the location stored in the config file.

        Will return None if it's not set in the config
        """
        return self._place_name

    @property
    def timezone(self) -> pytz.timezone:
        """Return a `dt.timezone` for the location stored in the config file.

        Will return None if it's not set in the config
        """
        return self._tz

    def _get_from_config(self):
        iso = ConfigLoader().ISO_country2
        place = ConfigLoader().place_name
        logging.debug("GCODE: Retrieved Location %s, %s", iso, place)
        # Query the geocode db
        try:
            df = self._query_location_data(iso_country=iso,
                                           place_name=place)

            if df.empty or not ("Lat" in df and "Lng" in df):
                raise InvalidLocationError(
                    f"Location {
                        place}({iso}) is either not in the database or "
                    "the database does not provide lat or lng for "
                    "the location")
            # iloc gets the first record returned.
            # Latitude from the results,
            self._latitude = df.get("Lat").iloc[0]
            # Longitude from the results,
            self._longitude = df.get("Lng").iloc[0]
            # Timezone from the results, transformed into a timezone instance
            # for use in datetime objects,
            tz = df.get("Timezone").iloc[0] \
                if not df.empty and "Timezone" in df else None
            self._tz = pytz.timezone(tz)
            logging.debug(
                "LOC: Retrieved lat %s, lng %s for %s in country %s. TZ=:%s",
                self.latitude, self.longitude, place, iso, self.timezone)
        except InvalidLocationError as e:
            raise e

    def _query_location_data(self, iso_country: str,
                             place_name: str) -> pd.DataFrame:
        # Connect to the SQLite database
        conn = sqlite3.connect(self._db)

        # Define the SQL query
        query = f"""
        SELECT * FROM {GEOTABLE}
        WHERE ISO_Country = ? AND Place_Name = ?
        LIMIT 1
        """

        # Execute the query and load the result into a DataFrame
        df = pd.read_sql_query(query, conn, params=(iso_country, place_name))
        logging.debug("LOC: %s", df)
        # Close the database connection
        conn.close()

        return df
