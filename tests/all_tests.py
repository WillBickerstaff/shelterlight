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

# Clear screen
os.system('cls' if os.name == 'nt' else 'clear')

total = len(test_files)
print("-" * 79 + "\n" + f"Starting test suite... ({total} unit tests)" + "\n" +
      "-" * 79)

passed = 0
for i, path in enumerate(test_files, start=1):
    print(f"Running Test:\t{path}\t\t", end='', flush=True)
    result = subprocess.run(
        ["python", path],
        env={**os.environ, "PYTHONPATH": project_root},
        capture_output=True
    )
    if result.returncode != 0:
        print("FAILED -- Check the test log")
    else:
        passed += 1
        print("PASSED")

print("-"*79 + "\n" +
      f"Test suite complete: {passed} of {total} unit tests passed."
      + "\n" + "-" * 79)
