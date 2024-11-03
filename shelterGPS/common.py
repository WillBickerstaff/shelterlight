from enum import Enum

class GPSDir(Enum):
    """Enumeration for cardinal directions in GPS coordinates."""
    North = 'N'
    South = 'S'
    East = 'E'
    West = 'W'


class GPSInvalid(Exception):
    """Exception raised when a valid GPS fix cannot be obtained."""
    pass


class GPSNoFix(Exception):
    """Exception raised when no GPS fix is possible after multiple attempts."""
    pass


class GPSOutOfBoundsError(Exception):
    """Exception raised when GPS coordinates are out of bounds."""
    pass