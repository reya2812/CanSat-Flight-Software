# Hardware Pinout

**Status (2026-11-24):** bring-up pins are **user-reported and UNVERIFIED** (OD-077). No pin is team-approved (OD-054). The flight configuration `micropython/cansat/config/hardware_config.py` keeps every pin TBD, and the guard scan enforces that. The bring-up pins live only in `esp32/config/flight_config.py` and `bringup/esp32_hw_diag.py`.

Board: ESP32-WROOM-32 DevKit, 30-pin, CP2102, USB-C (exact make/revision TBD). An earlier version of this file said ESP32-S3; that was superseded by D-006.

## Board identities (user-confirmed 2026-11-24)

- FLIGHT: MAC `4c:c3:82:ec:c9:d8` (ESP32-D0WD-V3 rev v3.1), the board wired to the sensors.
- GROUND: MAC `70:4b:ca:02:ce:30` (ESP32-D0WD-V3 rev v3.1), USB only.

## Flight board (bring-up wiring as reported by the user)

| Signal | ESP32 GPIO | Connected component | Electrical notes | Status |
|---|---|---|---|---|
| I2C SDA | 21 | GY-91, standalone BMP280, INA219 (shared bus) | 3.3 V logic; pull-ups on the breakouts [UNVERIFIED] | user-reported, unverified |
| I2C SCL | 22 | same | same | user-reported, unverified |
| SD SPI SCK | 18 | micro-SD module | Module supply/level shifting must be checked against the module's own documentation | user-reported, unverified |
| SD SPI MISO | 19 | micro-SD module | same | user-reported, unverified |
| SD SPI MOSI | 23 | micro-SD module | same | user-reported, unverified |
| SD SPI CS | 13 | micro-SD module | GPIO13 is not a strapping pin [ASSUMPTION, PHASE1 §2.5] | user-reported, unverified |
| Servo signal(s) | TBD | SG90 | **Not driven by any software.** Never power a servo from a GPIO | TBD (OD-050) |
| Limit switches | TBD | lever switches | — | TBD (OD-051) |
| Buzzers | TBD | active buzzers | — | TBD (OD-052) |
| Radio | — (internal) | ESP-NOW on the ESP32's own 2.4 GHz radio and PCB antenna | No pins; HC-12 not used (D-020) | software only |

Constraints to respect when pins are finalised (PHASE1_PROPOSAL §2.5): avoid strapping pins 0/2/5/12/15 (never pull GPIO12 high), flash pins 6–11, UART0 pins 1/3, and boot-glitching pins for anything that actuates. ADC2 pins cannot be read while Wi-Fi/ESP-NOW is active: use ADC1 (GPIO32–39) for any future analog input.

## Ground board

USB only (power and serial console). No external wiring.
