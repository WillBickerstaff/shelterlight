# Dummy RPi.GPIO module

# Define GPIO modes
BCM = 'BCM'
BOARD = 'BOARD'
OUT = 'OUT'
IN = 'IN'
HIGH = 1
LOW = 0

# Set up the GPIO mode
def setmode(mode):
    print(f"GPIO mode set to {mode}")

# Set up a pin for input or output
def setup(pin, mode):
    print(f"Pin {pin} set to {mode}")

# Write a value to a pin
def output(pin, state):
    print(f"Pin {pin} set to {'HIGH' if state else 'LOW'}")

# Read a value from a pin
def input(pin):
    return LOW

# Clean up GPIO settings
def cleanup(pin=None):
    if pin:
        print(f"GPIO pin {pin} cleaned up")
    else:
        print("GPIO cleanup called")

# Warnings control
def setwarnings(flag):
    print(f"GPIO warnings set to {'enabled' if flag else 'disabled'}")
