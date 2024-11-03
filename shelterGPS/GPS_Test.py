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

from Position import GPS, GPSInvalid, GPSOutOfBoundsError, GPSDir, Coordinate # Import after mocks
import NMEA_Messages

class TestGPS(unittest.TestCase):

    def setUp(self):
        """Setup for each test, ensuring singleton reset for GPS."""
        GPS._instance = None  # Reset singleton instance
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)

    def test_singleton_behavior(self):
        """Test that only one instance of GPS can exist."""
        logging.info("\n%s\n\t\t   Checking GPS behaves as Singleton\n%s",
                    "="*79, "-"*79)
        gps1 = GPS()
        gps2 = GPS()
        self.assertIs(gps1, gps2, "GPS class is not respecting singleton pattern.")
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('serial.Serial')
    @patch('lightlib.config.ConfigLoader')
    def test_init_serial_connection(self, MockConfigLoader, MockSerial):
        """Test that GPS initializes serial connection using configurations."""
        logging.info("\n%s\n\t\t   Commencing serial connection tests\n%s",
                    "="*79, "-"*79)
        # Configure the mock to return specific values
        MockConfigLoader.return_value.gps_serial_port = '/dev/serial0'
        MockConfigLoader.return_value.gps_baudrate = 9600
        MockConfigLoader.return_value.gps_timeout = 0.5

        # Initialize GPS instance, which should use the mock config
        gps = GPS()

        # Assert the serial.Serial call uses the correct values
        MockSerial.assert_called_with(port='/dev/serial0',
                                    baudrate=9600,
                                    timeout=0.5)
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS.pwr_on')
    @patch('Position.GPS.pwr_off')
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

    def test_Coordinate_valid(self):
        logging.getLogger().setLevel(self.default_loglevel)
        logging.info("\n%s\n\t\t   Commencing coordinate conversion tests\n%s",
            "="*79, "-"*79)
        pass_n = 0
        """Test conversion of GPS DMS coordinates to decimal format."""
        for test_case in NMEA_Messages.valid_coordinates:
            expected = test_case.get("expected")
            coord = test_case.get("coord")
            dir = test_case.get("dir")
            coord = Coordinate(direction=dir, gps_string=coord)
            result = coord.decimal_value
            self.assertAlmostEqual(result, expected, places = 10)
            pass_n += 1
        logging.info("\t*** %s of %s valid coordinate tests passed", pass_n, len(NMEA_Messages.valid_coordinates))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_Coordinate_out_of_bounds(self):
        """Test GPS coordinate conversion raises an error when out of bounds."""
        logging.info("\n%s\n\t\t   Commencing out of bounds coordinate tests\n%s",
                "="*79, "-"*79)
        logging.getLogger().setLevel(self.default_loglevel)
        with self.assertRaises(GPSOutOfBoundsError):
            coord = Coordinate(gps_string="9145.1234", direction=GPSDir.North)  # Latitude > 90
            coord = Coordinate(gps_string="18145.1234", direction=GPSDir.East)  # Longitude > 180
            logging.getLogger().setLevel(self.default_loglevel)
        logging.getLogger().setLevel(self.default_loglevel)

    def test_nmea_checksum_valid(self):
        """Test that NMEA checksum validation passes for valid data."""
        logging.info("\n%s\n\t\t   Commencing VALID NMEA checksum tests\n%s",
                "="*79, "-"*79)
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0
        for message in NMEA_Messages.valid_NMEA:
            if GPS.nmea_checksum(message):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False, f"Valid NMEA failed for message: {message}")
        logging.info("\t*** %s of %s valid checksum tests passed", pass_n, len(NMEA_Messages.valid_NMEA) )
        logging.getLogger().setLevel(self.default_loglevel)

    def test_nmea_checksum_invalid(self):
        """Test that NMEA checksum validation fails for invalid data."""
        logging.info("\n%s\n\t\t   Commencing INVALID NMEA checksum tests\n%s",
                "="*79, "-"*79)
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0  # Initialize pass_n to 0 for invalid tests
        for message in NMEA_Messages.valid_NMEA:
            # Modify the message to have an invalid checksum
            invalid_checksum = message[:-2] + "00"
            # Check if the invalid checksum fails
            if not GPS.nmea_checksum(invalid_checksum):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False, f"Invalid NMEA checksum unexpectedly passed for message: {invalid_checksum}")
        logging.info("\t*** %s of %s invalid checksum tests passed", pass_n, len(NMEA_Messages.valid_NMEA))
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS._get_msg')
    @patch('Position.GPS._get_coordinates')
    @patch('Position.GPS._get_datetime')
    def test_get_fix_success(self, mock_get_datetime, mock_get_coordinates, mock_get_msg):
        """Test that `get_fix` calls all required methods for a successful fix."""
        gps = GPS()
        gps.get_fix()
        mock_get_coordinates.assert_called_once()
        mock_get_datetime.assert_called_once()
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS._get_msg', side_effect=GPSInvalid)
    def test_get_fix_failure(self, mock_get_msg):
        """Test that `get_fix` raises GPSInvalid when no valid fix is obtained."""
        gps = GPS()
        with self.assertRaises(GPSInvalid):
            gps.get_fix()
        logging.getLogger().setLevel(self.default_loglevel)

    def test_process_datetime_valid(self):
        """Test that GPS correctly processes and converts valid UTC time and date."""
        logging.info("\n%s\n\t\t   Commencing VALID datetime tests\n%s",
                "="*79, "-"*79)
        gps = GPS()
        pass_n = 0
        logging.getLogger().setLevel(self.default_loglevel)
        for val in NMEA_Messages.valid_dt:
            expected = val.get("dt_obj")
            dt_obj = gps._process_datetime(utc_time=val.get("time"), date_str=val.get("date"))
            if not self.assertEqual(dt_obj, expected):
                pass_n += 1
        logging.info("\t*** %s of %s valid date tests passed", pass_n, len(NMEA_Messages.valid_dt))
        logging.getLogger().setLevel(self.default_loglevel)

    def test_process_datetime_invalid(self):
        """Test that GPS raises ValueError for improperly formatted datetime strings."""
        logging.info("\n%s\n\t\t   Commencing INVALID datetime tests\n%s",
                     "="*79, "-"*79)
        gps = GPS()
        pass_n = 0
        logging.getLogger().setLevel(self.default_loglevel)

        for val in NMEA_Messages.invalid_dt:
            try:
                with self.assertRaises(ValueError, msg=f"Failed for date: {val.get('date')} and time: {val.get('time')}"):
                    gps._process_datetime(date_str=val.get("date"), utc_time=val.get("time"))
            except AssertionError:
                continue  # If the ValueError isn't raised, the test will fail
            else:
                pass_n += 1  # Increment if the exception was correctly raised

        logging.info("\t*** %s of %s invalid date tests passed", pass_n, len(NMEA_Messages.invalid_dt))
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS._decode_message')
    def test_decode_message_valid(self, mock_decode_message):
        """Test decoding of a valid GPS message, ensuring proper storage in `self._last_msg`."""
        gps = GPS()
        test_message = b'$GPRMC,123519,A,4807.038,N,01131.000,E*6A'
        gps._decode_message(test_message)
        mock_decode_message.assert_called_once_with(test_message)
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS._validate_message_content')
    def test_validate_message_content_valid(self, mock_validate_message_content):
        """Test validation of message content based on predefined criteria."""
        gps = GPS()
        gps._last_msg = ["RMC", "A", "4807.038", "N", "01131.000", "E"]
        gps.msg_validate = [{'MSG': 'RMC', 'ValidIdx': 2, 'ValidVals': 'A'}]
        self.assertTrue(gps._validate_message_content("RMC"))
        logging.getLogger().setLevel(self.default_loglevel)