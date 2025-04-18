"""tests.helio_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing solar event calculations
Author: Will Bickerstaff
Version: 0.1
"""

import unittest
from unittest.mock import patch
import gps_test_vals as test_vals
import datetime as dt
import sys
import os
import logging
import util

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)

from shelterGPS.Position import GPS
from shelterGPS.Helio import SunTimes
from shelterGPS.common import NoSolarEventError

# Set up logging ONCE for the entire test module
util.setup_test_logging()


class test_SolarEvent(unittest.TestCase):
    """Class testing for solar events."""

    def setUp(self):
        """Begin setup for each test."""

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_SunTimes_Initial_Location(self, mock_serial):
        """Test for initial location."""
        SunTimes()

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_solar_event_times(self, mock_serial):
        """Testing solar event times."""
        loglevel = logging.getLogger().getEffectiveLevel()

        mock_instance = mock_serial.return_value
        gps = GPS()
        gps._gps_ser = mock_instance

        for tv in test_vals.valid_NMEA:
            if tv['datetime'] is None:
                continue
            # We don't need all the GPS debug messages in this test.
            # This should be tested using gps_test.py, drop the
            # loglevel
            logging.getLogger().setLevel(logging.WARN)
            mock_instance.readline.return_value = tv['msg'].encode()
            gps._get_coordinates(fix_wait=5)

            test_instance = SunTimes()

            with patch.object(test_instance, '_gps', gps), \
                    patch('datetime.date', wraps=dt.date) as mock_date:

                mock_date.today.return_value = tv['datetime'].date()
                # Restore the loglevel
                logging.getLogger().setLevel(loglevel)

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

    @patch('serial.Serial')
    def test_solar_event_no_sunset(self, mock_serial):
        """Test for extreme lattitudes (polar day, no sunset)."""
        from astral import Observer
        from shelterGPS.common import NoSolarEventError

        test_instance = SunTimes()
        observer = Observer(latitude=89.0, longitude=0.0)  # Near North Pole

        with self.assertRaises(NoSolarEventError):
            test_instance.calculate_solar_times(observer, dt.date(2025, 6, 21))

    @patch('serial.Serial')
    def test_solar_event_no_sunrise(self, mock_serial):
        """Test for extreme latitudes (polar night, no sunrise or sunset)."""
        from astral import Observer

        test_instance = SunTimes()
        observer = Observer(latitude=89.0, longitude=0.0)  # Near North Pole

        date = dt.date(2025, 12, 21)

        result = test_instance.calculate_solar_times(observer, date)

        self.assertIsNone(result["sunrise"])
        self.assertIsNone(result["sunset"])


if __name__ == '__main__':
    """Verbosity:

        0	One . per test	CI logs, super compact view
        1	Test name + result	(Default)
        2	Test + docstring + result	Debugging, test review, clarity
    """
    unittest.main(testRunner=util.LoggingTestRunner(verbosity=2))
