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
from lightlib.common import valid_smallint
from scheduler.feature_sets import FeatureSet


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
            "heartbeat_interval":       {"value": 300,
                                         "type": int,
                                         "is_pin": False,
                                         "Accepts_list": False},
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

            "bypass_fix_window":        {"value": False,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False}
        },
        # ------------------------------------------------------------#
        "IO": {
            "activity_digital_inputs":  {"value": 17,
                                         "type": int,
                                         "is_pin": True,
                                         "accepts_list": True},

            "activity_debounce_ms":     {"value": 25,
                                         "type": int,
                                         "is_pin": False,
                                         "Accepts_list": False},

            "min_detect_on_dur":        {"value": 30,
                                         "type": int,
                                         "is_pin": False,
                                         "Accepts_list": False},

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
        },
        # ------------------------------------------------------------#
        "MODEL": {
            "num_boost_rounds":         {"value": 100,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "training_days":            {"value": 90,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "feature_set":              {"value": "DEFAULT",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "confidence_threshold":     {"value": 0.6,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "historic_weight":          {"value": 0.5,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "boost_enable":             {"value": True,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False},

            "ON_boost":                 {"value": 1.0,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "min_data_in_leaf":         {"value": 10,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "min_on_fraction":          {"value": 0.05,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "early_stopping_rounds":    {"value": 10,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "enable_validation":        {"value": True,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False}
        },
        # ------------------------------------------------------------#
        "SYNTHETIC_DAYS": {
            "enable_synthesis":         {"value": True,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False},

            "inject_noise":             {"value": True,
                                         "type": bool,
                                         "is_pin": False,
                                         "accepts_list": False},

            "jitter_std_seconds":       {"value": 300,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False}
        },
        # ------------------------------------------------------------#
        "FALLBACK": {
            "action":                   {"value": "History",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "schedule_file":            {"value": "Fallback_Schedule.csv",
                                         "type": str,
                                         "is_pin": False,
                                         "accepts_list": False},

            "history_days":             {"value": 30,
                                         "type": int,
                                         "is_pin": False,
                                         "accepts_list": False},

            "certainty_range":          {"value": 0.3,
                                         "type": float,
                                         "is_pin": False,
                                         "accepts_list": False},

            "min_coverage":             {"value": 0.2,
                                         "type": float,
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
    def fallback_action(self) -> str:
        """The fallback method to use when model confidence is low."""
        return self.get_config_value(self.config, "FALLBACK",
                                     "action").lower()

    @property
    def fallback_history_days(self) -> int:
        """Number of history days to look for a fallback schedule."""
        return self.get_config_value(self.config, "FALLBACK",
                                     "history_days")

    @property
    def fallback_schedule_file(self) -> str:
        """Get the configured fallback schedule filename."""
        return self.get_config_value(self.config, "FALLBACK",
                                     "schedule_file")

    @property
    def fallback_certainty_range(self) -> float:
        """Get the configured certainty range.

        Predictions below certainty_range are considered confidently OFF.
        Predictions above (1 - certainty_range) are considered confidently ON.
        All other predictions are treated as uncertain.
        """
        return self.get_config_value(self.config, "FALLBACK",
                                     "certainty_range")

    @property
    def fallback_min_coverage(self) -> float:
        """Get the minimum coverage required by certainty range."""
        return self.get_config_value(self.config, "FALLBACK",
                                     "min_coverage")

    @property
    def synth_days(self) -> bool:
        """Generate synthetic days for days without activity."""
        return self.get_config_value(self.config, "SYNTHETIC_DAYS",
                                     "enable_synthesis")

    @property
    def inject_synth_noise(self) -> bool:
        """Inject noise into synthetic days."""
        return self.get_config_value(self.config, "SYNTHETIC_DAYS",
                                     "inject_noise")

    @property
    def synth_noise_seconds(self) -> int:
        """Jitter noise standard deviation amount in seconds."""
        return self.get_config_value(self.config, "SYNTHETIC_DAYS",
                                     "jitter_std_seconds")

    @property
    def model_boost_rounds(self) -> int:
        """Number of boosting rounds for LightGBM."""
        return self.get_config_value(self.config, "MODEL",
                                     "num_boost_rounds")

    @property
    def enable_model_validation(self) -> bool:
        """Enable or disable model validation data splits."""
        return self.get_config_value(self.config, "MODEL",
                                     "enable_validation")

    @property
    def min_on_fraction(self) -> float:
        """The minimum ON fraction required for a validation split."""
        return self.get_config_value(self.config, "MODEL",
                                     "min_on_fraction")

    @property
    def early_stopping_rounds(self) -> int:
        """Number of rounds score disn't improve before early stopping."""
        return self.get_config_value(self.config, "MODEL",
                                     "early_stopping_rounds")

    @property
    def boost_enable(self) -> bool:
        """Enable ON boosting."""
        return self.get_config_value(self, "MODEL",
                                    "enable_boost")

    @property
    def min_data_in_leaf(self) -> int:
        """Minimum amount of data in a leaf.

        Lower values increase sensitivity to rare cases.
        """
        return self.get_config_value(self.config, "MODEL",
                                     "min_data_in_leaf")

    @property
    def ON_boost(self) -> float:
        """Get the multiplier for boosting the number of ONs."""
        return self.get_config_value(self.config, "MODEL",
                                     "ON_boost")

    @property
    def training_days_history(self) -> int:
        """Get the number of days  to be used for training th emodel."""
        return self.get_config_value(self.config, "MODEL",
                                     "training_days")

    @property
    def historic_weight(self) -> float:
        """Weight given to historic datta for model training."""
        return self.get_config_value(self.config, "MODEL",
                                     "historic_weight")

    @property
    def confidence_threshold(self) -> float:
        """Minimum prediction confidence threshold for lights ON."""
        return self.get_config_value(self.config, "MODEL",
                                     "confidence_threshold")

    @property
    def model_features(self) -> int:
        """Model feature_set to use for training."""
        model_str = self.get_config_value(config=self.config, section="MODEL",
                                          option="feature_set").upper()
        try:
            return FeatureSet[model_str]
        except KeyError:
            logging.warning("Invalid MODEL.feature_set in config file (%s) "
                            "Using DEFAULT feature_set.", model_str)
            return FeatureSet.DEFAULT

    @property
    def min_activity_on(self) -> int:
        """Minimum `on time` for light aoutput after activity detection (S)."""
        return self.get_config_value(config=self.config, section="IO",
                                     option="min_detect_on_dur")

    @property
    def heartbeat_interval(self) -> int:
        """int: The time in seconds hearbeat messages appear in the log."""
        return self.get_config_value(config=self.config, section="GENERAL",
                                     option="heartbeat_interval")

    @property
    def bypass_fix_window(self) -> bool:
        """bool: True if GPS fix can be attempted at any time."""
        return self.get_config_value(config=self.config, section="GPS",
                                     option="bypass_fix_window")

    @property
    def activity_debounce_ms(self) -> int:
        """Int: debounce time in milliseconds for activity inputs."""
        return self.get_config_value(config=self.config, section="IO",
                                     option="activity_debounce_ms")

    @property
    def activity_debounce_s(self) -> float:
        """Float: debounce time in seconds for activity inputs."""
        return self.activity_debounce_ms / 1000.0

    @property
    def max_activity_time(self) -> int:
        """Max time activity can be high before fault is generated."""
        t = self.get_config_value(config=self.config, section="IO",
                                  option="max_activity_time")
        # Validate against SMALLINT max
        try:
            valid_smallint(t)
            return t
        except ValueError:
            logging.warning(
                f"Configured max_activity_time={t} "
                "exceeds SMALLINT limit (32767), using 32767")
            return 32767

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
                                     option="activity_digital_inputs")

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
                    "Alternative config file at %s is valid.",
                    file_path)
                return True  # File is valid (meets structural expectations)
            else:
                logging.warning(
                    "Alternative config file at %s is invalid.",
                    file_path)
                return False  # File is invalid if structure or pins
                # assignments do not meet expectations

        except configparser.Error as e:
            # Log any errors encountered during parsing and return False to
            # indicate invalid config
            logging.error(
                "Error parsing alternative config file %s: %s",
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
        # logging.debug("Converting %s to type %s",
        #              raw_value, specified_type)
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
        default_value = self._get_default_value(section, option)
        option_spec = self._FALLBACK_VALUES.get(section, {}).get(option, {})
        specified_type = option_spec.get("type", str)
        accepts_list = option_spec.get("accepts_list", False)

        try:
            # Retrieve the raw value from the config, or use the fallback
            raw_value = self.config.get(
                section, option, fallback=default_value)
            # Convert the raw value to the correct type
            return ConfigLoader._convert_to_type(raw_value,
                                                 specified_type, accepts_list)

        except (configparser.NoSectionError,
                configparser.NoOptionError, ValueError) as e:
            logging.warning(
                "Value for %s.%s is missing or invalid in the config "
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
            logging.info("Read config file from %s", file_path)

            # Validate configuration structure and GPIO pin assignments
            if not self.__validate_config_structure(config):
                return False
            if not self.__validate_unique_pins(config):
                return False

            # If all checks pass, assign the validated config to the instance
            logging.debug("config file at %s is valid")
            self.config = config
            return True
        except configparser.Error as e:
            logging.error(
                "Parsing error for config file %s: %s", file_path, e)
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
                logging.error("config file is invalid, required "
                              "section is missing: %s", section)
                return False
            # Log a warning if the section exists but is empty
            elif not config.items(section):
                logging.warning("Section [%s] in config file contains "
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

                        # logging.debug("CONFIG: %s.%s is pin assignment (%s)",
                        #              section, key, pins)

                        for pin in pins:
                            # Check for duplicate pin assignments
                            if pin in pins_used:
                                logging.error("Pin %s is defined "
                                              "multiple times. [%s]",
                                              pin, pins_used)
                                return False
                            pins_used.add(pin)
        return True
