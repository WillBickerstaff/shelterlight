from enum import Enum

class GPSDir(Enum):
    """Enumeration for cardinal directions in GPS coordinates."""
    North = 'N'
    N = 'N'
    South = 'S'
    S = 'S'
    East = 'E'
    E = 'E'
    West = 'W'
    W = 'W'

class GPSInvalid(Exception):
    """Exception raised when a valid GPS fix cannot be obtained."""
    pass

class GPSNoFix(Exception):
    """Exception raised when no GPS fix is possible after multiple attempts."""
    pass

class GPSOutOfBoundsError(Exception):
    """Exception raised when GPS coordinates are out of bounds."""
    pass
class NegativeValueError(ValueError):
    """Raised when the GPS coordinate value is negative."""
    pass