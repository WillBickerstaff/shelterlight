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

lines = []
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
print("-"*79)
for path in test_files:
    print(f"Running: {path}")
    result = subprocess.run(
        ["python", path],
        env={**os.environ, "PYTHONPATH": project_root},
        capture_output=True
    )

    if result.returncode != 0:
        lines.append(f"{path}\t\tFAILED - check the log")
    else:
        lines.append(f"{path}\t\tPASSED")

# Print results summary
print("-"*79 + "\n" + "\n".join(lines) + "\n" + "-"*79)
