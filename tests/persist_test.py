"""tests.persist_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit Testing for persistent data
Author: Will Bickerstaff
Version: 0.1
"""

from lightlib.persist import PersistentData
from unittest.mock import MagicMock
import unittest
import datetime as dt
import sys
import os
import logging

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)
parent_path = os.path.abspath(os.path.join(base_path, '..'))
sys.path.append(base_path)
sys.path.append(parent_path)

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed


class TestPersist(unittest.TestCase):
    """Testing persistent data."""

    def setUp(self):
        """Begin setup for each test."""
        self.default_loglevel = logging.WARN
        logging.basicConfig(level=self.default_loglevel)

    def test_singleton_behaviour(self):
        """Confirm class behaves as a singleton."""
        p1 = PersistentData()
        p2 = PersistentData()
        self.assertIs(p1, p2)

    def test_json_storage(self):
        """Check JSON data storage."""
        logging.getLogger().setLevel(logging.DEBUG)

        PersistentData().current_latitude = 10.6
        PersistentData().current_longitude = -5.2
        s_time = dt.datetime.now(tz=dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours=-4)
        PersistentData().add_sunrise_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz=dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours=+4)
        PersistentData().add_sunset_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz=dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours=-4, minutes=3, days=1)
        PersistentData().add_sunrise_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz=dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours=4, minutes=-4, days=1)
        PersistentData().add_sunset_time(datetime_instance=s_time)
        PersistentData().store_data()
        logging.getLogger().setLevel(self.default_loglevel)

    def test_json_retrieval(self):
        """Check JSON data retrieval."""
        logging.getLogger().setLevel(logging.DEBUG)
        # self.assertEqual(PersistentData().last_latitude,10.5)
        PersistentData()._populate_locals_from_file()
