"""lightlib.config.

Copyright (c) 2025 Will Bickerstaff
Licensed under the MIT License.
See LICENSE file in the root directory of this project.

Description: Locate & parse a configuration file
Author: Will Bickerstaff
Version: 0.1
"""

import logging
import configparser


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
        # ------------------------------------------------------------#
        "GENERAL": {
            "log_level":                {"value": "INFO",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "log_file":                 {"value": "shelterlight.log",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "cycle_time":               {"value": 300,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "cancel_input":             {"value": 5,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": False},

            "confirm_input":            {"value": 6,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": False},
            "sync_system_time":         {"value": True,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False},
        },
        # ------------------------------------------------------------#
        "LOCATION": {
            "ISO_country2":              {"value": "GB",
                                          "type": str,
                                          "is_pin": False,
                                          "accepts_list": False},

            "place_name":                {"value": "London",
                                          "type": str,
                                          "is_pin": False,
                                          "accepts_list": False},
        },
        # ------------------------------------------------------------#
        "GPS": {
            "serial_port":              {"value": "/dev/serial0",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "baudrate":                 {"value": 9600,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "timeout":                  {"value": 0.5,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "pwr_pin":                  {"value": 4,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": False},

            "pwr_up_time":              {"value": 2.0,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "fix_retry_interval":       {"value": 600.0,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "max_fix_time":             {"value": 120.0,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "failed_fix_days":          {"value": 14,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},
        },
        # ------------------------------------------------------------#
        "IO": {
            "activity_digital_inputs":  {"value": 17,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": True},

            "max_activity_time":        {"value": 1800,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "health_check_interval":    {"value": 300,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "lights_output":            {"value": 16,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": True},

            "fault_output":             {"value": 15,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": False},

            "crit_fault_out":           {"value": 14,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": False},
        },
        # ------------------------------------------------------------#
        "FIX_WINDOW": {
            "sunrise_offset":           {"value": 3600,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "sunset_offset":            {"value": -1800,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},
        },
        "DATA_STORE": {
            "media_mount_point":        {"value": "/media",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "persistent_data_JSON":     {"value": "persist.json",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},
        },
        # ------------------------------------------------------------#
        "ACTIVITY_DB": {
            "host":                     {"value": "localhost",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "port":                     {"value": 5432,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "database":                 {"value": "activity_db",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "user":                     {"value": "pi",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "password":                 {"value": "pi",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "connect_retry":            {"value": 5,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "connect_retry_delay":      {"value": 2,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False}
        }
    }

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance of ConfigLoader is created.

        This method implements the Singleton pattern for the `ConfigLoader`
        class, ensuring that only one instance of the class can exist at any
        time.

        Returns
        -------
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

        Args
        ----
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
        """Max time activity can be high before fault is generated."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="max_activity_time")

    @property
    def health_check_interval(self) -> int:
        """How often inputs are checked to see if they are stuck."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="health_check_interval")

    @property
    def cancel_input(self) -> int:
        """Pin used for responding to system messages."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="cancel_input")

    @property
    def confirm_input(self) -> int:
        """Pin used for responding to system messages."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="confirm_input")

    @property
    def log_file(self) -> str:
        """str: Path to the log file."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="log_file")

    @property
    def log_level(self) -> str:
        """str: Logging level."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="log_level")

    @property
    def cycle_time(self) -> int:
        """int: System cycle time in seconds."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="cycle_time")

    @property
    def gps_serial_port(self) -> str:
        """str: Serial port used for GPS communication."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="serial_port")

    @property
    def gps_baudrate(self) -> int:
        """int: Baud rate for GPS communication."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="baudrate")

    @property
    def gps_timeout(self) -> float:
        """float: Timeout for GPS communication."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="timeout")

    @property
    def gps_pwr_pin(self) -> int:
        """int: GPIO pin number used to power the GPS module."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="pwr_pin")

    @property
    def gps_pwr_up_time(self) -> float:
        """float: Time in seconds to wait after powering up GPS."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="pwr_up_time")

    @property
    def gps_fix_retry_interval(self) -> float:
        """float: Interval in seconds between GPS fix retries."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="fix_retry_interval")

    @property
    def gps_max_fix_time(self) -> float:
        """float: Maximum time in seconds for a GPS fix attempt."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="max_fix_time")

    @property
    def gps_failed_fix_days(self) -> int:
        """int: Num days after which a GPS fix failure triggers an alarm."""
        return self.get_config_value(config=self.config,
                                     section="GPS",
                                     option="failed_fix_days")

    @property
    def activity_digital_inputs(self) -> list:
        """GPIO pins for sensor inputs: list of int."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="sensor_inputs")

    @property
    def lights_output(self) -> int:
        """int: GPIO pin for lights output."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="lights_output")

    @property
    def fault_output(self) -> int:
        """int: GPIO pin for fault output."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="fault_output")

    @property
    def crit_fault_out(self) -> int:
        """int: GPIO pin for critical fault output."""
        return self.get_config_value(config=self.config,
                                     section="IO",
                                     option="crit_fault_out")

    @property
    def sunrise_offset(self) -> int:
        """int: Offset from sunrise in seconds for GPS fixing window."""
        return self.get_config_value(config=self.config,
                                     section="FIX_WINDOW",
                                     option="sunrise_offset")

    @property
    def sunset_offset(self) -> int:
        """int: Offset from sunset in seconds for GPS fixing window."""
        return self.get_config_value(config=self.config,
                                     section="FIX_WINDOW",
                                     option="sunset_offset")

    @property
    def media_mount_point(self) -> str:
        """str: Mount point of attached USB drives."""
        return self.get_config_value(config=self.config,
                                     section="DATA_STORE",
                                     option="media_mount_point")

    @property
    def persistent_data_json(self) -> str:
        """str: Path to persistent JSON data file."""
        return self.get_config_value(config=self.config,
                                     section="DATA_STORE",
                                     option="persistent_data_JSON")

    @property
    def ISO_country2(self) -> str:
        """str: 2character ISO country code."""
        return self.get_config_value(config=self.config,
                                     section="LOCATION",
                                     option="ISO_country2")

    @property
    def place_name(self) -> str:
        """str: Location place name."""
        return self.get_config_value(config=self.config,
                                     section="LOCATION",
                                     option="place_name")

    @property
    def sync_system_time(self) -> bool:
        """bool: Whether to sync system time after a valid GPS fix."""
        return self.get_config_value(config=self.config,
                                     section="GENERAL",
                                     option="sync_system_time")

    def load_config(self) -> None:
        """Load and validate configuration values or fall back to defaults.

        This method attempts to load the configuration file specified by
        `config_path`. If validation fails, it reverts to predefined fallback
        values. If loading fails due to file or parsing errors, it raises a
        `ConfigNotLoaded` exception.

        Raises
        ------
            ConfigNotLoaded: If the configuration file cannot be loaded or
                             parsed.
        """
        try:
            # Attempt to load and validate the configuration file
            if not self.__validate_and_load(self.config_path):
                logging.warning(
                    "CONFIG: Invalid configuration, using fallback values.")
                # Load fallback configuration if validation fails
                self.config.read_dict(self._FALLBACK_VALUES)
            else:
                # Mark the configuration as valid upon successful loading and
                # validation
                self._valid_config = True
        except (FileNotFoundError, configparser.Error) as e:
            # Log the error and raise an exception if loading fails
            logging.error("CONFIG: Failed to load configuration file: %s", e)
            raise ConfigNotLoaded("Configuration could not be loaded.")

    def validate_config_file(self, file_path: str) -> bool:
        """Validate config file at path without modifying main configuration.

        This method loads the configuration file located at `file_path` into a
        temporary `ConfigParser` instance to verify its structure and contents.
        It does not alter the main configuration held by the singleton
        instance, making it suitable for testing external configurations
        (e.g., USB-based configs) before committing to their use in
        the application.

        Args
        ----
            file_path (str): Path to the configuration file to validate. The
                file should contain expected sections and options
                for successful validation.

        Returns
        -------
            bool:
                - True if the configuration file has a valid structure and
                       unique GPIO pin definitions.
                - False if any structural or parsing issues are detected.

        Example
        -------
            To check an external configuration file is valid before using it:

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

            # Validate configuration structure and GPIO uniqueness using
            # private methods to avoid altering the main configuration state
            if self.__validate_config_structure(temp_config) and \
                    self.__validate_unique_pins(temp_config):
                logging.info(
                    "CONFIG: Alternative config file at %s is valid.",
                    file_path)
                return True  # File is valid (meets structural expectations)
            else:
                logging.warning(
                    "CONFIG: Alternative config file at %s is invalid.",
                    file_path)
                return False  # File is invalid if structure or pins
                # assignments do not meet expectations

        except configparser.Error as e:
            # Log any errors encountered during parsing and return False to
            # indicate invalid config
            logging.error(
                "CONFIG: Error parsing alternative config file %s: %s",
                file_path, e)
            return False

    @staticmethod
    def _convert_to_type(raw_value, specified_type, accepts_list):
        """Convert a raw value to type, handling lists if needed.

        Args
        ----
            raw_value (str): The raw value from the configuration file.
            specified_type (type): The expected type of the value (int, float,
            str). accepts_list (bool): Whether the value should be parsed as a
            list.

        Returns
        -------
            The converted value, either as a single value or a list.
        """
        logging.debug("CONFIG: Converting %s to type %s",
                      raw_value, specified_type)
        # If the value is expected to be a list and accepts_list is True
        if accepts_list and specified_type == int:
            return [int(item.strip()) for item in
                    str(raw_value).split(",") if item.strip()]

        # Apply type conversion based on specified type
        if specified_type == int:
            return int(raw_value)
        elif specified_type == float:
            return float(raw_value)
        elif specified_type == str:
            str_val = str(raw_value)
            if str_val.startswith('"') and str_val.endswith('"'):
                return str(raw_value[1:-1])
            return str_val
        elif specified_type == bool:
            return str(raw_value).lower() in ("true", "1", "yes", "on")

        return raw_value

    def _get_default_value(self, section: str, option: str):
        """Retrieve the fallback value for a specific section and option.

        Args
        ----
            section (str): The section name in `_FALLBACK_VALUES`, such as
                        "GPS" or "GENERAL".
            option (str): The specific option name within the section, such as
                        "log_file".

        Returns
        -------
            The raw fallback value as defined in `_FALLBACK_VALUES`.
        """
        def_val = self._FALLBACK_VALUES.get(section, {}).\
            get(option, {}).get("value")
        logging.debug("CONFIG: Default value for %s.%s is [%s]",
                      section, option, def_val)
        return def_val

    def get_config_value(self, config, section, option):
        """Retrive config option from section.

        Retrieve a configuration value from the specified section and option,
        applying the explicitly defined type and falling back to default values
        if necessary.

        This method retrieves a configuration value from a given section and
        option in the config file, default to a specified value if necessary.
        The type of the value is explicitly defined in `_FALLBACK_VALUES`.
        If an option is marked as accepting a list, it is parsed as a
        comma-separated string and returned as a list, even if it contains a
        single value.

        Args
        ----
            config (ConfigParser): The configuration parser instance containing
                                the loaded configuration.
            section (str): The config section, such as "GPS" or "GENERAL".
            option (str): The option name in the section, such as "baudrate".

        Returns
        -------
            The configuration value, cast to the appropriate type (or parsed as
            a list if marked `accepts_list`). If the option is missing or
            invalid, the fallback value is returned.

        Raises
        ------
            ValueError: If the retrieved value cannot be converted to the
                        specified type.
        """
        # Retrieve the fallback dictionary entry for type and value
        logging.debug("CONFIG: Getting config value for %s.%s",
                      section, option)
        default_value = self._get_default_value(section, option)
        option_spec = self._FALLBACK_VALUES.get(section, {}).get(option, {})
        specified_type = option_spec.get("type", str)
        accepts_list = option_spec.get("accepts_list", False)
        logging.debug("CONFIG: [%s].%s default = %s",
                      section, option, default_value)
        logging.debug("CONFIG: [%s].%s type = %s",
                      section, option, specified_type)
        logging.debug("CONFIG: [%s].%s accepts lists = %s",
                      section, option, accepts_list)

        try:
            # Retrieve the raw value from the config, or use the fallback
            raw_value = self.config.get(
                section, option, fallback=default_value)
            # Convert the raw value to the correct type
            logging.info("CONFIG: Option %s.%s set with value from config "
                         "file, type is [%s], value is %s, (%s accept lists)",
                         section, option, str(specified_type), raw_value,
                         "does" if accepts_list else "doesn't")
            return ConfigLoader._convert_to_type(raw_value,
                                                 specified_type, accepts_list)

        except (configparser.NoSectionError,
                configparser.NoOptionError, ValueError) as e:
            logging.warning(
                "CONFIG: Value for %s.%s is missing or invalid in the config "
                "file, using default value %s of type [%s], "
                "(%s accept lists): %s", section, option, default_value,
                str(specified_type), "does" if accepts_list else "doesn't", e)
            # Use the fallback value and convert it to the correct type
            return self._convert_to_type(default_value,
                                         specified_type, accepts_list)

    def __validate_and_load(self, file_path: str) -> bool:
        """Load and validate the configuration file.

        This method attempts to read the configuration from the specified file
        path. It verifies that the configuration structure includes all
        required sections and that GPIO pins are uniquely assigned across
        configuration items.

        Args
        ----
            file_path (str): Path to the configuration file to be loaded.

        Returns
        -------
            bool: True if the configuration is successfully loaded and passes
                  all validation checks, False otherwise.

        Raises
        ------
            configparser.Error: Raised if an error occurs during file parsing.
        """
        # Initialize a ConfigParser instance to read the file
        config = configparser.ConfigParser()
        try:
            # Attempt to read the configuration file
            config.read(file_path)
            logging.info("CONFIG: Read config file from %s", file_path)

            # Validate configuration structure and GPIO pin assignments
            if not self.__validate_config_structure(config):
                return False
            if not self.__validate_unique_pins(config):
                return False

            # If all checks pass, assign the validated config to the instance
            logging.info("CONFIG: config file at %s is valid")
            self.config = config
            return True
        except configparser.Error as e:
            logging.error(
                "CONFIG: Parsing error for config file %s: %s", file_path, e)
            return False

    def __validate_config_structure(self,
                                    config: configparser.ConfigParser) -> bool:
        """Ensure all required sections are present and log any empty sections.

        This method checks that the config contains all required sections
        as defined in `_FALLBACK_VALUES`. If a required section is missing,
        logs an error and returns False. If a section is present but contains
        no values, it logs a warning but still considers the structure valid.

        Args
        ----
            config (configparser.ConfigParser): The configuration parser
                                instance containing the loaded configuration.

        Returns
        -------
            bool: True if all required sections are present, False if any
                  required sections are missing.
        """
        # Retrieve required sections from fallback values
        required_sections = self._FALLBACK_VALUES.keys()
        for section in required_sections:
            # Check if each required section exists in the loaded config
            if section not in config:
                logging.error("CONFIG: config file is invalid, required "
                              "section is missing: %s", section)
                return False
            # Log a warning if the section exists but is empty
            elif not config.items(section):
                logging.warning("CONFIG: Section [%s] in config file contains "
                                "no values.", section)
        return True

    def __validate_unique_pins(self,
                               config: configparser.ConfigParser) -> bool:
        """Ensure each GPIO pin is defined only once across the configuration.

        This method iterates through all configuration items marked with the
        'is_pin' flag in `_FALLBACK_VALUES`, retrieving the pin values and
        checking for duplicates across the configuration. If any pin is defined
        multiple times, it logs an error and returns False.

        Args
        ----
            config (configparser.ConfigParser): The configuration parser
                                instance containing the loaded configuration.

        Returns
        -------
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
                        # Retrieve the pin(s) from the config
                        pins = self.get_config_value(config, section, key)

                        # If pins is a single int, wrap it in a list
                        if isinstance(pins, int):
                            pins = [pins]

                        logging.debug("CONFIG: %s.%s is pin assignment (%s)",
                                      section, key, pins)

                        for pin in pins:
                            # Check for duplicate pin assignments
                            if pin in pins_used:
                                logging.error("CONFIG: Pin %s is defined"
                                              " multiple times. [%s]",
                                              pin, pins_used)
                                return False
                            pins_used.add(pin)
        return True
