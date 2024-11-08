import pandas as pd
import sqlite3
import logging
import sys, os
import pytz
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

from lightlib.config import ConfigLoader

GEODB = "geocode.db"
GEOTABLE = "geocode_data"

class Location():
    def __init__(self):
        self._place_name: str = None
        self._country:str = None
        self._latitude: float = None
        self._longitude: float = None
        self._tz: pytz.timezone = None
        self._db = os.path.join("geocode",GEODB)
        self._get_from_config()

    @property
    def latitude(self) -> float:
        """Return the latitude of the location stored in the config file. Will
        return None if the latitude is not set"""
        return self._latitude

    @property
    def longitude(self) -> float:
        """Return the longitude of the location stored in the config file. Will
        return None if the longitude is not set"""
        return self._longitude

    @property
    def ISO_Country(self) -> str:
        """Return the 2 letter ISO country code of the location stored in the
        config file. Will return None if it's not set in the config"""
        return self._country

    @property
    def Place(self) -> str:
        """Return the place name of the location stored in the
        config file. Will return None if it's not set in the config"""
        return self._place_name

    @property
    def timezone(self) -> pytz.timezone:
        """Return a `dt.timezone` for the location stored in the
        config file. Will return None if it's not set in the config"""
        return self._tz

    def _get_from_config(self):
        iso = ConfigLoader().ISO_country2
        place = ConfigLoader().place_name
        logging.debug("GCODE: Retrieved Location %s, %s", iso, place)
        # Query the geocode db
        df = self._query_location_data(iso_country = iso, place_name = place)

        # iloc gets the first record returned.
        # None if the query returned no results or the column is missing

        # Latitude from the results,
        self._latitude = df.get("Lat").iloc[0] \
            if not df.empty and "Lat" in df else None
        # Longitude from the results,
        self._longitude = df.get("Lng").iloc[0] \
            if not df.empty and "Lng" in df else None
        # Timezone from the results, transformed into a timezone instance for
        # use in datetime objects,
        tz = df.get("Timezone").iloc[0] \
            if not df.empty and "Timezone" in df else None
        self._tz = pytz.timezone(tz)
        logging.debug(
            "LOC: Retrieved lat %s, lng %s for %s in country %s. TZ=:%s",
            self.latitude, self.longitude, place, iso, self.timezone)

    def _query_location_data(self, iso_country: str, place_name: str) -> pd.DataFrame:
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
        logging.debug("LOC: %s",df)
        # Close the database connection
        conn.close()

        return df