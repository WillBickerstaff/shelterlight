"""tests.util.

Common Utilities for tests
"""
import unittest
import logging
import os
import inspect
import time
import datetime


class LoggingTestResult(unittest.TextTestResult):
    """Custom test result class: logs test outcomes (success, failure, error).

    Inherits from unittest.TextTestResult and overrides methods to log results
    using the logging module.
    """

    def startTest(self, test):
        """Log the start of each test with a separator."""
        start_test_lines = [
            "\n", "="*79, f"\tRunning: {self.getDescription(test)}", "-"*79]
        start_test_block = "\n".join(start_test_lines)
        logging.info(start_test_block)
        # Flush logs to ensure they appear
        for handler in logging.getLogger().handlers:
            handler.flush()
        super().startTest(test)

    def addSuccess(self, test):
        """Log Test pass."""
        super().addSuccess(test)
        logging.info("\n%s\n\tPASS: %s", "-"*79, self.getDescription(test))
        # Flush logs to ensure they appear
        for handler in logging.getLogger().handlers:
            handler.flush()

    def addFailure(self, test, err):
        """Log test failure and traceback."""
        super().addFailure(test, err)
        logging.error("\n%s\n\tFAIL: %s\n%s", "-"*79,
                      self.getDescription(test),
                      self._exc_info_to_string(err, test))
        # Flush logs to ensure they appear
        for handler in logging.getLogger().handlers:
            handler.flush()

    def addError(self, test, err):
        """Log test error and traceback."""
        super().addError(test, err)
        logging.error("\n%s\n\tERROR: %s\n%s", "-"*79,
                      self.getDescription(test),
                      self._exc_info_to_string(err, test))
        # Flush logs to ensure they appear
        for handler in logging.getLogger().handlers:
            handler.flush()

    def printSummary(self, stream):
        """Log a clean summary block at the end."""
        summary_lines = [
            "\n", "=" * 79,
            "SUMMARY:",
            f"\tRan {self.testsRun} tests in {self._duration:.3f}s"]
        if not self.failures and not self.errors:
            summary_lines.append("\tRESULT: OK")
        else:
            summary_lines.append(f"\tRESULT: FAIL ({len(self.failures)} "
                                 "failures, {len(self.errors)} errors)")

        summary_lines.append("-" * 79)

        # Join and log the full block
        summary_block = "\n".join(summary_lines)
        logging.info(summary_block)
        # Flush logs to ensure they appear
        for handler in logging.getLogger().handlers:
            handler.flush()


class LoggingTestRunner(unittest.TextTestRunner):
    """Custom test runner that logs a test summary at the end."""

    def _makeResult(self):
        return LoggingTestResult(self.stream, self.descriptions,
                                 self.verbosity)

    def run(self, test):
        """Run the test suite and print a summary."""
        result = self._makeResult()
        start_time = time.time()

        test(result)

        result._duration = time.time() - start_time
        result.printErrors()
        result.printSummary(self.stream)

        for handler in logging.getLogger().handlers:
            handler.flush()

        return result


def setup_test_logging(name: str = None,
                       level: int = logging.DEBUG,
                       clear: bool = True) -> logging.Logger:
    """Set up consistent logging for test cases.

    Args
    ----
    name : str, optional
        Log filename inside 'tests' folder.
        If None, uses the calling test script's filename with `.log` extension.

    level : int
        Logging level to use. Defaults to logging.DEBUG.

    clear : bool
        If True (default), clears any existing content in the log file.
    """
    # Infer the calling test script's filename if not provided
    if name is None:
        frame = inspect.stack()[1]
        calling_file = os.path.basename(frame.filename)
        base_name, _ = os.path.splitext(calling_file)
        name = f"{base_name}.log"

    # Use the same directory as this file (tests/)
    log_dir = os.path.dirname(__file__)
    log_path = os.path.join(log_dir, name)

    # Clear the log file if requested
    if clear:
        with open(log_path, 'w'):
            pass  # Clears the log file

    # Only add the file handler if it's not already present
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            filename=log_path,
            level=level,
            format="[%(levelname)s] %(message)s"
        )
        logging.debug("%s UTC - Log initialized at:\n\t%s",
                      datetime.datetime.now(datetime.timezone.utc).strftime(
                          "%Y-%m-%d %H:%M:%S"), log_path)
    else:
        logging.debug("Logger already initialized.")
