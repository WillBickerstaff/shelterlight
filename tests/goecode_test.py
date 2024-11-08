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

from geocode.local import Location

class test_geocode(unittest.TestCase):
    def setUp(self):
        self.default_loglevel = logging.INFO
        logging.basicConfig(level=self.default_loglevel)

    def test_retrieval(self):
        logging.getLogger().setLevel(logging.DEBUG)
        loc = Location()
        logging.getLogger().setLevel(self.default_loglevel)
