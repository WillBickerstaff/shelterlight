"""Fake package to mimic RPi.GPIO."""

from random import randint


class _FakeGPIO(object):

    # Define constants
    # see: https://sourceforge.net/p/raspberry-gpio-python/code/ci/
    #      default/tree/source/constants.c
    HIGH = 1
    LOW = 0
    IN = 1
    OUT = 0
    HARD_PWM = 43
    I2C = 42
    SPI = 41
    SERIAL = 40
    UNKNOWN = -1
    BOARD = 10
    BCM = 11
    PUD_OFF = 0
    PUD_UP = 2
    PUD_DOWN = 1
    RISING = 0
    FALLING = 0
    BOTH = 0

    def __init__(self):
        self._mode = None
    # Define PWM
    # see: https://sourceforge.net/p/raspberry-gpio-python/code/ci/
    #      default/tree/source/py_pwm.c
    class PWM(object):

        def __init__(self, channel, frequency):
            pass

        def start(self, dutycycle):
            pass

        def ChangeDutyCycle(self, dutycycle):
            pass

        def ChangeFrequency(self, frequency):
            pass

        def stop(self):
            pass

    # Define functions
    # see: https://sourceforge.net/p/raspberry-gpio-python/code/ci/
    #      default/tree/source/py_gpio.c
    def cleanup(self, channel=None):
        pass

    def setup(self, channel, direction, initial=0, pull_up_down=PUD_OFF):
        pass

    def output(self, channel, value):
        pass

    def input(self, channel):
        return randint(0, 1)

    def setmode(self, mode):
        if self._mode is None:
            self._mode = mode
        elif self._mode != mode:
            raise RuntimeError(
                f"GPIO mode already set to {self._mode}, can't change to {mode}"
            )

    def getmode(self):
        return self._mode

    def add_event_callback(self, gpio, callback):
        pass

    def add_event_detect(self, gpio, edge, callback=None, bouncetime=None):
        pass

    def remove_event_detect(self, gpio):
        pass

    def event_detected(self, channel):
        return False

    def wait_for_edge(self, channel, edge, bouncetime=None, timeout=None):
        pass

    def gpio_function(self, channel):
        return GPIO.OUT

    def setwarnings(self, state):
        pass


GPIO = _FakeGPIO()

# Constants
BOARD = GPIO.BOARD
BCM = GPIO.BCM
OUT = GPIO.OUT
IN = GPIO.IN
HIGH = GPIO.HIGH
LOW = GPIO.LOW
PUD_DOWN = GPIO.PUD_DOWN
PUD_UP = GPIO.PUD_UP
PUD_OFF = GPIO.PUD_OFF

# Edge detection constants
RISING = GPIO.RISING
FALLING = GPIO.FALLING
BOTH = GPIO.BOTH

# Functions
setup = GPIO.setup
input = GPIO.input
output = GPIO.output
cleanup = GPIO.cleanup
setmode = GPIO.setmode
getmode = GPIO.getmode
add_event_detect = GPIO.add_event_detect
remove_event_detect = GPIO.remove_event_detect
add_event_callback = GPIO.add_event_callback
wait_for_edge = GPIO.wait_for_edge
event_detected = GPIO.event_detected
gpio_function = GPIO.gpio_function
setwarnings = GPIO.setwarnings

# PWM class
PWM = GPIO.PWM
