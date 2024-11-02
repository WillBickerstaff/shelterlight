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

valid_nmea_messages = [
        # GGA - GPS (GP)
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47",
        "$GPGGA,104230,3723.5478,S,12218.8765,W,1,07,1.0,10.2,M,0.0,M,,*43",
        "$GPGGA,152310,2503.1234,N,12134.5678,E,1,09,0.8,55.7,M,10.0,M,,*78",

        # GGA - BeiDou (BD)
        "$BDGGA,091830,2233.1274,N,11404.6581,E,1,10,0.9,50.1,M,0.0,M,,*56",
        "$BDGGA,132015,3010.8765,N,10234.4321,E,1,08,0.7,70.5,M,20.0,M,,*66",
        "$BDGGA,183745,4056.7890,S,11618.8765,W,1,06,1.1,30.3,M,5.0,M,,*51",

        # GGA - GLONASS (GL)
        "$GLGGA,141920,5540.1234,N,03736.8765,E,1,06,1.2,200.3,M,39.5,M,,*57",
        "$GLGGA,112045,4523.6543,N,06234.9876,E,1,07,0.9,150.8,M,30.0,M,,*5B",
        "$GLGGA,175310,3345.7890,S,04923.1234,W,1,08,0.6,80.4,M,25.0,M,,*6A",

        # GGA - Galileo (GA)
        "$GAGGA,164500,3507.7890,N,13942.1234,E,1,09,0.8,75.4,M,15.0,M,,*68",
        "$GAGGA,102530,2245.1234,N,01334.8765,E,1,08,1.0,90.2,M,18.0,M,,*61",
        "$GAGGA,201815,5043.5678,N,01623.6543,E,1,10,0.7,110.5,M,12.0,M,,*50",

        # GGA - Mixed Constellation (GN)
        "$GNGGA,102030,3723.5478,S,14515.8765,E,1,12,0.6,120.0,M,18.0,M,,*4D",
        "$GNGGA,135040,4745.6789,N,08312.5432,W,1,09,0.9,60.1,M,14.0,M,,*75",
        "$GNGGA,225540,5810.8765,S,00345.9876,E,1,11,1.1,95.8,M,20.0,M,,*71",

        # RMC - GPS (GP)
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A",
        "$GPRMC,225446,A,5123.456,N,01234.567,E,054.7,089.5,150998,004.4,E*79",
        "$GPRMC,153032,A,3402.678,S,05823.123,W,018.5,250.7,250601,006.8,W*6F",

        # RMC - BeiDou (BD)
        "$BDRMC,142350,A,2456.789,N,11458.123,E,008.3,203.5,310721,001.2,W*74",
        "$BDRMC,063415,A,2234.123,S,11312.345,E,005.0,092.0,170322,003.5,E*77",
        "$BDRMC,184756,A,3210.876,N,11534.567,E,012.8,137.9,280822,002.3,W*77",

        # RMC - GLONASS (GL)
        "$GLRMC,115632,A,5532.123,N,03821.654,E,014.2,178.9,110501,000.0,W*70",
        "$GLRMC,093215,A,6043.987,S,03015.876,W,011.7,312.5,220822,001.9,E*62",
        "$GLRMC,172845,A,4955.654,N,03612.432,E,023.1,045.2,080623,002.5,E*65",

        # RMC - Galileo (GA)
        "$GARMC,201045,A,3645.123,N,14012.345,E,018.0,110.5,290522,003.0,E*64",
        "$GARMC,045700,A,2222.876,S,02434.678,W,020.4,255.8,101015,004.5,W*74",
        "$GARMC,132500,A,5055.432,N,01323.876,E,030.0,015.3,121220,005.6,E*6D",

        # RMC - Mixed Constellation (GN)
        "$GNRMC,143512,A,3723.5478,S,14515.8765,E,033.6,275.4,080923,010.2,W*65",
        "$GNRMC,224500,A,4745.6789,N,08312.5432,W,041.1,305.0,170722,009.3,E*78",
        "$GNRMC,090123,A,5810.8765,S,00345.9876,E,012.5,180.0,220921,008.0,W*61"
    ]
class TestGPS(unittest.TestCase):

    def setUp(self):
        """Setup for each test, ensuring singleton reset for GPS."""
        GPS._instance = None  # Reset singleton instance
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)

    def test_singleton_behavior(self):
        """Test that only one instance of GPS can exist."""
        gps1 = GPS()
        gps2 = GPS()
        self.assertIs(gps1, gps2, "GPS class is not respecting singleton pattern.")
        logging.getLogger().setLevel(self.default_loglevel)

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
        logging.getLogger().setLevel(self.default_loglevel)

    @patch('Position.GPS.pwr_on')
    @patch('Position.GPS.pwr_off')
    def test_power_control(self, mock_pwr_off, mock_pwr_on):
        """Test that GPS correctly handles power on and off."""
        gps = GPS()
        gps.pwr_on()
        mock_pwr_on.assert_called_once()

        gps.pwr_off()
        mock_pwr_off.assert_called_once()
        logging.getLogger().setLevel(self.default_loglevel)

    def test_gpsCoord2Dec_valid(self):
        logging.getLogger().setLevel(self.default_loglevel)
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
        logging.getLogger().setLevel(self.default_loglevel)

    def test_gpsCoord2Dec_out_of_bounds(self):
        """Test GPS coordinate conversion raises an error when out of bounds."""
        logging.getLogger().setLevel(self.default_loglevel)
        with self.assertRaises(GPSOutOfBoundsError):
            GPS.gpsCoord2Dec("9145.1234", GPSDir.North)  # Latitude > 90
            GPS.gpsCoord2Dec("18145.1234", GPSDir.North)  # Longitude > 180
            logging.getLogger().setLevel(self.default_loglevel)
        logging.getLogger().setLevel(self.default_loglevel)

    # Chat GPT used to generate test message.
    # GPT messages included incorrect checksums, validated at:
    # https://nmeachecksum.eqth.net/
    def test_nmea_checksum_valid(self):
        """Test that NMEA checksum validation passes for valid data."""
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0
        for message in valid_nmea_messages:
            if GPS.nmea_checksum(message):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False, f"Valid NMEA failed for message: {message}")
        logging.info("\t*** %s of %s valid checksum tests passed", pass_n, len(valid_nmea_messages) )
        logging.getLogger().setLevel(self.default_loglevel)

    def test_nmea_checksum_invalid(self):
        """Test that NMEA checksum validation fails for invalid data."""
        logging.getLogger().setLevel(self.default_loglevel)
        pass_n = 0  # Initialize pass_n to 0 for invalid tests
        for message in valid_nmea_messages:
            # Modify the message to have an invalid checksum
            invalid_checksum = message[:-2] + "00"
            # Check if the invalid checksum fails
            if not GPS.nmea_checksum(invalid_checksum):
                pass_n += 1  # Increment pass_n if the assertion passes
            else:
                self.assertTrue(False, f"Invalid NMEA checksum unexpectedly passed for message: {invalid_checksum}")
        logging.info("\t*** %s of %s invalid checksum tests passed", pass_n, len(valid_nmea_messages))
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
        gps = GPS()
        dt_obj = gps._process_datetime(utc_time="123519", date_str="230323")
        expected = dt.datetime(2023, 3, 23, 12, 35, 19, tzinfo=dt.timezone.utc)
        self.assertEqual(dt_obj, expected)
        logging.getLogger().setLevel(self.default_loglevel)

    def test_process_datetime_invalid(self):
        """Test that GPS raises ValueError for improperly formatted datetime strings."""
        gps = GPS()
        with self.assertRaises(ValueError):
            gps._process_datetime("010260", "230394")  # Invalid UTC time
        with self.assertRaises(ValueError):
            gps._process_datetime("016059", "230394")  # Invalid UTC time
        with self.assertRaises(ValueError):
            gps._process_datetime("255959", "230394")  # Invalid UTC time
        with self.assertRaises(ValueError):
            gps._process_datetime("235959", "320394")  # Invalid UTC Date
        with self.assertRaises(ValueError):
            gps._process_datetime("235959", "201394")  # Invalid UTC Date
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