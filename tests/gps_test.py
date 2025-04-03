"""tests.gps_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: GPS Unit Testing
Author: Will Bickerstaff
Version: 0.1
"""

import unittest
from unittest.mock import patch, MagicMock
from . import gps_test_vals as test_vals
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
    
from shelterGPS.common import GPSInvalid, GPSOutOfBoundsError
from shelterGPS.Position import GPS
from shelterGPS.coord import Coordinate


class TestGPS(unittest.TestCase):
    """Class for GPS testing."""

    def setUp(self):
        """Begin Setup for each test, ensuring singleton reset for GPS."""
        GPS._instance = None  # Reset singleton instance
        self.default_loglevel = logging.DEBUG
        logfilename = 'gps_tests.log'
        with open(logfilename, 'w'):
            pass
        logging.basicConfig(level=self.default_loglevel,
                            filename=os.path.join('tests', logfilename))

    def test_singleton_behavior(self):
        """Test that only one instance of GPS can exist."""
        logging.info("\n%s\n\t\t   Checking GPS behaves as Singleton\n%s",
                     "="*79, "-"*79)
        gps1 = GPS()
        gps2 = GPS()
        self.assertIs(
            gps1, gps2, "GPS class is not respecting singleton pattern.")
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('shelterGPS.Position.GPS.pwr_on')
    @patch('shelterGPS.Position.GPS.pwr_off')
    def test_power_control(self, mock_pwr_off, mock_pwr_on):
        """Test that GPS correctly handles power on and off."""
        logging.info("\n%s\n\t\t   Commencing GPS Power tests\n%s",
                     "="*79, "-"*79)
        gps = GPS()
        gps.pwr_on()
        mock_pwr_on.assert_called_once()

        gps.pwr_off()
        mock_pwr_off.assert_called_once()
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('shelterGPS.Position.serial.Serial')
    def test_coordinate_extraction(self, mock_serial):
        """Testing coordinate extraction from NMEA messages."""
        logging.getLogger().setLevel(self.default_loglevel)

        # Create a mock serial instance
        mock_instance = mock_serial.return_value

        # Initialize the GPS class and assign the mock serial instance
        gps = GPS()
        gps._gps_ser = mock_instance  # Assign the mocked serial instance

        # Iterate over each test case in test_data
        for tv in test_vals.valid_NMEA:
            # Set the mock serial instance to return the NMEA sentence
            mock_instance.readline.return_value = tv['msg'].encode()

            # Call the _get_coordinates method, which should read from the
            # mocked serial
            gps._get_coordinates(fix_wait=5)

            # Check the extracted latitude, longitude, and altitude
            self.assertAlmostEqual(gps.latitude, tv['lat'], places=4)
            self.assertAlmostEqual(gps.longitude, tv['lon'], places=4)
            self.assertAlmostEqual(gps.altitude, tv['alt'], places=1)

        # Reset the logging level
        logging.getLogger().setLevel(self.default_loglevel)

    def test_Coordinate_valid(self):
        """Testing correct extraction of valid coordinates."""
        logging.getLogger().setLevel(self.default_loglevel)
        logging.info("\n%s\n\t\t   Commencing coordinate conversion tests\n%s",
                     "="*79, "-"*79)
        pass_n = 0
        """Test conversion of GPS DMS coordinates to decimal format."""
        for test_case in test_vals.valid_coordinates:
            expected = test_case.get("expected")
            coord = test_case.get("coord")
            dir = test_case.get("dir")
            coord = Coordinate(direction=dir, gps_string=coord)
            result = coord.decimal_value
            self.assertAlmostEqual(result, expected, places=10)
            pass_n += 1
        logging.info("\t*** %s of %s valid coordinate tests passed",
                     pass_n, len(test_vals.valid_coordinates))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_Coordinate_out_of_bounds(self):
        """Test GPS coord conversion raises an error when out of bounds."""
        logging.info(
            "\n%s\n\t\t   Commencing out of bounds coordinate tests\n%s",
            "="*79, "-"*79)
        logging.getLogger().setLevel(logging.DEBUG)
        for test_val in test_vals.invalid_coordinates:
            coord = test_val.get("coord")
            dir = test_val.get("dir")
            with self.assertRaises(GPSOutOfBoundsError):
                coord = Coordinate(gps_string=coord, direction=dir)
        logging.getLogger().setLevel(self.default_loglevel)

    def test_nmea_checksum_valid(self):
        """Test that NMEA checksum validation passes for valid data."""
        logging.info("\n%s\n\t\t   Commencing VALID NMEA checksum tests\n%s",
                     "="*79, "-"*79)
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0
        for message in test_vals.valid_NMEA:
            msg = message['msg']
            if GPS.nmea_checksum(msg):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False, f"Valid NMEA failed for message: {msg}")
        logging.info("\t*** %s of %s valid checksum tests passed",
                     pass_n, len(test_vals.valid_NMEA))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_nmea_checksum_invalid(self):
        """Test that NMEA checksum validation fails for invalid data."""
        logging.info("\n%s\n\t\t   Commencing INVALID NMEA checksum tests\n%s",
                     "="*79, "-"*79)
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0  # Initialize pass_n to 0 for invalid tests
        for message in test_vals.valid_NMEA:
            # Modify the message to have an invalid checksum
            invalid_checksum = message['msg'][:-2] + "00"
            # Check if the invalid checksum fails
            if not GPS.nmea_checksum(invalid_checksum):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False,
                                f"Invalid NMEA checksum unexpectedly"
                                f"passed for message: {invalid_checksum}")
        logging.info("\t*** %s of %s invalid checksum tests passed",
                     pass_n, len(test_vals.valid_NMEA))
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('shelterGPS.Position.GPS._get_msg')
    @patch('shelterGPS.Position.GPS._get_coordinates')
    @patch('shelterGPS.Position.GPS._get_datetime')
    def test_get_fix_success(self, mock_get_datetime,
                             mock_get_coordinates, mock_get_msg):
        """Test that `get_fix` calls required methods for a successful fix."""
        logging.getLogger().setLevel(logging.DEBUG)

        gps = GPS()
        gps.get_fix()
        mock_get_coordinates.assert_called_once()
        mock_get_datetime.assert_called_once()
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('shelterGPS.Position.GPS._get_msg', side_effect=GPSInvalid)
    def test_get_fix_failure(self, mock_get_msg):
        """Test `get_fix` raises GPSInvalid if no valid fix is obtained."""
        gps = GPS()
        with self.assertRaises(GPSInvalid):
            gps.get_fix()
        logging.getLogger().setLevel(self.default_loglevel)

    def test_process_datetime_valid(self):
        """GPS correctly processes and converts valid UTC time and date."""
        logging.info("\n%s\n\t\t   Commencing VALID datetime tests\n%s",
                     "="*79, "-"*79)
        gps = GPS()
        pass_n = 0
        logging.getLogger().setLevel(self.default_loglevel)
        for val in test_vals.valid_dt:
            expected = val.get("dt_obj")
            dt_obj = gps._process_datetime(
                utc_time=val.get("time"), date_str=val.get("date"))
            if not self.assertEqual(dt_obj, expected):
                pass_n += 1
        logging.info("\t*** %s of %s valid date tests passed",
                     pass_n, len(test_vals.valid_dt))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_process_datetime_invalid(self):
        """GPS raises ValueError for improperly formatted datetime strings."""
        logging.info("\n%s\n\t\t   Commencing INVALID datetime tests\n%s",
                     "="*79, "-"*79)
        gps = GPS()
        pass_n = 0
        logging.getLogger().setLevel(self.default_loglevel)

        for val in test_vals.invalid_dt:
            try:
                with self.assertRaises(
                        ValueError,
                        msg=f"Failed for date: {val.get('date')} and "
                        f"time: {val.get('time')}"):
                    gps._process_datetime(date_str=val.get(
                        "date"), utc_time=val.get("time"))
            except AssertionError:
                continue  # If the ValueError isn't raised, the test will fail
            else:
                pass_n += 1  # Increment if the exception was correctly raised

        logging.info("\t*** %s of %s invalid date tests passed",
                     pass_n, len(test_vals.invalid_dt))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_decode_message_valid(self):
        """Decoding of a valid GPS message, & storage in `self._last_msg`."""
        gps = GPS()
        logging.getLogger().setLevel(logging.DEBUG)

        for test_message in test_vals.valid_NMEA:
            gps._decode_message(test_message['msg'])
            self.assertIsNotNone(
                gps._last_msg, "Decoded message should not be None")
            self.assertTrue(len(gps._last_msg) > 0,
                            "Decoded message should not be empty")
            logging.debug("%s", gps.message_type)
            self.assertTrue(gps._validate_message_content(gps.message_type))
        logging.getLogger().setLevel(self.default_loglevel)
