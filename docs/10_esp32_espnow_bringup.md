# 10 — ESP32 bring-up, ESP-NOW telemetry and hardware validation

**Created:** 2026-11-24. **Decisions:** D-020 (ESP-NOW), D-021 (`esp32/` tree). **Open:** OD-078…OD-082.
**Evidence status:** every result so far is a laptop **software test** with fakes. **Nothing here has run on an ESP32, and nothing is [HW-VERIFIED].**

Every command below runs from the **repository root**.

---

## 1. What exists

| Path | Runs on | Purpose |
|---|---|---|
| `esp32/config/radio_config.py` | both boards | the only place MAC addresses and link timings live |
| `esp32/config/flight_config.py` | flight board | bring-up pins, sensor gates (SD, INA219), timing |
| `esp32/config/ground_config.py` | ground board | display settings |
| `esp32/lib/cs_proto.py` | both | protocol v1: encode / decode / validate (§4) |
| `esp32/lib/cs_link.py` | both | FlightLink (sequence, ACK, timeouts, recovery), GroundLink (duplicates, gaps, health) |
| `esp32/lib/cs_espnow.py` | both | the only module that touches the radio |
| `esp32/lib/cs_bmp280.py`, `cs_mpu.py`, `cs_ina219.py`, `cs_sd.py` | flight | register-level drivers and the SD self-test |
| `esp32/lib/cs_sensors.py` | flight | uniform sensor channels and discovery (§6) |
| `esp32/lib/cs_telemetry.py`, `cs_flight.py` | flight | telemetry builder and the non-blocking node loop |
| `esp32/lib/cs_fsw_bridge.py` | flight (optional) | connects the drivers to the existing `micropython/cansat` flight software (§8) |
| `esp32/lib/cs_diag.py`, `esp32/apps/flight_diag.py` | flight | hardware diagnostic (§7) |
| `esp32/apps/flight_node.py`, `ground_node.py`, `board_info.py` | boards | programs you run |
| `esp32/tools/*.py` | laptop | port detection, guarded flashing, role-checked deployment |
| `esp32/tests/` | laptop | 138 unit/integration/smoke tests (logic only) |

**Not touched by this work:** the existing flight state machine and every other file in `micropython/cansat/`, `firmware/` (C++), `bringup/`, and all their tests and guards.

## 1a. The two boards (user-confirmed 2026-11-24)

| Role | Port (this laptop) | MAC | Chip | How confirmed |
|---|---|---|---|---|
| **FLIGHT** (wired to all sensors) | `/dev/cu.usbserial-0001` | `4c:c3:82:ec:c9:d8` | ESP32-D0WD-V3 rev v3.1 | `esptool read-mac` + user's physical identification |
| **GROUND** (laptop only) | `/dev/cu.usbserial-5` | `70:4b:ca:02:ce:30` | ESP32-D0WD-V3 rev v3.1 | same |

Port names can change after replugging; the MAC is the identity. Selected firmware: `ESP32_GENERIC-20260824-v1.29.0.bin` (MicroPython v1.29.0), SHA-256 `e67ad6015a0a504c1fec9aa9bbf589d0432ed28e62546f4f8dd8a147f8bd95f6`, byte-identical to the file on micropython.org (checked 2026-11-24). Not yet flashed.

## 2. Hardware setup and wiring

The pins are **user-reported and unverified** (OD-077). They live in `esp32/config/flight_config.py`. The flight `hardware_config.py` stays TBD (OD-054).

| Function | Flight ESP32 GPIO | Device |
|---|---|---|
| I2C SDA / SCL | 21 / 22 | GY-91, standalone BMP280, INA219 (one shared bus, 100 kHz) |
| SD SCK / MISO / MOSI / CS | 18 / 19 / 23 / 13 | SPI micro-SD module |
| Servo | **none configured** | must stay unpowered or disconnected during all of this work |

Before powering anything:
1. **SD module supply:** read the module's own documentation or schematic. Some modules need 5 V on VCC (onboard regulator and level shifter); others are 3.3 V-only. Do not assume either. Until this is confirmed, `SD_SUPPLY_CONFIRMED = False` keeps the software away from the card.
2. **I2C supply:** every I2C breakout must be powered so that its SDA/SCL pull-ups go to **3.3 V**, not 5 V.
3. **Two BMP280s:** a BMP280 answers only at 0x76 or 0x77, set by its SDO/address strap. The GY-91's barometer and the standalone breakout must use **different** addresses. Two devices at the same address answer together, the data may be silently corrupted, and software cannot detect it (§6.3).
4. **INA219:** connect nothing to VIN+/VIN- until a monitored circuit is decided. The software reports no voltage or current until you declare the wiring (§6.4).
5. **Servo:** disconnected or unpowered. No code in `esp32/` can drive it (enforced by `esp32/tests/test_transport_tools_safety.py`).

The ground ESP32 needs only its USB cable.

## 3. Firmware: flash MicroPython (both boards)

Tools: `esptool` and `mpremote` (installed on this laptop: esptool 5.6.0, mpremote 1.29.0). If they are missing: `python3 -m pip install esptool mpremote`.

**3.1 Download** the latest **stable** image for the generic ESP32 from <https://micropython.org/download/ESP32_GENERIC/>. The file is named `ESP32_GENERIC-<date>-v1.xx.x.bin`. Do **not** use the `SPIRAM`, `OTA`, `D2WD`, `UNICORE` or `preview` variants. Use the **same file for both boards**: the flash tool refuses a different SHA-256 for the second board unless you override it. Note the SHA-256 shown on the download page if there is one. ESP-NOW has been in the official ESP32 build since v1.20 [ASSUMPTION: recalled from the MicroPython docs]. `board_info.py` checks it on the board.

**3.2 Identify the boards.** Port names vary, so the tools never assume one. Plug in **one board only**:
```sh
python3 esp32/tools/esp32_ports.py                           # passive list; CP210x ports are flagged
python3 esp32/tools/esp32_ports.py --read-mac /dev/cu.usbserial-XXXX   # chip + MAC (read-only; resets the board)
```
Put a physical label on the board ("FLIGHT, MAC ..:..:.."). Then plug in the second board and repeat. Close any serial monitor on the port first.

**3.3 Flash.** The tool runs a **dry run by default**. It checks the image name and size and prints its SHA-256. It reads the chip and MAC with `esptool read-mac`, refuses non-ESP32 chips, refuses the other role's configured MAC, and prints the exact commands:
```sh
python3 esp32/tools/flash_micropython.py --port /dev/cu.usbserial-XXXX --role flight --firmware ~/Downloads/ESP32_GENERIC-<date>-v1.xx.x.bin
python3 esp32/tools/flash_micropython.py --port /dev/cu.usbserial-XXXX --role flight --firmware ~/Downloads/ESP32_GENERIC-<date>-v1.xx.x.bin --execute
```
`--execute` asks you to type `FLASH FLIGHT <last 3 MAC bytes>`. It then re-reads the MAC, so a board swapped in the meantime aborts the flash. Finally it runs:
```
python3 -m esptool --chip esp32 --port <PORT> --baud 460800 erase-flash
python3 -m esptool --chip esp32 --port <PORT> --baud 460800 write-flash -z 0x1000 <firmware.bin>
```
It also appends the chip, MAC and firmware SHA-256 to `esp32/config/board_records.jsonl`. Repeat with `--role ground` on the other board. Add `--sha256 <hash>` to check the file against the published hash. If the connection fails, hold **BOOT** while the tool connects.

**3.4 Verify after flashing:**
```sh
python3 esp32/tools/esp32_ports.py --mp-info /dev/cu.usbserial-XXXX       # MicroPython version, MAC, espnow yes/no
mpremote connect /dev/cu.usbserial-XXXX run esp32/apps/board_info.py      # full read-only report
```
Record each board's MicroPython version (it is also in `board_records.jsonl` after deployment).

## 4. ESP-NOW configuration and protocol v1 [PROPOSED, OD-079]

### 4.1 Configure
Edit `esp32/config/radio_config.py` and set the two MACs that `board_info.py` printed:
```python
FLIGHT_MAC = "24:0a:c4:xx:xx:xx"
GROUND_MAC = "24:0a:c4:yy:yy:yy"
```
Both boards get the same file. Both programs refuse to start while a MAC is unset, malformed, broadcast or multicast, while the two MACs are equal, or when the board's own MAC is not the one listed for its role.

| Setting | Value | Source |
|---|---|---|
| `ESPNOW_CHANNEL` | 1 | [BENCH DEFAULT]; both boards must match |
| `TELEMETRY_PERIOD_MS` | 250 (4 Hz) | [PDR] slides 6/17/19; OD-030 open |
| `ACK_TIMEOUT_MS` | 500 | [BENCH DEFAULT] |
| `LINK_DOWN_MS` | 1000 | [PDR] slide 17 link-gap target |
| `RECOVERY_INTERVAL_MS` | 2000 | [BENCH DEFAULT] |
| `GROUND_STALE_MS` / `GROUND_LOST_MS` | 1000 / 3000 | [BENCH DEFAULT] |

Wi-Fi runs in station mode only so that ESP-NOW can use the radio. It never joins an access point (`disconnect()` is called), and no router or internet is used. ESP-NOW encryption is not enabled. The application CRC, MAC filtering and the fact that there is **no command uplink** limit the impact of foreign frames.

### 4.2 Frames (little-endian, fixed length, `struct` formats in `cs_proto.py`)

Header (6 B): `magic "CS"` · `version u8 = 1` · `type u8` (1 = telemetry, 2 = ACK) · `boot_id u16` (random per flight-board boot).
Trailer (2 B): CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over header + body. Check value: "123456789" → 0x29B1.

**Telemetry: 78 bytes in total**

| Offset | Field | Type | Unit / meaning |
|---|---|---|---|
| 6 | `seq` | u32 | per-boot sequence number from 0 |
| 10 | `uptime_ms` | u32 | flight-board uptime |
| 14 | `state` | u8 | 0 = flight software NOT running (bring-up); 1–8 = `FlightState` codes from `cansat/core/types.py` |
| 15 | `link` | u8 | flight-side link: 0 UNKNOWN, 1 UP, 2 DEGRADED, 3 DOWN |
| 16 | `valid` | u16 | field validity bits (below) |
| 18 | `flags` | u16 | status flags (below) |
| 20 | `fault` | u32 | flight-software fault mask (C++ bits 0–18 fit); meaningful only with FSW_RUNNING |
| 24 | `status[5]` | 5×u8 | per-sensor status: baro1, baro2, imu, power, sd |
| 29 | `p1` | u32 | baro1 pressure, 0.1 Pa |
| 33 | `t1` | i16 | baro1 temperature, 0.01 °C |
| 35 | `p2` | u32 | baro2 pressure, 0.1 Pa |
| 39 | `t2` | i16 | baro2 temperature, 0.01 °C |
| 41 | `alt` | i32 | altitude above the reference, cm (from baro1) |
| 45 | `ax, ay, az` | 3×i16 | acceleration, milli-g |
| 51 | `gx, gy, gz` | 3×i16 | angular rate, 0.1 °/s |
| 57 | `imu_t` | i16 | IMU die temperature, 0.01 °C |
| 59 | `bus` | u16 | INA219 bus voltage, mV |
| 61 | `shunt` | i16 | INA219 shunt voltage, 10 µV (the register LSB) |
| 63 | `current` | i32 | µA (= shunt voltage / shunt resistance) |
| 67 | `acked_seq` | u32 | last sequence number the flight board saw acknowledged (0xFFFFFFFF = none) |
| 71 | `tx_fail` | u16 | cumulative send failures (saturating) |
| 73 | `ack_miss` | u16 | cumulative missing ACKs (saturating) |
| 75 | `ack_rssi` | i8 | RSSI of the last ACK, dBm (−128 = unknown) |
| 76 | CRC | u16 | |

`valid` bits: 0 BARO1, 1 BARO2, 2 ALT, 3 ACCEL, 4 GYRO, 5 IMU_TEMP, 6 BUS_V, 7 CURRENT, 8 ACK_RSSI.
`flags`: 0 FSW_RUNNING, 1 FSW_REFUSED, 2 BARO_DUP_SUSPECT, 3 IMU_SATURATED, 4 ALT_REF_AUTO, 5 POWER_GATED, 6 LINK_RECOVERING.
Sensor status codes: 0 NOT_PRESENT, 1 INIT_FAILED, 2 OK, 3 READ_ERROR, 4 NOT_READY, 5 IMPLAUSIBLE, 6 UNKNOWN_CHIP, 7 DISABLED.

**ACK: 27 bytes in total.** `ack_seq u32` · `gs_uptime_ms u32` · `rx_ok u32` · `lost u32` · `rejected u16` · `rssi i8` (as received by the ground). Its `boot_id` echoes the telemetry frame's.

### 4.3 Rules
- **Missing data:** the value is sent as 0 and its validity bit is cleared. Values that are NaN, infinite or do not fit the field are sent as missing, **never clamped**. Readers must check `valid` and `status`.
- **Rejected whole frame:** wrong length, magic, version or type; CRC mismatch; an undefined state, link or status code; undefined validity bits. Each is counted by reason (`short`, `magic`, `version`, `type`, `length`, `crc`, `field`).
- **Implausible value with its valid bit set** (pressure outside 300–1100 hPa, temperature outside −40…85 °C, positive RSSI): **only that field is dropped**. The frame is kept and counted as `implausible`, so one bad sensor never hides the others.
- **Sequence:** the ground tracks the highest sequence number per `boot_id`. A gap adds to `lost`. A late frame fills its gap (`late`, `lost` − 1). A repeated sequence number is a `duplicate`: it is acknowledged but not shown. A new `boot_id` counts as a flight reboot and resets tracking.
- **ACK:** the ground acknowledges every valid frame. The flight board counts an ACK as missing after `ACK_TIMEOUT_MS`. A late ACK still proves the link is alive. Telemetry is **not retransmitted**: stale samples have no value, and loss is reported instead.
- **Non-blocking:** `send(..., sync=False)` and `recv(0)`. Work per loop is bounded (at most 8 frames received, 16 pending ACKs). The node loop isolates sensors, the state source and the link from each other (§8).
- **Recovery:** if no ACK arrives for `LINK_DOWN_MS`, the flight board re-initialises ESP-NOW and re-registers the peer, at most once every `RECOVERY_INTERVAL_MS`. It keeps sending throughout.

## 5. Running the two boards

**5.1 Deploy** (copies files only; refuses unless the board's MAC matches the role):
```sh
python3 esp32/tools/deploy.py --role flight --port /dev/cu.usbserial-XXXX --dry-run   # show the plan
python3 esp32/tools/deploy.py --role flight --port /dev/cu.usbserial-XXXX
python3 esp32/tools/deploy.py --role ground --port /dev/cu.usbserial-YYYY
```
Optional flags: `--autorun` installs the node program as `/main.py`, so it starts at every power-up. Remove it with `mpremote connect <PORT> rm :main.py`. `--with-fsw` (flight only) also copies the flight-software package (§8).

**5.2 Hardware diagnostic first** (flight board; the radio is not needed):
```sh
mpremote connect /dev/cu.usbserial-XXXX run esp32/apps/flight_diag.py
```

**5.3 Start the ground station, then the flight board** (two terminals):
```sh
mpremote connect /dev/cu.usbserial-YYYY run esp32/apps/ground_node.py
mpremote connect /dev/cu.usbserial-XXXX run esp32/apps/flight_node.py
```
The ground console refreshes every second. It shows the packet number, flight state, altitude, both pressures and temperatures, acceleration, gyro, IMU temperature, bus voltage and current (when declared connected), each sensor's status, loss %, lost/duplicate/late/rejected counts, time since the last frame, link status (NO_DATA / OK / STALE / LOST) and RSSI. Set `CSV_OUTPUT = True` in `ground_config.py` to also print one `TLM,...` line per packet for logging. To stop, press Ctrl-C. If a board keeps running, press its EN/RST button or run `mpremote connect <PORT> reset`.

## 6. Sensor drivers

All drivers take an injected I2C object (`machine.I2C` on the board, fakes on the laptop). Register maps and formulas are **[ASSUMPTION]**: recalled from the Bosch, InvenSense and TI datasheets and **not yet checked against the PDFs**. The laptop tests use the same recollection, so they cannot catch a wrong one. Only the bench can.

Every sensor sits in a `SensorChannel` exposing `init_ok`, `status`, `error`, `last` (latest reading), `t_ms`, `valid()` and counters. Exceptions stay inside their channel. A failed sensor is re-initialised every `SENSOR_RETRY_MS`, or after 3 consecutive bad reads. While a sensor is down, its last valid reading is replaced by an invalid one, so stale data is never resent as current. Telemetry also refuses readings older than 4 × `SENSOR_PERIOD_MS`.

**6.1 IMU (GY-91):** identity comes only from WHO_AM_I: 0x68 MPU-6050, 0x70 MPU-6500, 0x71 MPU-9250, 0x73 MPU-9255. Any other value gives UNKNOWN_CHIP with the raw hex and **no data is ever marked valid**. The driver's only write clears the SLEEP bit. Ranges and filters are read back from the chip, not changed. It reports acceleration (g), angular rate (°/s), die temperature (family-specific formula) and a saturation flag. Output that reads all zeros (chip asleep or reset) is IMPLAUSIBLE. The magnetometer is not used.

**6.2 Barometers (BMP280 / BME280 temperature + pressure):** chip ID 0x58 or 0x60. Calibration is validated at init. Non-blocking forced mode: each read collects the previous conversion and triggers the next, so the first read is NOT_READY. Oversampling ×1 is a **bring-up choice, not a flight setting**. Altitude uses the ISA formula, identical to `cansat.core.fmath` (tested). The reference is `BARO_REFERENCE_PA` if set, otherwise the first valid baro1 reading after boot (`ALT_REF_AUTO`). No sea-level value is assumed.

**6.3 Duplicate addresses:** one channel per responding address, never two for one address. If fewer BMP280s are identified than `EXPECTED_BAROMETERS` (2), `BARO_DUP_SUSPECT` is raised: either one is missing, or two share an address and look like one. `BARO_PRIMARY_ADDR` picks the altitude source (default: lowest address). Which physical module is which can only be found by disconnecting one (OD-082).

**6.4 INA219 (read-only):** never writes the chip. The INA219 has no ID register, so "identified" means it ACKs and its config register holds 0x399F. Bus voltage is reported only if `INA219_BUS_CONNECTED = True`. Current (= shunt voltage / `INA219_SHUNT_OHMS`, 0.1 Ω) is reported only if `INA219_SHUNT_CONNECTED = True`, and only below the PGA range with no overflow. Otherwise status is DISABLED and the raw values appear in the diagnostic as "not meaningful".

**6.5 micro-SD:** `cs_sd.sd_selftest` runs init, mount, write of its own test file, unmount, remount, read-back, verify, delete and unmount. Failures are reported per step (no card, write-protected, corrupt read-back), and the card is always unmounted. It runs only when `SD_SUPPLY_CONFIRMED = True`, and it never opens or deletes any other file. **There is no flight logging** until the hardware is validated.

## 7. Hardware diagnostic

`flight_diag.py` reports board and firmware details, the STA MAC (checked against `radio_config`), ESP-NOW module presence, the I2C scan, identification, 10 samples per sensor, INA219 status, the SD self-test and a PASS/FAIL/WARN/SKIP/INFO summary. Each row also carries an **evidence level**, and the levels are never mixed:

| Level | Meaning | Who sets it |
|---|---|---|
| software test | `esp32/tests` pass: logic is consistent | laptop |
| DETECTED | something ACKed at that I2C address | diagnostic |
| IDENTIFIED | its ID register holds a supported chip's value | diagnostic |
| PLAUSIBLE | readings are inside physical limits and change between samples | diagnostic |
| **PHYSICALLY VALIDATED** | the checks in §9 were done by a person and recorded | **never set by software** |

`bringup/esp32_hw_diag.py` (unchanged) remains an independent cross-check. It uses its own simpler code, its SD check is read-only, and it can be run with `mpremote run bringup/esp32_hw_diag.py` without deploying anything.

## 8. Integration with the existing flight software

- `cs_fsw_bridge.to_sensor_frame()` maps the driver readings into the existing `cansat.core.types.SensorFrame`, including validity, `comm_ok`, `data_ready` and `saturated`. Limit switches have no driver (OD-051), so they stay invalid.
- `FswState` calls the unchanged `FlightSoftware.tick()` on each sensor sample. Telemetry carries `state()` and `fault_mask()`. Actuator requests are drained and counted only; nothing actuates.
- `start_flight_software()` **always** runs the existing `cansat.boot_checks.run_boot_checks(..., target_hardware=True)`, then also requires an approved parameter set and a persistent store. Today, on the board, it **refuses**: pins are TBD (OD-054), parameters are unapproved (OD-057/OD-060), and no NVS store exists. Telemetry continues with `FSW_REFUSED` set. Enable the attempt with `RUN_FLIGHT_SOFTWARE = True` and `deploy.py --with-fsw`. The path forward is OD-080 and needs your approval, because it means changing guarded components.
- **Communication failure isolation (tested):** with the radio dead, all 17 SYNTHETIC scenarios produce byte-identical flight-software output to runs with no telemetry at all. In node tests, the state source ticks on every sensor sample even with the radio raising on every call, or with the link layer itself crashing.

## 9. Hardware validation checklist (record results in `docs/` or the team log; nothing here is done yet)

| ID | Check | Pass evidence to record |
|---|---|---|
| H-FW-1 | Both boards run the same MicroPython stable release | `board_records.jsonl` SHA-256 and the `board_info.py` version for both |
| H-FW-2 | `espnow` module present on both | `board_info.py` output |
| H-SAFE-1 | Servo disconnected/unpowered during all bring-up | photo / note |
| H-I2C-1 | Scan shows the expected addresses (MPU 0x68/0x69, BMP280 0x76 **and** 0x77, INA219 0x40) | diagnostic output |
| H-IMU-1 | WHO_AM_I value recorded → closes the chip question in OD-076 | diagnostic output |
| H-IMU-2 | Rest the board on each of its 6 faces: about +1 g / −1 g on the matching axis | 6 readings |
| H-IMU-3 | DATA_RDY seen in most samples (OD-081) | diagnostic note line |
| H-IMU-4 | Rotate about each axis: gyro sign and magnitude respond | readings |
| H-BARO-1 | Disconnect one BMP280 at a time and note which address disappears → physical mapping (OD-082) | table: module → address |
| H-BARO-2 | Compare pressure with an independent reference (e.g. a calibrated barometer or local station pressure) and record the difference | values; no pass threshold is set by software |
| H-BARO-3 | Raise the board ~1–2 m: altitude changes in the right direction | readings |
| H-PWR-1 | Decide and wire the INA219 monitored circuit, then set the two `INA219_*_CONNECTED` flags | wiring note |
| H-PWR-2 | Bus voltage vs multimeter on the same rail | both values |
| H-PWR-3 | Current vs multimeter in series; check the shunt marking (R100 = 0.1 Ω) | both values |
| H-SD-1 | SD module supply and logic levels confirmed from its documentation; then `SD_SUPPLY_CONFIRMED = True` | document / note |
| H-SD-2 | Diagnostic SD self-test PASS, with a missing-card run giving FAIL at `mount` | output of both runs |
| H-RF-1 | Bench link (boards ~1 m apart): ground shows LINK OK; record loss % over 5 min | screenshot / numbers |
| H-RF-2 | Power-cycle the flight board: ground shows `reboots` +1 and recovers | output |
| H-RF-3 | Unplug the ground board for 5 s: flight shows DOWN, recovery attempts, then UP | flight console |
| H-RF-4 | Outdoor range walk to ≥ 150 m line of sight ([PDR] target), record loss and RSSI vs distance (OD-078) | table |
| H-RF-5 | Repeat H-RF-1/4 with the flight board inside the closed CanSat enclosure | table |

## 10. Troubleshooting

| Symptom | Likely cause / action |
|---|---|
| `esptool` cannot connect | wrong port, serial monitor open, charge-only USB cable; hold BOOT while connecting |
| Flash tool: "not an original ESP32" | the board is an S2/S3/C3: ESP32_GENERIC is the wrong image |
| `REFUSING TO START: ... MAC ...` | `radio_config.py` not filled in, the wrong board, or deployed with the wrong `--role` |
| `espnow module: MISSING` | not the official ESP32_GENERIC build, or older than v1.20 |
| Ground stays NO_DATA | flight node not running; channel mismatch; MACs swapped in `radio_config`; boards too close (try ≥ 30 cm apart) or too far |
| `rejected (version=...)` grows | the two boards run different `esp32/lib` versions: redeploy both |
| `rejected (crc=...)` / `foreign` grows | interference or another ESP-NOW sender on the channel; try another `ESPNOW_CHANNEL` on **both** boards |
| I2C scan empty | SDA/SCL swapped, missing 3.3 V/GND, no pull-ups |
| >32 I2C addresses | SDA/SCL shorted or pull-ups missing |
| Only one BMP280 found | same address strap on both (most likely), or one unpowered (§6.3) |
| IMU UNKNOWN_CHIP | the GY-91 carries a chip outside the known list: record the WHO_AM_I hex, do not force it |
| IMU IMPLAUSIBLE "all 0" | chip asleep/reset (the driver re-inits automatically) or a bus fault |
| INA219 DISABLED | intended until the monitored circuit is declared (§6.4) |
| SD FAIL at mount | no card, not FAT-formatted, SPI wiring, supply |
| `FSW_REFUSED` flag | expected today (§8) |

## 11. Known limitations and unresolved assumptions

- **No hardware result exists.** All 138 `esp32/tests` and every existing suite ran on CPython 3.12 on a laptop. **MicroPython parsing and the MicroPython `espnow`/`machine.SDCard` APIs are [ASSUMPTION]**: they are recalled, not run (no `micropython` or `mpy-cross` binary is installed here). The first board run is the real test.
- Register maps, scale factors and the BMP280 compensation are recalled from the datasheets (§6).
- The esptool v4/v5 output parsing is based on recalled output formats. It fails loudly if it cannot find a MAC.
- ESP-NOW range, link-gap and enclosure performance are unmeasured (OD-078). Channel 1 is a bench default.
- Telemetry schema v1 is a proposal (OD-079). It does not yet carry team id, event latches, switch states or actuator-decision bits.
- The flight software cannot run on the board until OD-080 is resolved. The guards that block it were left unchanged on purpose.
- No hardware watchdog (OD-071), no SD flight logging, no limit-switch, buzzer or servo code.
- Sequence numbers are not wrap-safe beyond 2^32 frames (34 years at 4 Hz).
- Duplicate I2C addresses cannot be detected electrically (§6.3).
