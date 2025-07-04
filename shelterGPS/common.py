"""shelterGPS.common.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: GPS Common methods
Author: Will Bickerstaff
Version: 0.1
"""

from enum import Enum


class SolarEvent(Enum):
    """Enumeration of key solar events for sun position calculations."""

    SUNRISE = "sunrise"
    SUNSET = "sunset"
    NOON = "noon"
    DAWN = "dawn"
    DUSK = "dusk"


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


class NoSolarEventError(Exception):
    """Raised when sunrise or sunset can't be determined (polar day/night)."""

    pass


class InvalidObserverError(Exception):
    """Raised when observer is invalid (bad location, date, or corrupt)."""

    pass
