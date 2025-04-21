"""Fake lgpio module for testing on non-RPi systems (e.g. Windows)."""

BOTH_EDGES = 3
INPUT = 0
PULL_DOWN = 2

# Simulate gpiochip open/close
def gpiochip_open(chip):
    return 0  # Always return chip handle 0

def gpiochip_close(handle):
    pass

def set_mode(handle, gpio, mode):
    pass

def set_pull(handle, gpio, pud):
    pass

# Fake callback registration
_callback_registry = {}

def callback(handle, gpio, edge, func):
    _callback_registry[gpio] = func
    return 1  # fake callback ID

def cancel_callback(callback_id):
    pass
# -*- coding: utf-8 -*-

