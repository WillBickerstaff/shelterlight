import logging
import configparser
from typing import Optional

class ConfigNotLoaded(Exception):
    """Exception raised when the configuration fails to load or is canceled."""
    pass

class ConfigLoader:
    """Singleton-based configuration loader for managing system configurations.

    This class loads configurations from a specified file, validates structure
    and unique GPIO pin usage, and falls back to default values if a
    configuration file is invalid or unavailable.
    """

    _instance = None
    _FALLBACK_VALUES = {
        "GENERAL": {
            "log_level": {"value": "INFO", "is_pin": False},
            "log_file": {"value": "shelterlight.log", "is_pin": False},
            "cycle_time": {"value": 300, "is_pin": False},
            "cancel_input": {"value": 5, "is_pin": True },
            "confirm_input": {"value": 6, "is_pin": True }
        },
        "GPS": {
            "serial_port": {"value": "/dev/serial0", "is_pin": False},
            "baudrate": {"value": 9600, "is_pin": False},
            "timeout": {"value": 0.5, "is_pin": False},
            "pwr_pin": {"value": 4, "is_pin": True},
            "pwr_up_time": {"value": 2.0, "is_pin": False},
            "fix_retry_interval": {"value": 600.0, "is_pin": False},
            "max_fix_time": {"value": 120.0, "is_pin": False},
            "failed_fix_days": {"value": 14, "is_pin": False},
        },
        "IO": {
            "activity_digital_inputs": {"value": "17", "is_pin": True,
                               "accepts_list": True},
            "max_activity_time": {"value": 1800, "is_pin": False},
            "health_check_interval": {"value": 300, "is_pin": False},
            "lights_output": {"value": 16, "is_pin": True,
                               "accepts_list": True},
            "fault_output": {"value": 15, "is_pin": True},
            "crit_fault_out": {"value": 14, "is_pin": True},
        },
        "FIX_WINDOW": {
            "sunrise_offset": {"value": 3600, "is_pin": False},
            "sunset_offset": {"value": -1800, "is_pin": False},
        },
        "DATA_STORE": {
            "media_mount_point": {"value": "/media", "is_pin": False},
            "persistent_data_JSON": {"value": "persist.json", "is_pin": False},
        },
        "ACTIVITY_DB": {
        "host": {"value": "localhost", "is_pin": False},
        "port": {"value": 5432, "is_pin": False},
        "database": {"value": "activity_db", "is_pin": False},
        "user": {"value": "db_user", "is_pin": False},
        "password": {"value": "019smartlight283", "is_pin": False},
        "connect_retry": {"value": 5, "is_pin": False },
        "connect_retry_delay": {"value": 2, "is_pin": False}
        }
    }

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of ConfigLoader is created.

        This method implements the Singleton pattern for the `ConfigLoader`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns:
            ConfigLoader: A single instance of the `ConfigLoader` class.
        """
        if cls._instance is None:
            # Create and assign a new instance if it hasn't been created yet
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            # Track initialization status with a private attribute
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, config_path: str = "config.ini"):
        """Initialize ConfigLoader with configuration file path.

        This constructor sets up the `ConfigLoader` by assigning the provided
        configuration file path and preparing the `config` parser.
        Initialization is controlled by the `__initialized` flag to avoid
        redundant setup.

        Args:
            config_path (str): Path to the primary configuration file. Defaults
                            to "config.ini".
        """
        if not self.__initialized:
            # Assign the provided configuration path
            self.config_path = config_path
            # Initialize the ConfigParser instance
            self.config = configparser.ConfigParser()
            # Flag for tracking if the loaded config is valid
            self._valid_config = False
            # Attempt to load and validate the configuration file
            self.load_config()
            # Mark initialization as complete to prevent re-running setup
            self.__initialized = True

    @property
    def valid_config(self) -> bool:
        """bool: Indicates if the current configuration is valid."""
        return self._valid_config

    @property
    def max_activity_time(self) -> int:
        """Max time any activity detection can remain high before a fault
        should be generated"""
        return self.get_config_value(self.config, "IO","max_activity_time")

    @property
    def health_check_interval(self) -> int:
        """How often inputs are checked to see if they are stuck"""
        return self.get_config_value(self.config, "IO","health_check_interval")

    @property
    def cancel_input(self) -> int:
        """Pin used for responding to system messages."""
        return self.get_config_value(self.config, "GENERAL", "cancel_input")

    @property
    def confirm_input(self) -> int:
        """Pin used for responding to system messages."""
        return self.get_config_value(self.config, "GENERAL", "confirm_input")

    @property
    def log_file(self) -> str:
        """str: Path to the log file."""
        return self.get_config_value(self.config, "GENERAL", "log_file")

    @property
    def valid_config(self) -> bool:
        """bool: Indicates if the current configuration is valid."""
        return self._valid_config

    @property
    def log_file(self) -> str:
        """str: Path to the log file."""
        return self.get_config_value(
            self.config, "GENERAL", "log_file")

    @property
    def log_level(self) -> str:
        """str: Logging level."""
        return self.get_config_value(
            self.config, "GENERAL", "log_level"),

    @property
    def cycle_time(self) -> int:
        """int: System cycle time in seconds."""
        return self.get_config_value(
            self.config, "GENERAL", "cycle_time")

    @property
    def gps_serial_port(self) -> str:
        """str: Serial port used for GPS communication."""
        return self.get_config_value(
            self.config, "GPS", "serial_port")

    @property
    def gps_baudrate(self) -> int:
        """int: Baud rate for GPS communication."""
        return self.get_config_value(
            self.config, "GPS", "baudrate")

    @property
    def gps_timeout(self) -> float:
        """float: Timeout for GPS communication."""
        return self.get_config_value(
            self.config, "GPS", "timeout")

    @property
    def gps_pwr_pin(self) -> int:
        """int: GPIO pin number used to power the GPS module."""
        return self.get_config_value(
            self.config, "GPS", "pwr_pin")

    @property
    def gps_pwr_up_time(self) -> float:
        """float: Time in seconds to wait after powering up GPS."""
        return self.get_config_value(
            self.config, "GPS", "pwr_up_time")

    @property
    def gps_fix_retry_interval(self) -> float:
        """float: Interval in seconds between GPS fix retries."""
        return self.get_config_value(
            self.config, "GPS", "fix_retry_interval")

    @property
    def gps_max_fix_time(self) -> float:
        """float: Maximum time in seconds for a GPS fix attempt."""
        return self.get_config_value(
            self.config, "GPS", "max_fix_time")

    @property
    def gps_failed_fix_days(self) -> int:
        """int: Number of days after which a GPS fix failure triggers an
           alarm."""
        return self.get_config_value(
            self.config, "GPS", "failed_fix_days")

    @property
    def activity_digital_inputs(self) -> list:
        """list of int: GPIO pins for sensor inputs."""
        return self.get_config_value(
            self.config, "IO", "sensor_inputs")

    @property
    def lights_output(self) -> int:
        """int: GPIO pin for lights output."""
        return self.get_config_value(
            self.config, "IO", "lights_output")

    @property
    def fault_output(self) -> int:
        """int: GPIO pin for fault output."""
        return self.get_config_value(
            self.config, "IO", "fault_output")

    @property
    def crit_fault_out(self) -> int:
        """int: GPIO pin for critical fault output."""
        return self.get_config_value(
            self.config, "IO", "crit_fault_out")

    @property
    def sunrise_offset(self) -> int:
        """int: Offset from sunrise in seconds for GPS fixing window."""
        return self.get_config_value(
            self.config, "FIX_WINDOW", "sunrise_offset")

    @property
    def sunset_offset(self) -> int:
        """int: Offset from sunset in seconds for GPS fixing window."""
        return self.get_config_value(
            self.config, "FIX_WINDOW", "sunset_offset")

    @property
    def media_mount_point(self) -> str:
        """str: Mount point of attached USB drives."""
        return self.get_config_value(
            self.config, "DATA_STORE", "media_mount_point")

    @property
    def persistent_data_json(self) -> str:
        """str: Path to persistent JSON data file."""
        return self.get_config_value(
            self.config, "DATA_STORE", "persistent_data_JSON")

    def load_config(self) -> None:
        """Load and validate configuration values or fall back to defaults.

        This method attempts to load the configuration file specified by
        `config_path`. If validation fails, it reverts to predefined fallback
        values. If loading fails due to file or parsing errors, it raises a
        `ConfigNotLoaded` exception.

        Raises:
            ConfigNotLoaded: If the configuration file cannot be loaded or
                             parsed.
        """
        try:
            # Attempt to load and validate the configuration file
            if not self.__validate_and_load(self.config_path):
                logging.warning("Invalid configuration, using fallback values.")
                # Load fallback configuration if validation fails
                self.config.read_dict(self._FALLBACK_VALUES)
            else:
                # Mark the configuration as valid upon successful loading and
                # validation
                self._valid_config = True
        except (FileNotFoundError, configparser.Error) as e:
        # Log the error and raise an exception if loading fails
                logging.error("Failed to load configuration file: %s", e)
                raise ConfigNotLoaded("Configuration could not be loaded.")

    def validate_config_file(self, file_path: str) -> bool:
        """Validate a given config file at the specified path without modifying
           the singleton's main configuration.

        This method loads the configuration file located at `file_path` into a
        temporary `ConfigParser` instance to verify its structure and contents.
        It does not alter the main configuration held by the singleton instance,
        making it suitable for testing external configurations (e.g., USB-based
        configs) before committing to their use in the application.

        Args:
            file_path (str): Path to the configuration file to validate. The
                            file should contain expected sections and options
                            for successful validation.

        Returns:
            bool:
                - True if the configuration file has a valid structure and
                       unique GPIO pin definitions.
                - False if any structural or parsing issues are detected.

        Example:
            To check if an external configuration file is valid before using it:

            ```python
            config_loader = ConfigLoader()
            if config_loader.validate_config_file("/usb/smartlightconfig.ini"):
                # Safe to proceed with the USB configuration
            ```
        """
        # Initialize a temporary ConfigParser instance to load the file content
        temp_config = configparser.ConfigParser()
        try:
            # Attempt to read and load the configuration file into temp_config
            temp_config.read(file_path)

            # Validate configuration structure and GPIO uniqueness using private
            # methods to avoid altering the main configuration state
            if self.__validate_config_structure(temp_config) and \
            self.__validate_unique_pins(temp_config):
                logging.info("Temporary config file at %s is valid.", file_path)
                return True  # File is valid if it meets structural expectations
            else:
                logging.warning("Temporary config file at %s is invalid.",
                                file_path)
                return False  # File is invalid if structure or pins
                              # assignments do not meet expectations

        except configparser.Error as e:
            # Log any errors encountered during parsing and return False to
            # indicate invalid config
            logging.error(
                "Error parsing temporary config file %s: %s", file_path, e)
            return False

    def _get_fallback_value(self, section: str, option: str):
        """Retrieve the fallback value for a specific section and option.

        This method extracts the default value for a specified section and
        option from `_FALLBACK_VALUES`. It is primarily used to supply default
        values for configuration options that are either missing or invalid.

        Args:
            section (str): The section name in `_FALLBACK_VALUES`, such as
            "GPS" or "GENERAL". option (str): The specific option name within
            the section, such as "log_file".

        Returns:
            The fallback value for the specified section and option, if defined;
            otherwise, None.
        """
        # Access fallback values dictionary, ensuring both section and option
        # keys exist, and return the "value" entry for the option.
        return self._FALLBACK_VALUES.get(
            section, {}).get(option, {}).get("value")

    def get_config_value(self, config, section, option,
                        value_type: Optional[type] = None):
        """Retrieve a configuration value, using fallback values and type
           inference.

        This method retrieves a configuration value from a given section and
        option, defaulting to fallback values if necessary. The method
        determines the appropriate type based on either a specified
        `value_type` or inferred from the fallback value. If the option is
        marked as accepting a list, the method parses the configuration value
        accordingly.

        Args:
            config (ConfigParser): The configuration parser instance containing
                                   the loaded configuration.
            section (str): The configuration section, such as "GPS" or
                           "GENERAL".
            option (str): The option name within the section, such as
                          "baudrate".
            value_type (Optional[type]): Specifies the desired type for the
                                        retrieved value, such as `int` or
                                        `float`. If `None`, the type is inferred
                                        from the fallback value.

        Returns:
            The configuration value, cast to the appropriate type (or parsed as
            a list if marked `accepts_list`). If the option is missing or
            invalid, the fallback value is returned.

        """
        # Retrieve fallback value and determine the inferred type for the option
        default_value = self._get_fallback_value(section, option)
        inferred_type = value_type if value_type else type(default_value)

        # Determine if the option accepts a list by checking the fallback
        # structure
        accepts_list = self._FALLBACK_VALUES.get(
            section, {}).get(option, {}).get("accepts_list", False)

        try:
            # Retrieve and cast the value based on its expected type or
            # structure
            if inferred_type == int:
                return config.getint(section, option, fallback=default_value)
            elif inferred_type == float:
                return config.getfloat(section, option, fallback=default_value)
            elif accepts_list:
                # Handle list parsing if the option is marked as `accepts_list`
                item_type = float if any(isinstance(d, float) \
                                  for d in [default_value]) else int
                return [item_type(pin.strip())
                        for pin in config.get(section, option,
                                fallback=str(default_value)).split(",")
                        if pin.strip()]
            # Default to returning the value as a string if no other type is
            # specified
            return config.get(section, option, fallback=default_value)

        except (configparser.NoSectionError,
                configparser.NoOptionError,
                ValueError) as e:
            # Log and return the fallback if retrieval or parsing fails
            logging.warning("Defaulting for missing or invalid config "
                            "%s.%s: %s", section, option, e)
            return default_value

    def __validate_and_load(self, file_path: str) -> bool:
        """Load and validate the configuration file.

        This method attempts to read the configuration from the specified file
        path. It verifies that the configuration structure includes all
        required sections and that GPIO pins are uniquely assigned across
        configuration items.

        Args:
            file_path (str): Path to the configuration file to be loaded.

        Returns:
            bool: True if the configuration is successfully loaded and passes
                  all validation checks, False otherwise.

        Raises:
            configparser.Error: Raised if an error occurs during file parsing.
        """
        # Initialize a ConfigParser instance to read the file
        config = configparser.ConfigParser()
        try:
            # Attempt to read the configuration file
            config.read(file_path)
            logging.info("Loaded configuration from %s", file_path)

            # Validate configuration structure and GPIO pin assignments
            if not self.__validate_config_structure(config):
                return False
            if not self.__validate_unique_pins(config):
                return False

            # If all checks pass, assign the validated config to the instance
            self.config = config
            return True
        except configparser.Error as e:
            logging.error(
                "Configuration parsing error for %s: %s", file_path, e)
            return False

    def __validate_config_structure(self,
                                    config: configparser.ConfigParser) -> bool:
        """Ensure all required sections are present and log any empty sections.

        This method checks that the configuration contains all required sections
        as defined in `_FALLBACK_VALUES`. If a required section is missing,
        it logs an error and returns False. If a section is present but contains
        no values, it logs a warning but still considers the structure valid.

        Args:
            config (configparser.ConfigParser): The configuration parser
                                instance containing the loaded configuration.

        Returns:
            bool: True if all required sections are present, False if any
                  required sections are missing.
        """
        # Retrieve required sections from fallback values
        required_sections = self._FALLBACK_VALUES.keys()
        for section in required_sections:
            # Check if each required section exists in the loaded config
            if section not in config:
                logging.error("Missing required section: %s", section)
                return False
            # Log a warning if the section exists but is empty
            elif not config.items(section):
                logging.warning("Section %s is empty.", section)
        return True

    def __validate_unique_pins(self, config: configparser.ConfigParser) -> bool:
        """Ensure each GPIO pin is defined only once across the configuration.

        This method iterates through all configuration items marked with the
        'is_pin' flag in `_FALLBACK_VALUES`, retrieving the pin values and
        checking for duplicates across the configuration. If any pin is defined
        multiple times, it logs an error and returns False.

        Args:
            config (configparser.ConfigParser): The configuration parser
                                instance containing the loaded configuration.

        Returns:
            bool: True if all pins are uniquely defined, False if any pin is
                  assigned more than once.
        """
        pins_used = set()
        for section, options in self._FALLBACK_VALUES.items():
            # Check only sections present in the configuration
            if section in config:
                for key, details in options.items():
                    # Process items marked as GPIO pins
                    if details.get("is_pin"):
                        # Retrieve the pin(s) from the config as a list
                        pins = self.get_config_value(
                            config, section, key, list)
                        for pin in pins:
                            # Check for duplicate pin assignments
                            if pin in pins_used:
                                logging.error(
                                    "Pin %d is defined multiple times.", pin)
                                return False
                            pins_used.add(pin)
        return True