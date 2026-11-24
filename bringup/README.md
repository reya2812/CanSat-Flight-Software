# Hardware bring-up diagnostic (bench check, NOT flight software)

`esp32_hw_diag.py` is a standalone MicroPython script for checking the assembled sensor circuit on an ESP32 DevKit. It imports nothing from `micropython/cansat`, and the flight software never imports it. Its results are **bench observations, not flight validation**.

## What it checks
| Component | How | Writes to the device |
|---|---|---|
| I2C bus (SDA GPIO21, SCL GPIO22) | Initialises the bus at 100 kHz, scans it and prints every address in hex | — |
| IMU (GY-91) | Identifies the chip by WHO_AM_I (MPU-6050/6500/9250/9255), reads the full-scale settings and one raw accelerometer/gyro sample. An unlisted WHO_AM_I is reported as UNKNOWN with its raw hex value (WARN), and the read is still attempted | PWR_MGMT_1: clears the sleep bit once, then restores the original value |
| Magnetometer | Reported only if 0x0C is on the main bus (an MPU-9250's AK8963 sits behind the IMU's bypass, which this script does not enable) | — |
| BMP280 (GY-91 on-board + standalone) | Identifies each by chip ID 0x58, reads its calibration, takes one forced measurement and converts it | ctrl_meas = 0x25 once (oversampling ×1, forced; a diagnostic choice, not a flight setting) |
| Duplicate BMP280 addresses | Warns if fewer than the 2 expected BMP280s answer (see below) | — |
| INA219 | Reads the config, shunt-voltage and bus-voltage registers only | none (read-only) |
| SD card (SCK 18, MISO 19, MOSI 23, CS 13) | **Disabled by default (SKIP).** When enabled: `machine.SDCard` in SPI mode, mount, list the root, unmount | none (no files written) |

Not tested: the HC-12 (unavailable), servos, buzzers, batteries and deployment hardware. The script configures no outputs, PWM or DAC.

## Before you run it
- **Pins are user-reported and unverified.** They live only in this script. The flight configuration (`micropython/cansat/config/hardware_config.py`) still has every pin TBD (OD-054, OD-077).
- **INA219:** connect nothing to VIN+/VIN- (no battery, no load). This is a logic-interface check only. With floating inputs the voltage values are meaningless, and current and power are not computed (they need an unset calibration).
- **SD card:** leave `SD_SUPPLY_CONFIRMED = False` until you have confirmed that the SD module's supply and logic levels suit 3.3 V. Then set it to `True` and re-run.
- **Register maps and formulas are [ASSUMPTION]:** they were recalled from the Bosch BMP280, InvenSense MPU and TI INA219 datasheets and not yet checked against the PDFs.

## Running it (you do this; nothing here flashes or modifies the ESP32)
The board must already run MicroPython. Copy the script to the board and run it with Thonny (open it, then Run), or with `mpremote` if you have it:

```sh
mpremote run bringup/esp32_hw_diag.py
```

`mpremote run` executes the file from the laptop without saving it on the board. Neither tool is installed by this project.

## Reading the output
Each line is `[PASS]`, `[FAIL]`, `[WARN]`, `[SKIP]` or `[INFO]`, followed by a summary line.
- **PASS:** the device answered, was identified and returned plausible data. It does not mean the value is accurate.
- **WARN:** it answered but something is unexpected, for example an unknown ID or a non-default INA219 config.
- **FAIL:** no answer, an I/O error, or impossible data.

One failing device never stops the others.

### Two BMP280s and duplicate addresses
A BMP280 answers at 0x76 or 0x77 depending on its address strap. The GY-91's on-board BMP280 and the standalone breakout may both use the same address. **Two devices at the same address cannot be addressed independently on one bus.** Both answer at once, data can be silently corrupted, and a scan cannot show it.
- **If fewer than two BMP280s are found,** the script warns. Test each BMP280 alone on the bus, or change one breakout's address strap.
- **If two are found,** software still cannot tell which is the GY-91's. Disconnect one to map them. This diagnostic also cannot rule out a further device hiding behind one of those addresses.

## Laptop tests (logic only)
```sh
python3 -m unittest bringup/test_esp32_hw_diag.py
```

These run the script against a fake `machine` module and fake register maps. They check isolation, reporting, which registers are written, and that the SD test stays disabled. **They prove nothing about the real board, wiring or sensors.**
