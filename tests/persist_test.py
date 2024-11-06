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

from lightlib.persist import GPSDataStore

import gps_test_vals as test_vals

class TestGPS(unittest.TestCase):

    def setUp(self):
        """Setup for each test, ensuring singleton reset for GPS."""
        GPS._instance = None  # Reset singleton instance
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)