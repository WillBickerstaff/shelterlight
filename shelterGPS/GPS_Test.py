import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys, os
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

    def test_singleton_behavior(self):
        """Test that only one instance of GPS can exist."""
        gps1 = GPS()
        gps2 = GPS()
        self.assertIs(gps1, gps2, "GPS class is not respecting singleton pattern.")

    @patch('serial.Serial')
    @patch('lightlib.ConfigLoader')
    def test_init_serial_connection(self, MockConfigLoader, MockSerial):
        """Test that GPS initializes serial connection using configurations."""
        # Mock configuration loader values
        config = MockConfigLoader.return_value
        config.gps_serial_port = '/dev/serial0'
        config.gps_baudrate = 9600
        config.gps_timeout = 0.5
        config.gps_pwr_pin = 4

        gps = GPS()

        # Assert serial port is set up with correct parameters
        MockSerial.assert_called_with(port='/dev/serial0',
                                      baudrate=9600, timeout=0.5)

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
        """Test conversion of GPS DMS coordinates to decimal format."""
        lat = GPS.gpsCoord2Dec("3745.1234", GPSDir.North)
        lon = GPS.gpsCoord2Dec("12231.8765", GPSDir.West)
        self.assertAlmostEqual(lat, 37.752057, places=6)
        self.assertAlmostEqual(lon, -122.531275, places=6)

    def test_gpsCoord2Dec_out_of_bounds(self):
        """Test GPS coordinate conversion raises an error when out of bounds."""
        with self.assertRaises(GPSOutOfBoundsError):
            GPS.gpsCoord2Dec("9145.1234", GPSDir.North)  # Latitude > 90

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
        dt = gps._process_datetime("123519", "230394")
        expected = datetime(1994, 3, 23, 12, 35, 19, tzinfo=datetime.timezone.utc)
        self.assertEqual(dt, expected)

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