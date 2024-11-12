import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
import sys, os
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed

from shelterGPS.Helio import SolarEvent, SunTimes
from shelterGPS.Position import GPS
import gps_test_vals as test_vals

class test_SolarEvent(unittest.TestCase):
    def setUp(self):
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_SunTimes_Initial_Location(self, mock_serial):
        logging.getLogger().setLevel(logging.DEBUG)
        test_instance = SunTimes()
        logging.getLogger().setLevel(self.default_loglevel)

    # Doesn't test, just debug.logs all of the calculations for review
    @patch('serial.Serial')
    def test_solar_event_times(self, mock_serial):
        logging.getLogger().setLevel(logging.DEBUG)

        # Create a mock serial instance
        mock_instance = mock_serial.return_value

        # Create an instance of the GPS class and assign the mocked serial instance
        gps = GPS()
        gps._gps_ser = mock_instance

        # Loop through each test value
        for tv in test_vals.valid_NMEA:
            if tv['datetime'] is None: continue
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