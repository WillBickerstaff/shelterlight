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

from lightlib.persist import PersistentData
from lightlib.common import strfdt

import gps_test_vals as test_vals

class TestPersist(unittest.TestCase):

    def setUp(self):
        self.default_loglevel = logging.WARN
        logging.basicConfig(level=self.default_loglevel)


    def test_singleton_behaviour(self):
        p1=PersistentData()
        p2=PersistentData()
        self.assertIs(p1,p2)

    def test_json_storage(self):
        logging.getLogger().setLevel(logging.DEBUG)

        PersistentData().current_latitude = 10.6
        PersistentData().current_longitude = -5.2
        s_time = dt.datetime.now(tz = dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours = -4)
        PersistentData().add_sunrise_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz = dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours = +4)
        PersistentData().add_sunset_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz = dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours = -4, minutes = 3, days = 1)
        PersistentData().add_sunrise_time(datetime_instance=s_time)
        s_time = dt.datetime.now(tz = dt.timezone.utc)
        s_time = s_time + dt.timedelta(hours = 4,minutes = -4, days = 1)
        PersistentData().add_sunset_time(datetime_instance=s_time)
        PersistentData().store_data()
        logging.getLogger().setLevel(self.default_loglevel)

    def test_json_retrieval(self):
        logging.getLogger().setLevel(logging.DEBUG)
       # self.assertEqual(PersistentData().last_latitude,10.5)
        PersistentData()._populate_locals_from_file()