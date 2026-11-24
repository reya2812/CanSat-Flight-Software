# flight_config.py - flight-board BRING-UP configuration (pins, sensor gates).
#
# Pins are USER-REPORTED WIRING (2026-11-19 and 2026-11-24), UNVERIFIED (OD-077).
# They are deliberately NOT in micropython/cansat/config/hardware_config.py,
# which keeps every pin TBD until the team approves the wiring (OD-054); the
# guard scan enforces that. This file is used only by the esp32/ bring-up and
# telemetry programs.
#
# No servo, buzzer, switch or other OUTPUT pin is configured here, on purpose.

# ---- shared I2C bus: GY-91, standalone BMP280, INA219 ----  [USER] unverified
I2C_ID = 0
I2C_SDA = 21
I2C_SCL = 22
I2C_FREQ_HZ = 100000   # [BENCH DEFAULT] standard mode: most tolerant of long jumper wires

# ---- micro-SD over SPI ----  [USER] unverified
SD_SCK = 18
SD_MISO = 19
SD_MOSI = 23
SD_CS = 5              # [USER 2026-11-24] moved from GPIO13 (D-023). GPIO5 is a strapping pin: see hardware/pinout.md
SD_SLOT = 2            # [ASSUMPTION] machine.SDCard slot 2 = SPI mode on the ESP32 port
SD_MOUNT_POINT = "/sd"
# User wiring 2026-11-24 (D-023): module VCC from the ESP32 VIN (5 V) pin, GND to GND.
# Leave False until it is confirmed that THIS module is a 5 V-input type (own
# 3.3 V regulator + level shifting), from its documentation/schematic.
# While False nothing touches the card. Same gate as bringup/esp32_hw_diag.py.
SD_SUPPLY_CONFIRMED = False

# ---- barometers ----
# User inventory: GY-91 (on-board BMP280-family) + one standalone BMP280.
# A BMP280 answers at 0x76 or 0x77 only, so two of them need different straps.
EXPECTED_BAROMETERS = 2
# Which address feeds altitude (baro1). None = the lowest address that holds a
# BMP280/BME280. Software cannot tell which board is which: map it physically.
BARO_PRIMARY_ADDR = None
# Altitude reference pressure in Pa. None = the first valid baro1 reading after
# boot (altitude above the power-on site). Set a number (e.g. a measured QNH or
# ground pressure) to override. No default sea-level value is assumed.
BARO_REFERENCE_PA = None

# ---- INA219 (read-only) ----
INA219_ADDR = 0x40     # [USER/docs/03] default strap; confirm by scan
INA219_SHUNT_OHMS = 0.1  # [docs/03] 0.1 ohm shunt; confirm the "R100" marking on the board
# Declare what is ACTUALLY wired. While False the values are read but marked
# invalid and never sent as measurements (floating inputs read garbage).
INA219_BUS_CONNECTED = False    # True only when VIN- is connected to the monitored rail
INA219_SHUNT_CONNECTED = False  # True only when the load current flows VIN+ -> shunt -> VIN-

# ---- timing ----  [BENCH DEFAULT]
SENSOR_PERIOD_MS = 50          # sensor sampling period (faster than telemetry, OD-042)
SENSOR_RETRY_MS = 2000         # retry period for a sensor whose init failed
STATUS_PRINT_MS = 2000         # flight-board serial status line period
LOOP_SLEEP_MS = 5              # idle sleep per loop iteration

# ---- flight software integration ----
# False: bring-up telemetry only (state = NO_FSW). True: try to run the
# MicroPython flight software from micropython/cansat. Its boot checks will
# REFUSE on hardware until pins and flight parameters are approved (OD-054,
# OD-057, OD-060); telemetry then reports FSW_REFUSED and continues.
RUN_FLIGHT_SOFTWARE = False
