"""lightlib.lightcontrol.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Control the light outputs, generate schedules & monitor activity.
Author: Will Bickerstaff
Version: 0.1
"""

from RPi import GPIO
from lightlib.activitydb import Activity
from scheduler.Schedule import LightScheduler


class LightController:
    """Manage light on status, activity recording and schedule generation."""

    def __init__(self):
        self.schedule = LightScheduler()
        self.activity_monitor = Activity()

    def turn_on(self):
        """Turn on lights if scheduler or activity monitor demand them."""

    def turn_off(self):
        """Turn off lights if there is no schedule AND no current activity."""

    def cleanup(self):
        """Cleanup GPIO resources."""
