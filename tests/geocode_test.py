"""tests.geocode_test.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Unit testing geocode
Author: Will Bickerstaff
Version: 0.1
"""

from unittest.mock import MagicMock

import sys
import os
import logging
import unittest

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_path)
parent_path = os.path.abspath(os.path.join(base_path, '..'))
sys.path.append(base_path)
sys.path.append(parent_path)

from geocode.local import Location

if 'RPi' not in sys.modules:
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()
    sys.modules['serial'] = MagicMock()  # Also mock serial if needed


class test_geocode(unittest.TestCase):
    """Test the geocode class."""

    def setUp(self):
        """Log level setup."""
        self.default_loglevel = logging.DEBUG
        logfilename = 'geocode_tests.log'
        with open(logfilename, 'w'):
            pass
        logging.basicConfig(level=self.default_loglevel,
                            filename=os.path.join('tests', logfilename))

    def test_retrieval(self):
        """Test retrievel of locations."""
        logging.getLogger().setLevel(logging.DEBUG)
        loc = Location()
        logging.getLogger().setLevel(self.default_loglevel)
