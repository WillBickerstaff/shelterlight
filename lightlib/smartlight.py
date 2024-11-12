import logging
import time
import sys
import inspect
from enum import Enum
from typing import Optional
from RPi import GPIO
from lightlib.config import ConfigLoader

class GPIO_PIN_STATE(Enum):
        ON = True
        OFF = False
        HIGH = True
        LOW = False

class CANCEL_CONFIRM(Enum):
    CANCEL = False
    CONFIRM = True

import inspect
import logging

def get_caller_info():
    """Get the names of the two previous calling functions and the arguments
    of the most recent call, excluding `log_caller` if present.

    This function uses the inspect module to analyze the call stack and
    extracts the names of the two functions preceding the current call.
    If `log_caller` is found in the stack, it will be excluded, and the
    next two functions will be considered. It formats these names as a
    '>>' separated string to indicate the call chain and retrieves the
    local variables (arguments) of the most recent caller.

    Returns:
        tuple: A tuple containing:
            - str: A '>>' string representing the names of the two
                   previous calling functions, excluding `log_caller`.
            - dict: A dictionary of local variables from the most recent
                    caller.
    """
    stack = inspect.stack()

    # Ensure the stack has sufficient depth
    if len(stack) < 3:
        return "Insufficient stack depth", {}

    # Initialize indices to skip `log_caller` if present
    index = 1  # Start from 1 because 0 is the current frame (get_caller_info)
    if stack[index].function == "log_caller":
        index += 1  # Skip `log_caller` if it's the current function

    if len(stack) <= index + 1:
        return "Insufficient stack depth", {}

    # Get the two previous frames
    first_caller_frame = stack[index + 1]
    second_caller_frame = stack[index]

    # Extract function names from the frames
    first_caller_function = first_caller_frame.function
    second_caller_function = second_caller_frame.function

    # Combine them into a '>>' separated string
    caller_function = f"{first_caller_function} >> {second_caller_function}"

    # Get the arguments (locals) from the most recent caller
    caller_locals = second_caller_frame.frame.f_locals

    return caller_function, caller_locals

def log_caller(loglevel: int = logging.ERROR, module: str = None) -> None:
    """Log information about the calling functions and their arguments.

    Args:
        loglevel (int): The logging level, such as logging.ERROR or logging.INFO.
        module (str, optional): Additional module information to include in the log.

    Returns:
        None
    """
    # Get the stack message from get_caller_info
    stack_message, caller_args = get_caller_info()

    module = f"{module}: " if module is not None else ""

    # Use the logging module to log the message at the specified log level
    logging.log(loglevel, f"{module}Called by:")
    logging.log(loglevel, f"{module}  {stack_message} with args:")
    for key, value in caller_args.items():
        logging.log(loglevel,f"{module}    {key}: {value}")


def set_power_pin(pin_number: int, state: GPIO_PIN_STATE,
                    wait_after: Optional[float] = None) -> None:
    """Set the GPIO power state by enabling or disabling the power pin.

    Args:
        pin_number (int): The GPIO pin number to control.
        state (GPIO_PIN_STATE): Desired power state; GPIO_PIN_STATE.ON to
                                power on, GPIO_PIN_STATE.OFF to power off.
        wait_after (Optional[float]): Optional delay after changing the
                                        power state in seconds.

    Raises:
        RuntimeError: If GPIO interaction fails, possibly due to permission
                        issues, incorrect setup, or conflicts.
    """
    # Default the wait time to 0 if not provided
    wait_after = wait_after or 0

    try:
        # Set up the pin as an output
        GPIO.setup(pin_number, GPIO.OUT)
        # Only change the state if it's different from the current state
        if GPIO.input(pin_number) != state.value:
            GPIO.output(pin_number, state.value)
            action = "powered ON" if state == GPIO_PIN_STATE.ON \
                                    else "powered OFF"
            logging.info("Pin %s %s, waiting %s seconds", pin_number,
                            action, wait_after)
            time.sleep(wait_after)

    except RuntimeError as e:
        action = "power ON" if state == GPIO_PIN_STATE.ON else "power OFF"
        logging.error(
            "Failed to set pin %s to %s: %s", pin_number, action, e
        )
        raise RuntimeError(
            "Failed to %s pin %s due to GPIO error." % (action, pin_number)
        ) from e

def init_log(log_level: Optional[str] = None):
    """Initialize the logging configuration with specified or default
        settings.

    This method configures the logging system based on the provided log
    level. If `log_level` is not provided or is invalid, it falls back to
    the level specified in the configuration file or defaults to 'INFO'.

    The logging output is directed to the file path specified by
    `ConfigLoader().log_file`, which is managed as part of the application's
    configuration. The log format includes the timestamp, log level name,
    and the log message.

    Args:
        log_level (Optional[str]): Desired logging level as a string (e.g.,
                                'DEBUG', 'INFO'). If not provided or
                                invalid, it defaults to the configured
                                level or 'INFO'.

    Example:
        ```python
        SmartLightingControl.init_log("DEBUG")
        ```

    Notes:
        - This method does not raise an exception if `log_level` is invalid.
        Instead, it logs a warning message and falls back to 'INFO'.
        - This method only sets up logging if no existing logging
        configuration is detected (i.e., it avoids reconfiguring if
        handlers are already set).
    """
    # Ensure logging is not configured multiple times
    if not logging.getLogger().hasHandlers():
        # Use provided log level or fetch from config if not specified
        log_level = log_level or ConfigLoader().log_level
        # Determine the logging level or default to INFO if invalid
        level = getattr(logging, log_level.upper(), logging.INFO)

        # Log a warning if an unrecognized log level is provided and
        # fallback to INFO
        if level == logging.INFO and log_level.upper() != "INFO":
            logging.warning("Invalid log level '%s' provided, defaulting "
                            "to INFO.", log_level)

        # Set up the logging configuration with specified format and file
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            filename=ConfigLoader().log_file
        )

        logging.info("Logging initialized with level %s.",
                        log_level.upper())

def warn_and_wait(message: str, wait_time: int = 5,
                  default_action: CANCEL_CONFIRM = CANCEL_CONFIRM.CONFIRM,
                  cancel_pin: Optional[int] = None,
                  confirm_pin: Optional[int] = None) -> CANCEL_CONFIRM:
    """Warn the user with a countdown and allow for cancellation or confirmation.

    Args:
        message (str): The warning message displayed to the user.
        wait_time (int): Time in seconds for the countdown.
        cancel_or_confirm (CANCEL_CONFIRM): The default return if no input
                                             is received (CANCEL or CONFIRM).
        cancel_pin (Optional[int]): GPIO pin for cancel input.
        confirm_pin (Optional[int]): GPIO pin for confirm input.

    Returns:
        CANCEL_CONFIRM: The result based on user input or the default
                        (`cancel_or_confirm`).
    """
    # Use default pins if not provided
    cancel_pin = cancel_pin or ConfigLoader().cancel_input
    confirm_pin = confirm_pin or ConfigLoader().confirm_input

    # Set up GPIOs for user input
    GPIO.setup(cancel_pin, GPIO.IN)
    GPIO.setup(confirm_pin, GPIO.IN)

    print(message)
    for remaining in range(wait_time, 0, -1):
        # Display the countdown on the TTY line
        sys.stdout.write(
            f"\r{message} in {remaining} seconds... Press to cancel/confirm.")
        sys.stdout.flush()

        # Check for GPIO input to cancel
        if GPIO.input(cancel_pin) == GPIO.HIGH:
            print("\nCanceled by user.")
            logging.info(f"{message} canceled by user.")
            return CANCEL_CONFIRM.CANCEL

        # Check for GPIO input to confirm
        if GPIO.input(confirm_pin) == GPIO.HIGH:
            print("\nConfirmed by user.")
            logging.info(f"{message} confirmed by user.")
            return CANCEL_CONFIRM.CONFIRM

        # Wait for 1 second before the next countdown iteration
        time.sleep(1)

    # Return the default based on `cancel_or_confirm` if no user input
    print("\nNo input received, proceeding.")
    logging.info(f"{message} - proceeding with default: {default_action.name}.")
    return default_action