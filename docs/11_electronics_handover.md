# 11 — Electronics handover: CanSat flight-board bring-up

**Date:** 2026-11-24 · **From:** software · **To:** electronics team
**Purpose:** the radio link and software are working; the sensors are not responding. The remaining problems are electrical. This brief tells you what is known, what to measure, how to check your work, and how to report back. No coding is needed.

---

## 1. Where things stand

| Item | Status | Evidence |
|---|---|---|
| MicroPython v1.29.0 on both ESP32 boards | ✅ Working | Flashed and verified 2026-11-24 |
| ESP-NOW radio link, flight ↔ ground | ✅ Working on the bench | 3-minute test: 707 packets, 1 lost (0.14 %), signal about −50 dBm, boards a short distance apart |
| I²C sensors (GY-91, BMP280, INA219) | ❌ **No device responds** | Details in §3 |
| SD card | ⏸ Not tested on purpose | Waiting for the module's supply voltage to be confirmed |
| Servo | ⛔ Not used | No software can drive it. Keep it unpowered |

Every result so far is a **bench observation**. Nothing is formally validated yet.

## 2. Hardware you are working with

**Two ESP32 DevKit boards** (30-pin, CP2102 USB, USB-C). They look identical, so tell them apart by MAC address only. Serial port names change every time a board is replugged.

| Board | MAC address | Role |
|---|---|---|
| **FLIGHT** | `4c:c3:82:ec:c9:d8` | Wired to the sensors. All your work is on this board. |
| **GROUND** | `70:4b:ca:02:ce:30` | Laptop USB only. Leave it alone. |

Please label both boards physically with their role and MAC if you haven't already.

**Flight-board wiring.** Pins were reported by the user; the wiring was checked by the user on 2026-11-24.

| Signal | ESP32 pin | Goes to |
|---|---|---|
| I²C SDA | GPIO21 (D21) | GY-91, standalone BMP280, INA219 (one shared bus) |
| I²C SCL | GPIO22 (D22) | same |
| SD SCK / MISO / MOSI / CS | GPIO18 / 19 / 23 / 13 | micro-SD module |
| 3.3 V / GND | 3V3 / GND | breadboard rails |

Expected I²C addresses:

| Device | Address |
|---|---|
| GY-91 IMU | 0x68 or 0x69 |
| BMP280 barometers | 0x76 or 0x77. The GY-91's on-board one and the standalone one **must use different addresses**. |
| INA219 | 0x40 |

> **Do not rewire to different ESP32 pins without telling software.** The software has these pin numbers in `esp32/config/flight_config.py`. If a pin changes there, it must change in the software too.

## 3. What we found (read this before measuring)

The software was checked line by line: the right pins reach the I²C hardware, nothing else uses GPIO21/22, and the bus starts without errors. Both ESP32 hardware I²C controllers and a software I²C were tried, at 100 kHz and 10 kHz.

**Test A — all modules connected:**
- SDA and SCL stayed **HIGH** even with the ESP32's internal pull-down switched on. So a powered pull-up is present on the bus.
- **No address answered** on any scan (6 of 6 empty), including the BMP280 and INA219.

**Test B — GY-91 alone (BMP280 and INA219 disconnected):**
- SDA and SCL went **LOW** with the internal pull-down, and HIGH only with the ESP32's own weak pull-up. So **no powered pull-up comes from the GY-91**, and the lines float.
- The hardware scans reported nearly *every* address (93–109 of them), a different set each time. **These are false.** It is the typical signature of a bus with no proper pull-ups: SDA does not rise in time, so the ESP32 sees fake "acknowledges". The software scan found nothing.
- **The GY-91 has not been detected.**

**What this suggests (not proven):**
1. The pull-ups seen in test A came from the BMP280 or INA219 boards, not the GY-91.
2. The GY-91 either has no pull-ups fitted, or its pull-ups go to a rail that is not powered (for example a regulator output that is not coming up).
3. Even *with* pull-ups present (test A), nothing answered. So the question of whether each module's chip is actually powered applies to **all three modules**, not just the GY-91.

## 4. GY-91 facts and unknowns

There is **no official schematic** for the GY-91. It is a generic module and variants differ, so check what is on *your* board.

| | Status |
|---|---|
| Typical pins: VIN, 3V3, GND, SCL, SDA (plus SDO/SAO, NCS, CSB) | Common on most GY-91 boards. This board's pin is labelled **VIN/VCC**. |
| VIN feeds an on-board low-dropout regulator; 3V3 is its output | Described by vendors, not confirmed for this board |
| Regulator works from a 3.3 V input | **Unknown.** Sources conflict. A low-dropout regulator needs its input above its output plus the dropout, so it may give slightly less than 3.3 V, or not work properly. |
| On-board I²C pull-up resistors fitted | **Unknown.** Sources conflict. Test B suggests none are powered. |
| MPU-9250 chip supply range | 2.4–3.6 V |
| No power LED on this board | Confirmed by the user |

## 5. ⚠️ Safety rules

1. **No 5 V on the GY-91** until its board revision and regulator part are identified.
2. **SDA and SCL must never be pulled up to 5 V.** ESP32 pins are 3.3 V only. Pull-ups go to 3.3 V only. Check this on every module you reconnect (§6, M1).
3. **Servo stays unpowered or disconnected.** Never power a servo from an ESP32 pin.
4. **SD module:** confirm from its own documentation or schematic whether it needs 3.3 V or 5 V on VCC, and whether its signal pins are 3.3 V-safe, **before** software enables the SD test.
5. **Make wiring changes with USB unplugged.**
6. **Never connect two modules at the same I²C address.** Both answer at once and the data is corrupted; software cannot detect it.
7. **Don't erase or reflash the boards.** Software handles that, with built-in checks.

## 6. Tasks, in order

### Step 1 — Measure the GY-91 (multimeter; nothing changed)

The GY-91 stays the only module connected. Black probe on GND at the GY-91.

| ID | What | Power | Expected / meaning |
|---|---|---|---|
| **M1** | SDA to GND and SCL to GND, idle | USB on | Should be ≤ 3.3 V. **Near 5 V: stop and report (safety).** Near 0 V matches "no pull-up". |
| **M2** | VIN/VCC pin to GND | USB on | About 3.3 V. Near 0 V means power isn't reaching the module. |
| **M3** | 3V3 pin to GND (if the board has one) | USB on | About 3.0–3.3 V means the chips are powered. Near 0 V with M2 OK means the regulator isn't passing power. |
| **M4** | Resistance SDA → 3V3 pin, and SCL → 3V3 pin | **USB unplugged** | A few kΩ (e.g. 4.7–10 kΩ) means pull-ups are fitted. Open / MΩ means none are fitted. |
| **M5** | Marking printed on the small regulator chip near VIN; clear photos of both sides of the board | — | Lets software look up the regulator's real specifications |

### Step 2 — Decide and fix, based on Step 1

- **M3 OK but M4 shows no pull-ups:** add **one 4.7 kΩ resistor from SDA to the 3.3 V rail and one from SCL to the 3.3 V rail.** This is standard for this module and electrically safe for the ESP32 (about 0.7 mA when a line is low).
- **M2 OK but M3 near 0 V:** the module isn't powered through its regulator. **Don't** switch to 5 V. Send software the M5 marking and photos, and we decide together.
- **M2 near 0 V:** power isn't reaching the module (rail, jumper or contact). Fix the power path, then repeat Step 1.

### Step 3 — Check your work (one command)

Run the scan in §7. **Good result:** the same small set of addresses on every scan line (for the GY-91: about 0x68 or 0x69, and 0x76 or 0x77), with no flood of addresses. Send the full output to software. **Don't** try to read or configure the sensor yourself; software identifies the chip next.

### Step 4 — Reconnect the other modules one at a time

For each module (standalone BMP280, then INA219):
1. Unplug USB and connect the module.
2. Measure **M1** again (SDA/SCL must be ≤ 3.3 V).
3. Measure the module's own VCC to GND.
4. Run the scan in §7 and save the output.

Each new module should add its address, and nothing else should change. For the BMP280, **write down which address disappears when you disconnect it** (0x76 or 0x77). This maps which physical board is which (checklist H-BARO-1).

### Step 5 — Information software needs

| Item | Why |
|---|---|
| **INA219: which rail it should measure, and how VIN+/VIN− are wired** | Software won't report voltage or current until the monitored circuit is defined. The shunt should be 0.1 Ω: check the "R100" marking. |
| **SD module: supply voltage and level shifting**, from its documentation | Needed before the SD test can be enabled |
| **Power topology:** which battery/converter feeds the ESP32, the sensors and the servo; shared grounds | Open item OD-053 / OD-063 |
| **Servo supply and mechanism mapping** | Open item OD-050. Software does nothing with the servo until approved. |

### Later — radio tests (after sensors work)

| ID | Test |
|---|---|
| H-RF-4 | Outdoor walk to ≥ 150 m line of sight. Record packet loss and signal strength against distance. |
| H-RF-5 | Same with the flight board inside the closed CanSat enclosure |

Software runs the programs; you handle the placement and distances.

## 7. How to run the scan

**One-time setup on the laptop:** Python 3 with `mpremote` and `esptool` (`python3 -m pip install mpremote esptool`), and a copy of the repository. Run commands from the repository's top folder. **Close Thonny or any serial monitor first.**

1. **Find the flight board's port** (names change):
   ```sh
   python3 esp32/tools/esp32_ports.py
   python3 esp32/tools/esp32_ports.py --mp-info /dev/cu.usbserial-XXXX
   ```
   Continue only if it reports **MAC `4c:c3:82:ec:c9:d8`** ("this is the FLIGHT board"). If it says GROUND, try the other port. With only the flight board plugged in there is just one port.
2. **Run the scan** (a few seconds; copies nothing to the board):
   ```sh
   mpremote connect /dev/cu.usbserial-XXXX run esp32/apps/i2c_scan_standalone.py
   ```

The scan only probes addresses. It never writes to a sensor and never drives the servo or any output.

**Reading the output:**

| Line | Meaning |
|---|---|
| `pull-down SDA=1 SCL=1` | A powered external pull-up is present (good) |
| `pull-down SDA=0 SCL=0` | No powered pull-up: lines are floating |
| `EMPTY` | Bus works, nothing answered |
| `FOUND` with a few addresses, the same on every line | Real devices ✅ |
| `FOUND` with ~100 addresses that change between lines | **Fake:** missing or too-weak pull-ups |
| `INIT_ERROR` / `SCAN_ERROR` | Software or bus error: send the output to software |

Known quirk: the summary line "something holds it low" can appear when a line is merely floating. Trust the pull-up/pull-down lines instead. A fix is pending.

## 8. How to report back

For every measurement or test, send:
1. **Date and who measured.**
2. **The ID** from this brief (M1–M5, H-BARO-1, H-RF-4, …).
3. **What was connected** at the time.
4. **The value with units**, or the **full scan output** (copy it all; don't summarise).
5. **Photos** of the board and wiring where relevant.

Results go into the project log (`docs/OPEN_DECISIONS.md`), recorded as bench observations. Software then reruns the diagnostics and sensor identification.

## 9. Don't change these (software-owned)

- Anything under `esp32/`, `micropython/` or `firmware/`, and in particular the pins in `esp32/config/flight_config.py`.
- The firmware on either board. **No erasing or reflashing.**
- `esp32/config/radio_config.py` (the MAC addresses).

If a hardware change affects pins, addresses or supplies, tell software first, so the configuration and safety checks are updated with it.

## 10. Reference documents

| File | What's in it |
|---|---|
| `docs/10_esp32_espnow_bringup.md` | Full bring-up guide: wiring §2, sensor behaviour §6, bench checklist §9, troubleshooting §10 |
| `hardware/pinout.md` | Pin table and ESP32 pin rules (pins to avoid, boot-sensitive pins) |
| `docs/03_hardware_specification.md` | Component list and electrical cautions |
| `docs/OPEN_DECISIONS.md` | Open questions and the log of every bench result so far |
