"""
tests.test_geocode

Integration tests for geocode.local.Location using real geocode.db.
"""

import unittest
import logging
import os
import sys
from unittest.mock import patch
import pytz
import util

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)

from geocode.local import Location, InvalidLocationError
from lightlib.config import ConfigLoader


class TestGeocode(unittest.TestCase):
    """Integration tests for the Location class."""

    def setUp(self):
        """Set up the test environment forcls each test case."""
        util.setup_test_logging()
        self.location = Location()

    def test_location_properties_populated(self):
        """Test Location properties are populated correctly."""
        logging.debug("Testing location properties population.")

        logging.debug(f"Location place: {self.location.place}")
        logging.debug(f"Location country: {self.location.ISO_Country}")
        logging.debug(f"Location latitude: {self.location.latitude}")
        logging.debug(f"Location longitude: {self.location.longitude}")
        logging.debug(f"Location timezone: {self.location.timezone}")

        # Fail early with a clear message if config is misconfigured
        self.assertIsNotNone(self.location.place,
                             "Config place_name is not in geocode.db")
        self.assertIsNotNone(self.location.ISO_Country,
                             "Config ISO_country2 is not in geocode.db")

        self.assertIsInstance(self.location.latitude, float)
        self.assertIsInstance(self.location.longitude, float)
        self.assertIsInstance(self.location.timezone, pytz.BaseTzInfo)

        logging.debug("Location properties populated correctly.")

    def test_lat_lon_within_bounds(self):
        """Test latitude and longitude values are within valid bounds."""
        logging.debug("Testing latitude and longitude bounds.")
        lat = self.location.latitude
        lon = self.location.longitude

        logging.debug(f"Latitude: {lat}, Longitude: {lon}")

        self.assertTrue(-90.0 <= lat <= 90.0, "Latitude out of bounds")
        self.assertTrue(-180.0 <= lon <= 180.0, "Longitude out of bounds")

        logging.debug("Latitude and longitude are within valid bounds.")

    @patch.object(ConfigLoader, 'ISO_country2', new_callable=lambda: "ZZ")
    @patch.object(ConfigLoader, 'place_name',
                  new_callable=lambda: "NowhereLand")
    def test_invalid_location_raises_error(self, mock_place, mock_iso):
        """Test InvalidLocationError is raised for unknown location."""
        logging.debug("Testing InvalidLocationError for "
                      "invalid location config.")
        with self.assertRaises(InvalidLocationError):
            Location()
        logging.debug("InvalidLocationError correctly raised.")


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
