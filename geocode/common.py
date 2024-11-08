class LocationInvalidError(Exception):
    """Exception raised when the location in the config file is not valid
    or not found in the goecode database"""
    pass