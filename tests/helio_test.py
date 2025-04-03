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

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed

from . import gps_test_vals as test_vals
from shelterGPS.Position import GPS
from shelterGPS.Helio import SunTimes
from shelterGPS.common import NoSolarEventError

class test_SolarEvent(unittest.TestCase):
    """Class testing for solar events."""

    def setUp(self):
        """Begin setup for each test."""
        self.default_loglevel = logging.DEBUG
        logfilename = 'helio_tests.log'
        with open(logfilename, 'w'):
            pass
        logging.basicConfig(level=self.default_loglevel,
                            filename=os.path.join('tests', logfilename))

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_SunTimes_Initial_Location(self, mock_serial):
        """Test for initial location."""
        logging.info("\n%s\n\t\t   Determine Location\n%s",
                     "="*79, "-"*79)
        logging.getLogger().setLevel(logging.DEBUG)
        SunTimes()
        logging.getLogger().setLevel(self.default_loglevel)

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_solar_event_times(self, mock_serial):
        """Testing solar event times."""
        logging.info("\n%s\n\t\t   Calculate Sunrise and Sunset\n%s",
                     "="*79, "-"*79)
        logging.getLogger().setLevel(logging.DEBUG)

        mock_instance = mock_serial.return_value
        gps = GPS()
        gps._gps_ser = mock_instance

        for tv in test_vals.valid_NMEA:
            if tv['datetime'] is None:
                continue
            logging.getLogger().setLevel(logging.WARN)
            mock_instance.readline.return_value = tv['msg'].encode()
            gps._get_coordinates(fix_wait=5)

            test_instance = SunTimes()

            with patch.object(test_instance, '_gps', gps), \
                    patch('datetime.date', wraps=dt.date) as mock_date:

                mock_date.today.return_value = tv['datetime'].date()
                logging.getLogger().setLevel(logging.DEBUG)

                try:
                    test_instance._set_solar_times_and_fix_window()
                except Exception as e:
                    if isinstance(e, NoSolarEventError):
                        # Expected if tomorrow's solar event is polar
                        logging.warning(
                            "Skipping test value due to polar condition: %s",
                            e)
                        continue
                    else:
                        raise e  # Unexpected

        logging.getLogger().setLevel(logging.INFO)

    @patch('serial.Serial')
    def test_solar_event_no_sunset(self, mock_serial):
        """Test for extreme lattitudes (polar day, no sunset)."""
        logging.info("\n%s\n\t\t   Testing polar day behaviour\n%s",
                     "="*79, "-"*79)
        from astral import Observer
        from shelterGPS.common import NoSolarEventError

        test_instance = SunTimes()
        observer = Observer(latitude=89.0, longitude=0.0)  # Near North Pole

        with self.assertRaises(NoSolarEventError):
            test_instance.calculate_solar_times(observer, dt.date(2025, 6, 21))

    @patch('serial.Serial')
    def test_solar_event_no_sunrise(self, mock_serial):
        """Test for extreme latitudes (polar night, no sunrise/sunset)."""
        logging.info("\n%s\n\t\t   Testing polar night behaviour\n%s",
                     "="*79, "-"*79)
        from astral import Observer

        test_instance = SunTimes()
        observer = Observer(latitude=89.0, longitude=0.0)  # Near North Pole

        date = dt.date(2025, 12, 21)

        result = test_instance.calculate_solar_times(observer, date)

        self.assertIsNone(result["sunrise"])
        self.assertIsNone(result["sunset"])
