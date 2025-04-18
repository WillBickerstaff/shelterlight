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
import sys
python_exe = sys.executable # Make sure we use the venv Python

# Make sure project directories are in PATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
test_env = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join([
        project_root,
        os.path.join(project_root, "tests")  # ensure tests/ is on PYTHONPATH
    ])
}

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
# print(test_env)
for i, path in enumerate(test_files, start=1):
    print(f"Running Test:\t{path}\t\t", end='', flush=True)
    result = subprocess.run(
        [python_exe, path],
        env=test_env,
        cwd=project_root,  # ensure correct working directory
        capture_output=True,
        text=True           # auto-decode stdout/stderr
    )
    if result.returncode != 0:
        print("FAILED")
        print("---- STDOUT ----")
        print(result.stdout)
        print("---- STDERR ----")
        print(result.stderr)
    else:
        passed += 1
        print("PASSED")

print("-"*79 + "\n" +
      f"Test suite complete: {passed} of {total} unit tests passed."
      + "\n" + "-" * 79)
