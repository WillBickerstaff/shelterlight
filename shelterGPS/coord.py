import logging
from typing import Optional, Union
from shelterGPS.common import GPSDir, GPSOutOfBoundsError, NegativeValueError

class Coordinate:
    """
    A class to represent and handle GPS coordinates in both DMS (degrees,
    minutes, and seconds) and decimal formats.

    This class manages the conversion of GPS coordinates provided in a string
    format to decimal degrees, considering the direction (latitude or longitude)
    and performing validation to ensure the values are within acceptable
    geographic bounds. The class supports both latitude (North/South) and
    longitude (East/West) directions.

    Attributes:
        direction (GPSDir): The cardinal direction of the coordinate
        (N, S, E, W). lat_lng_str (str): Returns "Latitude" if the coordinate
        is latitude; "Longitude" otherwise. is_latitude (bool): Indicates if
        the coordinate is a latitude. is_longitude (bool): Indicates if the
        coordinate is a longitude. decimal_value (float): The decimal
        representation of the GPS coordinate. gps_string (str): The original
        GPS coordinate in string format, with appropriate formatting.

    Methods:
        gps_string.setter: Sets the GPS coordinate string, ensuring it is
                positive and correctly formatted.
        _deg_min_sec: Splits the GPS coordinate string into degrees, minutes,
                and seconds, and logs the values.
        _decimal: Converts the DMS coordinate to decimal format and
                validates it.
        _validate_decimal: Validates the decimal coordinate to ensure it is
                within geographic bounds.
    """

    def __init__(self, direction: Optional[GPSDir] = None,
                 gps_string: Optional[str] = None):
        """
        Initialize a Coordinate object.

        Args:
            direction (Optional[GPSDir]): The direction of the coordinate
                                          (N, S, E, W). Defaults to None.
            gps_string (Optional[str]): The GPS coordinate in string format.
                                        Defaults to None.

        Raises:
            ValueError: If the provided GPS coordinate string is negative.
        """
        self._dir = None
        self._gps_str = None
        self._degree_len = 0
        self._dec = 0.0
        if direction is not None:
            self.direction = direction
        if gps_string is not None:
            logging.debug("COORD: Initialized with GPS string %s", gps_string)
            self.gps_string = gps_string
        self._calc_coords()

    @property
    def direction(self) -> GPSDir:
        """Get the direction of the coordinate."""
        return self._dir

    @property
    def lat_lng_str(self) -> str:
        """Return 'Latitude' if the coordinate is a latitude, 'Longitude'
           otherwise."""
        return "Latitude" if self.is_latitude else "Longitude"

    @direction.setter
    def direction(self, direction: GPSDir):
        """Set the GPS coordinate string, ensuring it is positive and formatted correctly.

        This method accepts the GPS coordinate in either string or float format.
        If a float is provided, it is converted to a string to ensure consistent
        formatting. The coordinate is then formatted to match NMEA 0183
        standards:
        - Latitude: ddmm.ssss
        - Longitude: dddmm.ssss

        The string is padded with 0's as needed before being stored in the class
        variable. If the coordinate string is set before direction, padding of
        the string will not occur until direction is set.

        Args:
            gps_str (Union[str, float]): The GPS coordinate in string or float
                                         format.
                - If a float is provided, it will be converted to a string.

        Raises:
            GPSOutOfBoundsError: If the GPS coordinate string is negative or
                                 cannot be converted to a valid number.

        Example:
            # Pads to '00123.4560' if longitude '0123.4560 if latitude
            instCoordinate.gps_string = "123.456"
            # Converts to '45.6700' and pads to :
            # '00045.6700' if  longitude and ' 0045.6700' if latitude
            instCoordinate.gps_string = 45.67
            # Resets _gps_str to None
            instCoordinate.gps_string = None
        """
        if direction not in GPSDir:
            raise ValueError(f"Coordinate direction is invalid: {direction}")
        self._dir = direction
        logging.debug("COORD: Direction set to %s (%s)", self._dir, type(self._dir))
        self._degree_len = 3 if self.is_longitude else 2
        self._pad_gps_string()

    @property
    def is_latitude(self) -> bool:
        """Return True if the coordinate is a latitude (North/South), False
           otherwise."""
        return self.direction in [GPSDir.North, GPSDir.South]

    @property
    def degrees(self) -> int:
        """Get the degrees component of the GPS coordinate.

        Returns:
            int: The degrees component of the GPS coordinate.
        """
        return self._deg

    @property
    def minutes(self) -> int:
        """Get the minutes component of the GPS coordinate.

        Returns:
            int: The minutes component of the GPS coordinate as an integer.
        """
        return int(self._min)

    @property
    def seconds(self) -> float:
        """Get the seconds component of the GPS coordinate.

        Returns:
            float: The seconds component of the GPS coordinate as a float.
        """
        return (self._min - self.minutes) * 60

    @property
    def deg_min_sec(self) -> str:
        """Get the Degrees, Minutes, Seconds (DMS) representation of the GPS
           coordinate.

        Returns:
            str: The formatted DMS string.
        """
        dms = "{} degrees, {} minutes, {} seconds {}".format(
            self.degrees, self.minutes, round(self.seconds, 2),
            self.direction.name)
        return dms

    @property
    def is_longitude(self) -> bool:
        """Return True if the coordinate is a longitude (East/West), False
           otherwise."""
        return self.direction in [GPSDir.East, GPSDir.West]

    @property
    def decimal_value(self) -> float:
        """Return the decimal representation of the GPS coordinate."""
        return self._dec

    @property
    def gps_string(self) -> str:
        """Return the original GPS coordinate string."""
        return self._gps_str

    @gps_string.setter
    def gps_string(self, gps_str: Union[str, float]) -> None:
        """ Set the GPS coordinate string, ensuring it is positive and formatted
        correctly.

        This method will make sure the string is correctly formatted to NMEA
        0183 ddmm.ssss for latitude and dddmm.ssss for longitude by padding
        left and right with 0's if required before storing the value in the
        class variable.

        Note:
            If the coordinate string is set before direction, padding of
            the string will not occur until direction is set

        Args:
            gps_str (Union[str, float]): The GPS coordinate in string or float
            format.

        Raises:
            GPSOutOfBoundsError: If the GPS coordinate string is negative.
        """
        logging.debug("COORD: Setting gps string to %s", gps_str)
        if gps_str is None:
            self._gps_str = None
            return
        # Convert float to string if necessary
        if isinstance(gps_str, float):
            gps_str = f"{gps_str}"
        try:
            self._gps_str = gps_str
            self._pad_gps_string()
            if float(gps_str) < 0.0:
                logging.error(
                    "COORD: GPS coordinate string (%s) cannot be negative",
                    gps_str)
                raise GPSOutOfBoundsError(
                    f"GPS coordinate string ({gps_str}) cannot be negative")

        except ValueError:
            raise GPSOutOfBoundsError(
                f"GPS string [{gps_str}] cannot be converted to a number")

    def to_string(self) -> str:
        """String representation of the coordinate as deg, min, sec and
        decimal coordinate """
        return "{}: {}\t({})".format(self.lat_lng_str, self.deg_min_sec,
                                    round(self.decimal_value,4))

    def _pad_gps_string(self) -> None:
        """Pad a coordinate string with 0's to match NMEA 0183 format.

        This method formats a coordinate string to conform to NMEA 0183
        standards:
        - Latitude: ddmm.ssss
        - Longitude: dddmm.ssss

        It pads the string with 0's as needed. For example:
        - A longitude given as '123.123' will be padded to '00123.1230'.
        - A latitude given as '234.56' will be padded to '0234.5600'.

        Raises:
            ValueError: If the `gps_string` is not a numeric value or is negative.
            GPSOutOfBoundsError: If the integer part of the coordinate is too large.
        """
        logging.debug("COORD: gps_string=%s dir=%s", self.gps_string, self._dir)
        if self.gps_string is None or self._dir is None:
            return

        # Ensure the value is numeric and positive
        try:
            value = float(self.gps_string)
            if value < 0.0:
                raise NegativeValueError(
                    f"NMEA coordinate cannot be negative: {self.gps_string} "
                    "was given"
                )
        except ValueError:
            logging.error(
                "COORD: GPS coordinate %s is not numeric", self.gps_string)
            raise ValueError(f"{self.gps_string} is not numeric")

        # Split into [ddmm / dddmm] & [ssss]
        split_str = self.gps_string.split(".")
        req_int_len = 5 if self.is_longitude else 4
        if len(split_str[0]) > req_int_len:
            logging.error(
                    "COORD: GPS string %s is too long, should be: '%s'",
                    self.gps_string,
                    "dddmm.ssss" if self.is_longitude else "ddmm.ssss")
            raise GPSOutOfBoundsError(
                f"Coordinate is too big: {self.gps_string}")

        # Pad the integer part
        split_str[0] = split_str[0].zfill(req_int_len)

        # Pad the decimal part or create it if missing
        if len(split_str) == 1:
            split_str.append("0000")  # If no decimal part, add "0000"
        else:
            split_str[1] = split_str[1].ljust(4, "0")  # Pad the decimal part

        # Rejoin the string
        self._gps_str = ".".join(split_str)
        logging.debug("COORD: Padded GPS string is %s", self._gps_str)


    def _calc_coords(self) -> None:
        """Calculate and update the GPS coordinate values.

        This method calculates and updates both the degree-minute-second (DMS)
        representation and the decimal degree value of the GPS coordinate using
        the `_deg_min_sec()` and `_decimal()` methods. Calculations are
        performed only if the GPS string (`gps_string`) and direction
        (`direction`) properties are set.
        """
        if self.gps_string is None or self.direction is None:
            return
        self._deg_min_sec()
        self._decimal()
        logging.debug("COORD: %s coordinate is %s", self.lat_lng_str, self.decimal_value)

    def _deg_min_sec(self):
        """Convert the GPS coordinate string into degrees, minutes, and
           seconds."""
        if self._dir is None:
            return
        logging.debug("COORD: NMEA %s is %s", self.lat_lng_str, self._gps_str)
        self._deg = int(self.gps_string[:self._degree_len])
        self._min = float(self.gps_string[self._degree_len:])
        logging.debug("COORD: Coordinate is %s degrees, %s minutes, %s "
                      "seconds %s", self._deg, self.minutes,
                      round(self.seconds, 2), self.direction.value)

    def _decimal(self):
        """Convert the DMS (degrees, minutes, seconds) coordinate to decimal
           format and validate it."""
        self._dec = self._deg + (self._min / 60)
        if self.direction in [GPSDir.South, GPSDir.West]:
            self._dec = -self._dec
        logging.debug("COORD: Decimal coordinate calculated as %s", self._dec)
        if not self._validate_decimal(self._dec):
            self._dec = None

    def _validate_decimal(self, decimal_value: float) -> bool:
        """
        Validate that the decimal coordinate is within geographic bounds.

        Args:
            decimal_value (float): The decimal representation of the coordinate.

        Returns:
            bool: True if the coordinate is valid, False otherwise.

        Raises:
            GPSOutOfBoundsError: If the coordinate is out of bounds.
        """
        if (self.is_latitude and -90.0 <= decimal_value <= 90.0) or \
           (self.is_longitude and -180.0 <= decimal_value <= 180.0):
            logging.info("%s coordinate is %s, (%s decimal degrees)",
                         self.lat_lng_str, self.deg_min_sec, self.decimal_value)
            return True
        else:
            logging.error(
                "COORD: Decimal coordinate %s is out of bounds for %s",
                decimal_value, self.lat_lng_str)
            raise GPSOutOfBoundsError(
                f"Coordinate {decimal_value} is out of bounds "
                f"for {self.lat_lng_str}")