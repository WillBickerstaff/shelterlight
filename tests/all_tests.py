"""tests.all_tests.py.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Run all tests
Author: Will Bickerstaff
Version: 0.1
"""

import subprocess
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
test_files = [
    "tests/activity_test.py",
    "tests/geocode_test.py",
    "tests/gps_test.py",
    "tests/helio_test.py",
    "tests/persist_test.py",
    "tests/schedule_test.py",
    "tests/usb_test.py",
]

for path in test_files:
    print(f"Running: {path}")
    subprocess.run(
        ["python", path],
        check=True,
        env={**os.environ, "PYTHONPATH": project_root}
    )
