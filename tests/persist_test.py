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

    def test_json_storage(self):
        logging.getLogger().setLevel(logging.DEBUG)
        json_obj = PersistentData()
        json_obj.last_latitude = 10.5
        json_obj.last_longitude = -5.2
        s_time = dt.datetime.now()
        s_time = s_time + dt.timedelta(hours = -4)
        json_obj.add_sunrise_time(datetime_instance=s_time)
        s_time = dt.datetime.now()
        s_time = s_time + dt.timedelta(hours = +4)
        json_obj.add_sunset_time(datetime_instance=s_time)
        json_obj.store_data()

    def test_json_retrieval(self):
        json_obj = PersistentData()