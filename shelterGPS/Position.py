
"""shelterGPS.Position.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Get fixes and determine location.
Author: Will Bickerstaff
Version: 0.1
"""

import datetime as dt
import logging
import re
import serial
import subprocess
import time
import glob
from threading import Lock
from typing import Union, Optional
import lgpio
from shelterGPS.coord import Coordinate
from lightlib.config import ConfigLoader
from lightlib.smartlight import log_caller
from shelterGPS.common import GPSDir, GPSInvalid, GPSOutOfBoundsError


class GPS:
    """GPS Module for managing GPS data, fix attempts, and validation.

    Initializes the GPS module, controls its power state, retrieves,
    and validates GPS fixes. Handles coordinate, datetime information,
    and any potential errors encountered during fix attempts.
    """

    _instance = None
    _lock = Lock()  # Thread-safe lock for instance creation

    msg_validate = [
        {'MSG': 'GGA', 'ValidIdx': 6, 'ValidVals': '126'},
        {'MSG': 'GLL', 'ValidIdx': 6, 'ValidVals': 'A'},
        {'MSG': 'RMC', 'ValidIdx': 2, 'ValidVals': 'A'}
    ]
    msg_coords = [
        {'MSG': 'GGA', 'LAT': 2, 'NS': 3, 'LON': 4, 'EW': 5, 'ALT': 9},
        {'MSG': 'GLL', 'LAT': 1, 'NS': 2, 'LON': 3, 'EW': 4, 'ALT': -1},
        {'MSG': 'RMC', 'LAT': 3, 'NS': 4, 'LON': 5, 'EW': 6, 'ALT': -1}
    ]
    msg_dt = [
        {'MSG': 'GGA', 'UTC': 1, 'DATE': -1},
        {'MSG': 'GLL', 'UTC': 5, 'DATE': -1},
        {'MSG': 'RMC', 'UTC': 1, 'DATE': 9},
        {'MSG': 'ZDA', 'UTC': 1, 'DATE': 2}
    ]

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of GPS is created.

        This method implements the Singleton pattern for the `GPS`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns
        -------
            GPS: A single instance of the `GPS` class.
        """
        if not cls._instance:
            with cls._lock:  # Thread-safe check and assignment
                if not cls._instance:
                    cls._instance = super(GPS, cls).__new__(cls)
                    cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the GPS module and establish a serial connection.

        This initializer configures the GPS module by establishing a serial
        connection and setting up power control and other module parameters.
        The `ConfigLoader` singleton provides configuration values like serial
        port, baud rate, timeout, power-up time, maximum fix time, and GPIO
        pin configurations to initialize the GPS module's attributes.

        Attributes
        ----------
            _pwr_up_time (float): The time to wait after powering on the GPS
                module before attempting a fix.
            _max_fix_time (float): The maximum allowable time for attempting
                to obtain a GPS fix.
            __pwr_pin (int): GPIO pin used to power on/off the GPS module.
            __serial_port (str): Serial port address to connect to the GPS
                module.
            __gps_ser (serial.Serial): Serial connection object for
                communicating with the GPS module.
            _lat (float): Last recorded latitude from the GPS fix in decimal
                degrees.
            _lon (float): Last recorded longitude from the GPS fix in decimal
                degrees.
            _alt (float): Last recorded altitude from the GPS fix in meters.
            _dt (datetime.datetime): Last recorded datetime from the GPS fix
                in UTC.
            _last_msg (list): The most recent parsed message from the GPS,
                used for validation and troubleshooting.

        Raises
        ------
            serial.SerialException: If the serial connection to the GPS module
                cannot be established, logs the error and raises the exception.
        """
        if self.__initialized:
            return  # Skip reinitialization for singleton pattern

        # Actual initialization logic only runs once
        self.__serial_port = ConfigLoader().gps_serial_port
        try:
            # Open the serial connection with specified parameters
            self.__gps_ser = serial.Serial(
                port=self.__serial_port,
                baudrate=ConfigLoader().gps_baudrate,
                timeout=ConfigLoader().gps_timeout)
            logging.info("GPS: initialized with port %s", self.__serial_port)
        except serial.SerialException as e:
            logging.error("GPS: Failed to initialize serial port %s - %s",
                          self.__serial_port, e)
            available_ports = glob.glob('/dev/tty[A-Za-z]*')
            logging.debug("GPS: Available serial ports: %s", available_ports)
            self.__gps_ser = None

        # Initialize remaining attributes
        self._pwr_up_time = ConfigLoader().gps_pwr_up_time
        self._max_fix_time = ConfigLoader().gps_max_fix_time
        self.__pwr_pin = ConfigLoader().gps_pwr_pin
        self._lat = Coordinate()
        self._lon = Coordinate()
        self._alt = 0.0
        self._dt = dt.datetime(1970, 1, 1, 0, 0, 0, 0, tzinfo=dt.timezone.utc)
        self._last_msg = []
        self._datetime_established = False
        self._position_established = False

        # Mark as initialized
        self.__initialized = True

    def __del__(self):
        """Clean up resources when the GPS instance is deleted."""
        try:
            self.cleanup()
        except Exception as e:
            logging.warning("GPS __del__ cleanup failed: %s", e)

    @property
    def position_established(self) -> bool:
        """A bool representing if lat & lon has been established."""
        return self._position_established

    @property
    def datetime_established(self) -> bool:
        """A bool representing if date and time have been established."""
        return self._datetime_established

    @property
    def message_type(self) -> str:
        """Get the message type of the last message received from GPS module.

        (RMC, GGA, GLL, ZDA etc)
        """
        if self._last_msg is None:
            return
        return self._last_msg[0]

    @property
    def latitude_coord(self) -> Coordinate:
        """Coordinate object that represents latitude."""
        return self._lat

    @property
    def latitude(self) -> float:
        """Return the most recent lat from the GPS fix, in decimal degrees."""
        return self._lat.decimal_value

    @property
    def longitude_coord(self) -> Coordinate:
        """Coordinate object that represents longitude."""
        return self._lon

    @property
    def longitude(self) -> float:
        """Return the most recent lon from the GPS fix, in decimal degrees."""
        return self._lon.decimal_value

    @property
    def altitude(self) -> float:
        """Return the most recent altitude from the GPS fix, in meters."""
        return self._alt

    @property
    def datetime(self) -> dt.datetime:
        """Return the current UTC date and time from the GPS fix."""
        return self._dt

    @property
    def position_str(self) -> str:
        """Format and return position as a string."""
        return "\n\t".join([f"Lat: {self.lattitude:.2f}",
                            f"Lng: {self.longitude:.2f}",
                            f"Alt: {self.altitude:.2f}m"])

    def gpsCoord2Dec(self,
                     gps_coord: Union[str, float], direction: GPSDir) -> float:
        """Convert GPS coordinates from DMS format to decimal format.

        Args
        ----
            gps_coord (Union[str, float]): Coordinate from the GPS module.
            direction (GPSDir): Directional indicator [N,S,E,W].

        Returns
        -------
            float: The coordinate in signed decimal format.

        Raises
        ------
            GPSOutOfBoundsError: If the result is out of latitude or longitude
                                bounds or the input coordinate is negative.
        """
        self._coord = Coordinate(direction=direction, gps_string=gps_coord)
        return self._coord.decimal_value

# Attribution: NMEA checksum calculation adapted from Josh Sherman's guide
# https://doschman.blogspot.com/2013/01/calculating-nmea-sentence-checksums.html
    @staticmethod
    def nmea_checksum(msg_str: str = "") -> bool:
        """Calculate and verify the NMEA checksum for a GPS message string.

        This function is used to verify the integrity of an NMEA (National
        Marine Electronics Association) message received from a GPS device.
        The NMEA message includes a checksum at the end of the string, which is
        used to ensure that the message has not been corrupted during
        transmission. The checksum is calculated by XOR-ing the ASCII values of
        all characters between the '$' and '*' symbols.

        Args
        ----
            msg_str (str): The full NMEA message string, should begin with
                           a '$' character and end with a '*' followed by the
                           two-character hexadecimal checksum.

        Returns
        -------
            bool: True if the calculated checksum matches the checksum in the
                  message string, indicating that the message is valid and
                  uncorrupted. False if the checksums do not match, indicating
                  potential corruption or tampering.

        Example
        -------
            A valid NMEA message might look like:
            ```
            $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
            ```
            - The checksum `*47` at the end of the message is compared to the
              calculated checksum to verify the message integrity.

        Raises
        ------
            ValueError: If the message string is incorrectly formatted or does
                        not contain a valid checksum section. This error is
                        logged but does not halt the function.

        Note:
            - The checksum calculation only includes characters between '$' and
              '*', not including the '$' and '*'.
            - The comparison is case-insensitive, as the checksum is typically
              presented in uppercase but may be compared with a lowercase
              representation.
        """
        try:
            # Decode the message if it's in bytes
            if isinstance(msg_str, bytes):
                msg_str = msg_str.decode('utf-8')
            # Extract the checksum from the last two characters after  the '*'
            # `cksum` holds the expected checksum in hex format, located at
            # the end of the sentence.
            # Check if '*' is in the string, otherwise return False
            if not msg_str.startswith('$') or '*' not in msg_str:
                logging.warning("GPS: Invalid NMEA format, message does not "
                                "start with a $ or contain a *")
                return False

            # Extract the checksum after '*' and clean it: strip
            # whitespace/newlines and isolate the hex portion
            cksum = msg_str[msg_str.find("*") + 1:].strip().split()[0]

            # Isolate the main message content to compute checksum
            # Locate the part between '$' and '*', excluding both symbols.
            # `chksumdata` now contains the raw message that we will use to
            # calculate the checksum.
            chksumdata = re.sub(r"(\n|\r\n)", "",
                                msg_str[msg_str.find("$") + 1:
                                        msg_str.find("*")])

            # Calculate the checksum using XOR on each character
            # Initialize `csum` to zero; this will accumulate the XOR of each
            # character.
            csum = 0
            for c in chksumdata:
                csum ^= ord(c)  # XOR each character's ASCII value into `csum`.

            # Compare computed checksum with expected checksum
            # Convert `csum` to hex and compare with the extracted `cksum`
            # (converted to int).
            is_valid = hex(csum) == hex(int(cksum, 16))

            # Log and return result of checksum comparison
            # Log the result: pass or fail, based on if the checksum matched.
            if is_valid:
                logging.debug("GPS: NMEA checksum validation passed, computed "
                              "%s, expected 0x%s.", hex(csum), cksum)
            else:
                logging.warning("NMEA checksum mismatch: computed %s vs. "
                                "expected 0x%s", hex(csum), cksum)

            return is_valid

        except (TypeError, ValueError) as e:
            logging.debug(
                "GPS: Format issue during checksum calculation: %s", e)
            log_caller(module="GPS")
            return False

    def pwr_on(self, wait_after: Optional[float] = None) -> None:
        """Power up the GPS module by enabling its power pin.

        Args
        ----
           wait_after (Optional[float]): Time to wait after power on
                                         before continuing
        """
        try:
            # Open gpiochip0 if not already
            if not hasattr(self, '_gpio_handle') or self._gpio_handle is None:
                self._gpio_handle = lgpio.gpiochip_open(0)

            # Claim the GPS pin as OUTPUT
            lgpio.gpio_claim_output(
                self._gpio_handle, self.__pwr_pin, lgpio.LOW)

            # Drive it HIGH to turn GPS ON
            lgpio.gpio_write(self._gpio_handle, self.__pwr_pin, lgpio.HIGH)
            logging.info("GPS powered ON (GPIO %s set HIGH)", self.__pwr_pin)

            # Optional wait to stabilize power
            if wait_after:
                time.sleep(wait_after)

        except Exception as e:
            logging.error("Failed to power ON GPS: %s", e)
            if hasattr(self, '_gpio_handle') and self._gpio_handle is not None:
                lgpio.gpiochip_close(self._gpio_handle)
                logging.info("GPS Powered off.")
                self._gpio_handle = None

    def pwr_off(self) -> None:
        """Disable the GPS module by setting its power control pin to LOW."""
        try:
            if hasattr(self, '_gpio_handle') and self._gpio_handle is not None:
                lgpio.gpio_write(self._gpio_handle, self.__pwr_pin, lgpio.LOW)
                lgpio.gpiochip_close(self._gpio_handle)
                logging.info("GPS Powered off.")
                self._gpio_handle = None
            else:
                logging.debug("GPS power off called no valid GPIO handle")
        except Exception as e:
            logging.error("Failed to power off GPS: %s", e)
            self._gpio_handle = None

    def get_fix(self, pwr_up_wait: float = None,
                max_fix_time: float = None) -> None:
        """Attempt to obtain a GPS fix, retrieving coordinates and timestamp.

        Args
        ----
            pwr_up_wait (float): Time to wait in seconds after powering on the
            module. Defaulting to that in config file
            max_fix_time (float): Max time to attempt to acquire GPS fix data
            in seconds. Defaulting to that in config file

        Raises
        ------
            GPSInvalid: Raised if a valid fix cannot be obtained within the
                        specified time.

        Notes
        -----
            **Run in a separate thread** or you could potentially
            be stuck in a loop until you fix or the max_fix_time expires
        """
        if pwr_up_wait is None:
            pwr_up_wait = self._pwr_up_time

        if max_fix_time is None:
            max_fix_time = self._max_fix_time

        logging.info("GPS: Starting fix attempt with power-up wait %s "
                     "and max duration of %s", pwr_up_wait, max_fix_time)

        self.pwr_on(pwr_up_wait)

        try:
            if self.__gps_ser is None:
                logging.error("GPS Serial connection not initialized is %s "
                              "the correct serial port?", self.__serial_port)
                self._initialise_serial()

            self._get_coordinates(max_fix_time)
            self._get_datetime(max_fix_time)
        except GPSInvalid:
            logging.error("GPS: Failed to acquire a fix.")
            raise
        finally:
            self.pwr_off()

    def _initialise_serial(self) -> None:
        """Attempt to initialse the GPS serial connection."""
        ports_to_try = ["/dev/ttyAMA0", "/dev/serial0", "/dev/s0"]
        for port in ports_to_try:
            try:
                logging.info("Attempting to open GPS serial port %s", port)
                self.__gps_ser = serial.Serial(
                    port=port,
                    baudrate=ConfigLoader().gps_baudrate,
                    timeout=ConfigLoader().gps_timeout)
                if self.__gps_ser.is_open:
                    logging.info("GPS serial port %s opened successfuly", port)
                    return
            except (serial.SerialException, AttributeError) as e:
                logging.warning(
                    "Failed to open GPS srial port %s: %s", port, e)
                self.__gps_ser = None

        logging.error("Unable to find GPS module on any serial port.")
        raise GPSInvalid("Could not establish a serial connection with the "
                         "GPS module.")

    def _get_msg(self, msg: str = "RMC", max_time: float = None) -> None:
        """Read and validate GPS messages, storing if correct.

        Continuously attempts to read from the GPS module until a valid message
        of the specified type is received or the maximum time is reached.

        Args
        ----
            msg (str): NMEA message type, e.g., "RMC" or "GGA".
            max_time (float): Maximum time to wait for a valid message, in
                              seconds. if None given uses that from config file

        Raises
        ------
            GPSInvalid: If no valid message is obtained within `max_time`.
        """
        if max_time is None:
            max_time = self._max_fix_time
        logging.info("GPS: Attempting to read %s message for %s seconds",
                     msg, max_time)
        start_time: dt.datetime = dt.datetime.now()
        # Keep trying until we get the required message and it validates
        # or we reach the defined maximum attempt duration
        while dt.datetime.now() - start_time < dt.timedelta(seconds=max_time):
            ser_line: str = self.__gps_ser.readline()
            logging.debug("GPS Raw message received:\n\t%s", ser_line)
            # Check if message is valid and proceed with decoding and
            # content verification if true
            if self._is_valid_message(ser_line):
                self._decode_message(ser_line)
                if self._validate_message_content(msg):
                    return True  # Exit once a valid message is confirmed

        raise GPSInvalid(f"No valid fix obtained after {max_time} seconds")

    def _is_valid_message(self, ser_line: bytes) -> bool:
        """Check if the message has content and passes checksum validation.

        Args
        ----
            ser_line (Union[bytes,str]): Raw byte line or string read from the
                                        GPS serial input.

        Returns
        -------
            bool: True if the message has content and passes checksum
                  validation; False otherwise.
        """
        # Serial line must be at least 15 characters to contain the message
        # identifier, some basic data fields, and a valid checksum (e.g.,
        # $GPGGA,1234.56,N*CS).
        MIN_MSG_LEN: int = 14
        return len(ser_line) > MIN_MSG_LEN and self.nmea_checksum(ser_line)

    def _decode_message(self, ser_line: Union[bytes, str]) -> None:
        """Decode and parse GPS message, removing checksum for validation.

        Decodes the raw message, splits it by commas, removes the checksum,
        and stores the decoded message in `self._last_msg`.

        Args
        ----
            ser_line (bytes): Raw byte line read from the GPS serial input.

        Raises
        ------
            ValueError: Logs a decoding error if the message cannot be
                        processed.
        """
        try:
            # Decode the raw line and split into components by commas
            if isinstance(ser_line, bytes):
                ser_line = ser_line.decode(errors="ignore")
            self._last_msg = ser_line.split(",")

            # store trailing checksum from final field cleanly
            # checksum is validated elsewhere
            raw_checksum = self._last_msg[-1].split("*")[-1].strip()[:2]
            self._last_msg[-1] = self._last_msg[-1].split("*")[0].strip()
            self._last_msg.append(raw_checksum)
            logging.debug("GPS: Decoded message: %s", self._last_msg)

        except ValueError as ve:
            logging.error("GPS: Error decoding message: %s", ve)

    def _validate_message_content(self, msg: str) -> bool:
        """Check if the message content matches expected validation criteria.

        Uses the validated message type and specific indices for validation,
        cross-referencing with `self.msg_validate`.

        Args
        ----
            msg (str): Expected NMEA message type for validation e.g GGA, RMC.

        Returns
        -------
            bool: True if the message content meets validation criteria;
                False otherwise.
        """
        valid_vals = None
        valid_idx = None
        msg_type = self._last_msg[0][-3:]
        if msg_type != msg:
            logging.debug("Read a%s %s message, waiting for a%s %s",
                          "n" if msg_type == "RMC" else "",
                          msg_type,
                          "n" if msg == "RMC" else "",
                          msg)
            return False

        logging.info("Got a%s %s Message!!!", "n" if msg_type == "RMC" else "",
                     msg_type)

        for entry in self.msg_validate:
            if msg_type == entry['MSG']:
                # Verify that the message status\validation field contains
                # a value indicating validated data
                valid_idx = entry['ValidIdx']
                valid_vals = entry['ValidVals']
                if self._last_msg[valid_idx] in valid_vals:
                    logging.info("%s message is valid.", msg_type)
                    return True
                logging.info(
                    "GPS: %s message does not include a validated data "
                    "indicator. (field %s does not contain%s%s)",
                    msg, valid_idx, " any of "if msg == "GGA" else " ",
                    list(valid_vals) if isinstance(valid_vals, str) else
                    valid_vals)
                return False

        logging.debug("GPS: Non-tracked message type %s; skipping.", msg_type)
        return False

    def _get_coordinates(self, fix_wait: float) -> None:
        """Retrieve GPS coordinates from the module.

        Args
        ----
            fix_wait (float): Maximum time to attempt to retrieve coordinates.

        Raises
        ------
            GPSInvalid: If coordinates cannot be retrieved within `fix_wait`.
        """
        if not self._get_msg('GGA', fix_wait):
            return
        self._position_established = False
        matched = False
        for entry in self.msg_coords:
            if self._last_msg[0][-3:] == entry['MSG']:
                try:
                    logging.debug("COORD: %s", self._last_msg)
                    self._lat = Coordinate(
                        gps_string=self._last_msg[entry['LAT']],
                        direction=GPSDir[self._last_msg[entry['NS']]])
                    self._lon = Coordinate(
                        gps_string=self._last_msg[entry['LON']],
                        direction=GPSDir[self._last_msg[entry['EW']]])
                    # Check if 'ALT' field exists and set altitude accordingly
                    if entry['ALT'] != -1 and entry['ALT'] < (
                            len(self._last_msg)):
                        self._alt = float(self._last_msg[entry['ALT']])
                    else:
                        self._alt = 0.0
                    logging.info("GPS: Position fix obtained:\n\t%s, "
                                 "\n\t%s\n\tAlt: %s",
                                 self._lat.to_string(),
                                 self._lon.to_string(), self._alt)
                    self._position_established = True
                    matched = True
                except GPSOutOfBoundsError as obe:
                    logging.warning("GPS: Out-of-bounds coordinate: %s", obe)
                except (KeyError, ValueError) as e:
                    logging.error("GPS: Error processing coordinates: %s", e)
                    raise GPSInvalid("Failed to retrieve coordinates.")
        if not matched:
            logging.debug("Never matched a %s in msg_coords",
                          self._last_msg[0][-3:])

    def _get_datetime(self, fix_wait: float) -> None:
        """Retrieve GPS datetime from the module.

        Args
        ----
            fix_wait (float): Maximum time to attempt to retrieve datetime.

        Raises
        ------
            GPSInvalid: If datetime cannot be retrieved within `fix_wait`.
        """
        if not self._get_msg('RMC', fix_wait):
            return
        self._datetime_established = False
        matched = False
        for entry in self.msg_dt:
            if self._last_msg[0][-3:] == entry['MSG']:
                try:
                    utc_time = self._last_msg[entry['UTC']]
                    date_str = (self._last_msg[entry['DATE']]
                                if entry['DATE'] != -1 else None)
                    self._dt = self._process_datetime(utc_time, date_str)
                    logging.info(
                        "GPS: Date and time obtained: %s", self._dt)
                    self._datetime_established = True
                    self._sync_system_time()
                    matched = True
                except (KeyError, ValueError) as e:
                    logging.error("GPS: Error processing datetime: %s", e)
                    raise GPSInvalid("Failed to retrieve datetime.")
        if not matched:
            logging.debug("Never matched a %s in msg_dt",
                          self._last_msg[0][-3:])

    def _process_datetime(self, utc_time: str,
                          date_str: Optional[str] = None) -> dt.datetime:
        """Convert UTC time and optional date str into tz-aware datetime.

        Args
        ----
            utc_time (str): UTC time in 'hhmmss' format.
            date_str (Optional[str]): Optional date in 'yymmdd' format.

        Returns
        -------
            dt.datetime: A timezone-aware datetime object in UTC.

        Raises
        ------
            ValueError: If `utc_time` or `date_str` is incorrectly formatted.
        """
        try:
            # Split every 2 characters
            time_parts = [utc_time[i:i+2] for i in range(0, len(utc_time), 2)]
            logging.debug("GPS: Time string contains (hh)%s:(mm)%s:(ss)%s",
                          time_parts[0], time_parts[1], time_parts[2],)
            utc_time_obj = dt.time(int(time_parts[0]),
                                   int(time_parts[1]),
                                   int(time_parts[2]))
        except (ValueError, IndexError) as e:
            logging.error("\n%s", "-"*79)
            logging.error("GPS: *** Invalid UTC time format '%s'. Error: %s",
                          utc_time, e)
            log_caller(module="GPS")
            raise ValueError(f"Invalid UTC time format: {utc_time}") from e

        try:
            if date_str:
                # Split every 2 characters
                date_parts = [date_str[i:i+2]
                              for i in range(0, len(date_str), 2)]
                logging.debug("GPS: Date string contains (YY)%s-(MM)%s-(DD)%s",
                              date_parts[0], date_parts[1], date_parts[2],)
                date_obj = dt.date(int("20" + date_parts[2]),
                                   int(date_parts[1]),
                                   int(date_parts[0]))
            else:
                date_obj = dt.date.today()

            date_obj = dt.datetime.combine(
                date_obj, utc_time_obj).replace(tzinfo=dt.timezone.utc)
            logging.info("GPS: Datetime is %s", str(date_obj))
            return date_obj
        except (ValueError, IndexError) as e:
            logging.error("\n%s", "-"*79)
            logging.error("GPS: *** Invalid date format '%s'. Error: %s",
                          date_str, e)
            log_caller(module="GPS")
            raise ValueError(f"Invalid date format: {date_str}") from e

    def _sync_system_time(self) -> None:
        """Set system time to UTC datetime from GPS fix."""
        if self._datetime_established:
            iso_time = self._dt.isoformat()
            try:
                subprocess.run(["sudo", "/bin/date", "-s", iso_time],
                               check=True)
                logging.info(f"System time synced to GPS time: {iso_time}")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to sync system time: {e}")
        else:
            logging.warning("System time sync skipped. No valid datetime fix.")

    def cleanup(self):
        """Clean up serial and GPIO resources.

        This method ensures that the serial connection and GPIO resources
        are properly released when the instance is no longer in use.
        """
        # Close the serial connection if it exists and is open
        if hasattr(self, '_GPS__gps_ser') and self.__gps_ser is not None and \
                self.__gps_ser.is_open:
            try:
                self.__gps_ser.close()
                logging.info("Serial connection closed.")
            except serial.SerialException as e:
                logging.error("Failed to close serial connection: %s", e)

        # Clean up GPIO resources
        if hasattr(self, '_gpio_handle') and self._gpio_handle is not None:
            try:
                lgpio.gpio_write(self._gpio_handle, self.__pwr_pin, lgpio.LOW)
                logging.info("GPS: Power pin set LOW during cleanup.")
            except Exception as e:
                logging.warning("GPS: Failed to set power pin LOW "
                                "during cleanup: %s", e)

            try:
                lgpio.gpiochip_close(self._gpio_handle)
                logging.info("GPS: gpiochip handle closed during cleanup.")
            except Exception as e:
                logging.warning("GPS: Failed to close gpiochip handle: %s", e)

            self._gpio_handle = None  # Mark as cleaned up
