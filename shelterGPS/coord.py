import logging
from typing import Optional, Union
from common import GPSDir, GPSOutOfBoundsError

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
        self._degree_len = 0
        if direction is not None:
            self.direction = direction
        if gps_string is not None:
            self.gps_string = gps_string

    @property
    def direction(self):
        """Get the direction of the coordinate."""
        return self._dir

    @property
    def lat_lng_str(self):
        """Return 'Latitude' if the coordinate is a latitude, 'Longitude'
           otherwise."""
        return "Latitude" if self.is_latitude else "Longitude"

    @direction.setter
    def direction(self, direction: GPSDir):
        """
        Set the direction of the coordinate and determine the degree length.

        Args:
            direction (GPSDir): The direction of the coordinate (N, S, E, W).

        Raises:
            ValueError: If the provided direction is not a valid GPSDir value.
        """
        if direction not in GPSDir:
            raise ValueError(f"Coordinate direction is invalid: {direction}")
        self._dir = direction
        self._degree_len = 3 if self.is_longitude else 2

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
        """Get the Degrees, Minutes, Seconds (DMS) representation of the GPS coordinate.

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
        """
        Set the GPS coordinate string, ensuring it is positive and formatted
        correctly.

        Args:
            gps_str (Union[str, float]): The GPS coordinate in string or float
            format.

        Raises:
            ValueError: If the GPS coordinate string is negative.
        """
        if float(gps_str) < 0.0:
            logging.error(
                "COORD: GPS coordinate string (%s) cannot be negative",
                gps_str)
            raise ValueError(
                f"GPS coordinate string ({gps_str}) cannot be negative")
        self._gps_str = str(gps_str).zfill(10) if self.is_longitude \
                   else str(gps_str).zfill(9)
        self._deg_min_sec()
        self._decimal()

    def _deg_min_sec(self):
        """Convert the GPS coordinate string into degrees, minutes, and
           seconds."""
        if self._dir is None:
            return
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