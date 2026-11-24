# radio_config.py - ESP-NOW link settings. Deployed IDENTICALLY to BOTH boards.
#
# The ONLY place MAC addresses live. Fill them in from each board's own report:
#     mpremote connect <PORT> run esp32/apps/board_info.py
# (or `python3 esp32/tools/esp32_ports.py --read-mac <PORT>` before MicroPython
#  is flashed: the ESP32 base MAC is the Wi-Fi station MAC).
# Both nodes refuse to start while either value is None, malformed, or equal to
# the other, and each node refuses to run if its own MAC is not the one listed
# for its role (stops the wrong program running on the wrong board).
#
# Label key: [USER] user-specified, [BENCH DEFAULT] software choice for bench
# testing, configurable, not a mission requirement; [PDR] from the PDR.

# Confirmed by the user 2026-11-24 (board wired to the sensors); read with esptool read-mac on
# /dev/cu.usbserial-0001, chip ESP32-D0WD-V3 rev v3.1.
FLIGHT_MAC = "4c:c3:82:ec:c9:d8"   # CanSat flight computer
# Confirmed by the user 2026-11-24 (board on the laptop); read with esptool read-mac on
# /dev/cu.usbserial-5, chip ESP32-D0WD-V3 rev v3.1.
GROUND_MAC = "70:4b:ca:02:ce:30"   # ground station

# Both boards must use the same Wi-Fi channel (1-13). [BENCH DEFAULT]
# ESP-NOW with no access point uses whatever channel the radio is set to.
ESPNOW_CHANNEL = 1

# Telemetry period. [PDR] slides 6/17/19: 4 Hz target (OD-030 still open).
TELEMETRY_PERIOD_MS = 250

# A telemetry frame with no ACK after this long counts as "ack missing". [BENCH DEFAULT]
ACK_TIMEOUT_MS = 500

# Flight side: no ACK for this long -> link DOWN -> periodic radio re-initialisation.
# [PDR] slide 17: allowable link gap <= 1.0 s.
LINK_DOWN_MS = 1000
RECOVERY_INTERVAL_MS = 2000   # [BENCH DEFAULT] minimum time between re-initialisations

# Ground side: time since the last valid frame before STALE / LOST. [BENCH DEFAULT]
GROUND_STALE_MS = 1000
GROUND_LOST_MS = 3000

# Bounded work per loop iteration (non-blocking guarantee). [BENCH DEFAULT]
MAX_PENDING_ACKS = 16
MAX_RX_PER_POLL = 8
