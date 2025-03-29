"""tests.helio_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing solar event calculations
Author: Will Bickerstaff
Version: 0.1
"""

import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
import sys
import os
import logging

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)
parent_path = os.path.abspath(os.path.join(base_path, '..'))
sys.path.append(base_path)
sys.path.append(parent_path)

import gps_test_vals as test_vals
from shelterGPS.Position import GPS
from shelterGPS.Helio import SunTimes

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed


class test_SolarEvent(unittest.TestCase):
    """Class testing for solar events."""

    def setUp(self):
        """Begin setup for each test."""
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_SunTimes_Initial_Location(self, mock_serial):
        """Test for initial location."""
        logging.getLogger().setLevel(logging.DEBUG)
        SunTimes()
        logging.getLogger().setLevel(self.default_loglevel)

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_solar_event_times(self, mock_serial):
        """Testing solar event times."""
        logging.getLogger().setLevel(logging.DEBUG)

        # Create a mock serial instance
        mock_instance = mock_serial.return_value

        # Create an instance of the GPS class and assign the
        # mocked serial instance
        gps = GPS()
        gps._gps_ser = mock_instance

        # Loop through each test value
        for tv in test_vals.valid_NMEA:
            if tv['datetime'] is None:
                continue
            logging.getLogger().setLevel(logging.WARN)
            mock_instance.readline.return_value = tv['msg'].encode()
            gps._get_coordinates(fix_wait=5)

            # Create the SunTimes instance
            test_instance = SunTimes()

            # Patch the internal _gps object and correctly mock dt.date.today()
            with patch.object(test_instance, '_gps', gps), \
                    patch('datetime.date', wraps=dt.date) as mock_date:

                # Set the return value of today() method
                mock_date.today.return_value = tv['datetime'].date()

                # Set logging to DEBUG for detailed output
                logging.getLogger().setLevel(logging.DEBUG)

                # Call the method to update solar times
                test_instance._set_solar_times_and_fix_window()
        # Reset logging level to INFO
        logging.getLogger().setLevel(logging.INFO)
