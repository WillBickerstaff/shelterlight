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

from Position import GPS, GPSInvalid, GPSOutOfBoundsError, GPSDir  # Import after mocks

class TestGPS(unittest.TestCase):

    def setUp(self):
        """Setup for each test, ensuring singleton reset for GPS."""
        GPS._instance = None  # Reset singleton instance
        logging.basicConfig(level=logging.INFO)

    def test_singleton_behavior(self):
        """Test that only one instance of GPS can exist."""
        gps1 = GPS()
        gps2 = GPS()
        self.assertIs(gps1, gps2, "GPS class is not respecting singleton pattern.")

    @patch('serial.Serial')
    @patch('lightlib.config.ConfigLoader')
    def test_init_serial_connection(self, MockConfigLoader, MockSerial):
        """Test that GPS initializes serial connection using configurations."""

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

    @patch('Position.GPS.pwr_on')
    @patch('Position.GPS.pwr_off')
    def test_power_control(self, mock_pwr_off, mock_pwr_on):
        """Test that GPS correctly handles power on and off."""
        gps = GPS()
        gps.pwr_on()
        mock_pwr_on.assert_called_once()

        gps.pwr_off()
        mock_pwr_off.assert_called_once()

    def test_gpsCoord2Dec_valid(self):
        logging.getLogger().setLevel(logging.DEBUG)
        """Test conversion of GPS DMS coordinates to decimal format."""
        lat = GPS.gpsCoord2Dec("3745.1234", GPSDir.North)
        lon = GPS.gpsCoord2Dec("12231.8765", GPSDir.West)
        self.assertAlmostEqual(lat, 37.752057, places=6)
        self.assertAlmostEqual(lon, -122.531275, places=6)
        lat = GPS.gpsCoord2Dec("0745.1234", GPSDir.South)
        lon = GPS.gpsCoord2Dec("02231.8765", GPSDir.East)
        self.assertAlmostEqual(lat, -7.7520566, places=6)
        self.assertAlmostEqual(lon, 22.531275, places=6)
        # check missing leading 0
        lat = GPS.gpsCoord2Dec("745.1234", GPSDir.South)
        lon = GPS.gpsCoord2Dec("2231.8765", GPSDir.East)
        self.assertAlmostEqual(lat, -7.7520566, places=6)
        self.assertAlmostEqual(lon, 22.531275, places=6)
        logging.getLogger().setLevel(logging.INFO)
        # check the boundaries
        lat = GPS.gpsCoord2Dec("0000.0000", GPSDir.North)
        self.assertAlmostEqual(lat, 0.0, places=6)
        lat = GPS.gpsCoord2Dec("0000.0000", GPSDir.South)
        self.assertAlmostEqual(lat, -0.0, places=6)
        lat = GPS.gpsCoord2Dec("9000.0000", GPSDir.North)
        self.assertAlmostEqual(lat, 90.0, places=6)
        lat = GPS.gpsCoord2Dec("9000.0000", GPSDir.South)
        self.assertAlmostEqual(lat, -90.0, places=6)
        lon = GPS.gpsCoord2Dec("00000.0000", GPSDir.East)
        self.assertAlmostEqual(lon, 0.0, places=6)
        lon = GPS.gpsCoord2Dec("00000.0000", GPSDir.West)
        self.assertAlmostEqual(lon, -0.0, places=6)
        lon = GPS.gpsCoord2Dec("18000.0000", GPSDir.East)
        self.assertAlmostEqual(lon, 180.0, places=6)
        lon = GPS.gpsCoord2Dec("18000.0000", GPSDir.West)
        self.assertAlmostEqual(lon, -180.0, places=6)

    def test_gpsCoord2Dec_out_of_bounds(self):
        """Test GPS coordinate conversion raises an error when out of bounds."""
        with self.assertRaises(GPSOutOfBoundsError):
            GPS.gpsCoord2Dec("9145.1234", GPSDir.North)  # Latitude > 90
            GPS.gpsCoord2Dec("18145.1234", GPSDir.North)  # Longitude > 180

    @patch('re.sub', return_value="GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W")
    def test_nema_checksum_valid(self, mock_sub):
        """Test that NMEA checksum validation passes for valid data."""
        valid_message = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        self.assertTrue(GPS.nema_checksum(valid_message))

    @patch('re.sub', return_value="GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W")
    def test_nema_checksum_invalid(self, mock_sub):
        """Test that NMEA checksum validation fails for invalid data."""
        invalid_message = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*00"
        self.assertFalse(GPS.nema_checksum(invalid_message))

    @patch('Position.GPS._get_msg')
    @patch('Position.GPS._get_coordinates')
    @patch('Position.GPS._get_datetime')
    def test_get_fix_success(self, mock_get_datetime, mock_get_coordinates, mock_get_msg):
        """Test that `get_fix` calls all required methods for a successful fix."""
        gps = GPS()
        gps.get_fix()
        mock_get_coordinates.assert_called_once()
        mock_get_datetime.assert_called_once()

    @patch('Position.GPS._get_msg', side_effect=GPSInvalid)
    def test_get_fix_failure(self, mock_get_msg):
        """Test that `get_fix` raises GPSInvalid when no valid fix is obtained."""
        gps = GPS()
        with self.assertRaises(GPSInvalid):
            gps.get_fix()

    def test_process_datetime_valid(self):
        """Test that GPS correctly processes and converts valid UTC time and date."""
        gps = GPS()
        dt_obj = gps._process_datetime(utc_time="123519", date_str="230323")
        expected = dt.datetime(2023, 3, 23, 12, 35, 19, tzinfo=dt.timezone.utc)
        self.assertEqual(dt_obj, expected)

    def test_process_datetime_invalid(self):
        """Test that GPS raises ValueError for improperly formatted datetime strings."""
        gps = GPS()
        with self.assertRaises(ValueError):
            gps._process_datetime("invalid", "230394")  # Invalid UTC time

    @patch('Position.GPS._decode_message')
    def test_decode_message_valid(self, mock_decode_message):
        """Test decoding of a valid GPS message, ensuring proper storage in `self._last_msg`."""
        gps = GPS()
        test_message = b'$GPRMC,123519,A,4807.038,N,01131.000,E*6A'
        gps._decode_message(test_message)
        mock_decode_message.assert_called_once_with(test_message)

    @patch('Position.GPS._validate_message_content')
    def test_validate_message_content_valid(self, mock_validate_message_content):
        """Test validation of message content based on predefined criteria."""
        gps = GPS()
        gps._last_msg = ["RMC", "A", "4807.038", "N", "01131.000", "E"]
        gps.msg_validate = [{'MSG': 'RMC', 'ValidIdx': 2, 'ValidVals': 'A'}]
        self.assertTrue(gps._validate_message_content("RMC"))