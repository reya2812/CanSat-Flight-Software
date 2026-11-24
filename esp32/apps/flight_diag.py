# flight_diag.py - run the flight-board hardware diagnostic (esp32/lib/cs_diag.py).
#
#     mpremote connect <PORT> run esp32/apps/flight_diag.py
#
# Needs /lib and flight_config.py on the board (esp32/tools/deploy.py --role flight).
# Does NOT need the flight software, the ground board or the radio link.
# No servo / buzzer / deployment code. SD writes happen only if
# flight_config.SD_SUPPLY_CONFIRMED is True, and only to its own test file.
import os
import sys

import machine

import flight_config as FC
from cs_diag import run_diag

try:
    import radio_config as RC
except ImportError:
    RC = None
try:
    import network
except ImportError:
    network = None
try:
    import espnow  # noqa: F401 - presence check only; the radio is not activated
    _espnow = True
except ImportError:
    _espnow = False

run_diag(machine, os, FC, rc=RC, network_mod=network, espnow_present=_espnow, sys_mod=sys,
         token="%08x" % int.from_bytes(os.urandom(4), "little"))
