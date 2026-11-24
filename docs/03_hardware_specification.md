# 03 — Hardware Specification and Procurement Baseline

**Revision:** 18 November 2026 — updated from the user's explicit component specification.

## Status terminology
- **User-confirmed baseline:** the component and role specified by the user below.
- **Invoice-listed:** appeared on the original procurement invoice.
- **TBD:** physical details, wiring, settings or implementation still require verification.
- This is a procurement/design baseline, not proof that every component has been received, installed or tested.

## 1. Confirmed system configuration

| Subsystem | Role | Component / specification | Qty |
|---|---|---|---:|
| Microcontroller | CanSat flight computer | ESP32 dev board, ESP32-WROOM-32, 30-pin, CP2102, Type-C | 1 |
| Microcontroller | Ground station | Same ESP32 board, powered from laptop USB | 1 |
| Telemetry | CanSat ↔ ground station | HC-12 433 MHz wireless serial module, SI4463, UART, approx. 1 km open-air claim, spring antenna | 2 |
| Sensor | Pressure + temperature | BMP280, I2C address 0x76/0x77 | 1 |
| Sensor | IMU | MPU6050 / GY-521, I2C address 0x68 | 1 |
| Actuator | Servo | SG90 micro servo, 9 g, 180°, plastic gears | 3 |
| EPS | Battery | 18650 Li-ion, 2500 mAh, 1S, 3.7 V nominal, approx. 45 g | 2 |
| EPS | Battery holder | Single-cell, covered holder with leads | 2 |
| EPS | Charging/protection | TP4056 charger + DW01 protection, 1 A, Type-C | 2 |
| EPS | Main power switch | Mini toggle or rocker, rated 3 A or higher | 2 |
| EPS | Voltage/current measurement | INA219, I2C 0x40, 0.1 Ω shunt, up to 3.2 A | 1 |
| EPS | Boost converter | MT3608, input 2–24 V, trim to 5.0 V output | 3 |
| EPS | Bulk capacitor | 470 µF, 16 V, radial electrolytic | 5 |
| EPS | Decoupling capacitor | 100 nF ceramic, through-hole | 10 |
| EPS | Wiring | 22 AWG solid hookup wire, multi-colour, red/black minimum | 1 set |
| EPS | Connectors | JST-PH 2.0, 2-pin pairs with wire, male + female | 5 pairs |
| EPS | Bench supply | MB102 breadboard power supply, USB input, 5 V / 3.3 V rails | 1 |
| Solar | Solar panel | Mini panel, 4 V, 100 mA; dimensions must fit CanSat | 2 |
| Data logging | SD interface | Micro-SD SPI module with level shifter, 3.3/5 V | 1 |
| Data logging | Storage | Micro-SD card, 16 GB, Class 10, FAT32 | 1 |
| Recovery | Audible locator | Active buzzer, 5 V, breadboard pins | 2 |
| Release detection | Separation switch | Micro limit switch, lever type | 2 |
| Prototyping | Breadboard | 830/840-point full-size | 3 |
| Prototyping | Jumper wires | Male-to-male, 40 pcs, 20 cm | 2 packs |
| Prototyping | Jumper wires | Male-to-female, 40 pcs, 20 cm | 2 packs |
| Prototyping | Jumper wires | Female-to-female, 40 pcs, 20 cm | 1 pack |
| Prototyping | Header pins | Male, 40×1, 2.54 mm straight | 4 |
| Prototyping | Resistors | Assorted 1/4 W; include 100 kΩ, 10 kΩ, 4.7 kΩ, 330 Ω | 1 kit |
| Prototyping | LEDs | Assorted 5 mm | 1 pack |
| Programming | USB cable | USB Type-C data cable, not charge-only | 2 |
| Tools/storage | Enclosure/box | Box to accommodate components | TBD |

## 2. Confirmed communication architecture

> **Update 2026-11-24 (D-020):** at the user's explicit direction the telemetry link is now **ESP-NOW directly between the two ESP32-WROOM-32 boards** (2.4 GHz, no router, no internet). The HC-12 modules are not used. The HC-12 text below is kept for history and is **superseded** for the current baseline. Implementation: `esp32/`; protocol and bring-up guide: `docs/10_esp32_espnow_bringup.md`. Link performance is not measured (OD-078).


- The CanSat flight computer is one ESP32-WROOM-32 board.
- The ground station is a second ESP32-WROOM-32 board connected to a laptop over USB.
- One HC-12 module is intended at the CanSat end and one at the ground-station end.
- HC-12 communication is UART serial over a 433 MHz radio link.
- The earlier PDR's ESP-NOW 2.4 GHz proposal is superseded by this user-confirmed HC-12 baseline unless the team later changes it.

~~**Do not implement ESP-NOW for this baseline.**~~ (superseded by D-020, 2026-11-24) Implement the radio layer against an abstract serial-radio interface; use HC-12 UART once the exact module pinout, AT configuration and wiring are verified.

## 3. Confirmed sensor architecture

- BMP280: pressure and temperature, I2C address may be 0x76 or 0x77.
- MPU6050 / GY-521: accelerometer and gyroscope, I2C address 0x68.
- INA219: voltage/current monitor, I2C address 0x40, 0.1 Ω shunt, stated current capability up to 3.2 A.

The exact BMP280 address must be detected or confirmed from the board's SDO/ADDR strap and wiring. Do not assume 0x76 without checking.

## 4. Power-system baseline — topology still needs an electrical drawing

The user specifies two 18650 cells, two single-cell holders, two TP4056 charger/protection boards, two or more power switches, and three MT3608 boost modules set to 5.0 V.

This parts list does **not** by itself specify whether the cells are independent 1S supplies, connected in parallel, or used in separate subsystems. Do not assume a 2S pack. Do not connect charger outputs together or combine battery outputs until the actual topology is drawn and reviewed.

Before firmware or wiring decisions, document:
- Which cell powers the flight computer, sensors, radio and each servo.
- Whether each TP4056 board charges a separate cell.
- Whether any outputs share ground or are connected in parallel.
- Which MT3608 feeds which rail/load.
- The actual measured 5 V output and peak-current capability under load.
- Battery protection, undervoltage behaviour and safe charging arrangement.

The stated 3.2 A INA219 range and MT3608 ratings are component-list specifications; validate against actual modules and thermal conditions.

## 5. Actuator and mechanism assignment — unresolved

Three SG90 servos are specified, but their exact assignments are not yet provided. The previous PDR discusses:
- Drone mount release pin.
- Parachute compartment latch/release.
- Spring-assisted passive solar-panel deployment.

Do not assume one servo per function. Obtain a mechanism-to-servo mapping and define which actuators are onboard the CanSat versus part of the drone mounting system.

SG90 servos have plastic gears. Verify the actual mechanical load and suitability before relying on them for any safety-critical release. Never power a servo from an ESP32 GPIO. Servo supply, common ground, signal wiring, safe startup position and mechanical end stops must be reviewed.

## 6. Release detection and recovery

- Two lever-type micro limit switches are specified.
- Their exact mechanical roles, normally-open/normally-closed wiring and pull-up/pull-down circuits are TBD.
- Two 5 V active buzzers are specified for recovery; exact control circuit and purpose are TBD.

## 7. Pinout and wiring table

No GPIO numbers are approved yet. Fill this only after identifying the exact ESP32-WROOM-32 development board and reviewing its pinout.

| Function | ESP32 GPIO | Component | Status |
|---|---|---|---|
| I2C SDA | TBD | BMP280, MPU6050, INA219 | TBD |
| I2C SCL | TBD | BMP280, MPU6050, INA219 | TBD |
| HC-12 UART TX | TBD | HC-12 RXD | TBD |
| HC-12 UART RX | TBD | HC-12 TXD | TBD |
| HC-12 SET | TBD or fixed configuration | HC-12 SET | TBD |
| SD SPI SCK | TBD | SD module | TBD |
| SD SPI MISO | TBD | SD module | TBD |
| SD SPI MOSI | TBD | SD module | TBD |
| SD SPI CS | TBD | SD module | TBD |
| Servo signals 1–3 | TBD | SG90 servos | TBD |
| Limit switch inputs 1–2 | TBD | Lever switches | TBD |
| Buzzer outputs 1–2 | TBD | Active buzzers | TBD |
| Battery / rail sense | TBD | INA219 / power circuit | TBD |

## 8. Electrical and safety cautions

- Confirm the exact ESP32 board pinout and 3.3 V logic before connecting peripherals.
- Confirm HC-12 module supply and logic-level requirements from the exact module documentation; do not assume all breakout boards have identical regulators or pinouts.
- Do not power servos from an MCU GPIO or assume an MT3608 can safely supply all servo peak currents. Measure and validate the rail under realistic load.
- Confirm the 18650 cells are genuine, undamaged and appropriately protected. The topology and charging wiring must be reviewed before use.
- TP4056 + DW01 boards are specified, but their protection and load-sharing behaviour must be checked for the exact board. Do not assume a power-path management circuit.
- The SD adapter's level shifter and 3.3/5 V compatibility must be verified. Ensure its SPI signals are safe for the ESP32.
- Breadboards and jumper wires are for bench development, not automatically appropriate for flight vibration or deployment loads.
- Solar panels are described as 4 V, 100 mA each; confirm their role (measurement/charging/power) and do not connect directly to a battery without a reviewed charging/regulation design.
- Never trigger physical deployment mechanisms during ordinary simulation or automated tests.

## 9. PDR reconciliation

The latest available PDR is still the team's source document, but this confirmed component specification supersedes several earlier selections:
- PDR ESP-NOW 2.4 GHz → HC-12 433 MHz UART.
- PDR GY-91 / MPU9250 → MPU6050 / GY-521.
- PDR pressure/temperature sensor arrangement → BMP280 pressure + temperature.
- INA219 remains, now specified as address 0x40 with 0.1 Ω shunt.
- PDR's broad ESP32 description is refined to ESP32-WROOM-32, 30-pin, CP2102, Type-C.
- Solar panels are now specified as two 4 V, 100 mA mini panels; dimensions and electrical role still need confirmation.
- Limit switches and buzzers are explicitly included in the component baseline.

The PDR's flight sequence, parachute assumptions, descent target and other mechanical requirements should not be considered changed unless separately confirmed.
