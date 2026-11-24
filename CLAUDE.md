# Instructions for Claude Code

## Project
Onboard flight software and ground-station software for a CanSat/PocketQube mission. The latest available PDR is in `references/CanSat_PDR.pdf`; the user's explicit hardware baseline is documented in `docs/03_hardware_specification.md`.

## Confirmed baseline
- Two ESP32-WROOM-32 development boards, 30-pin, CP2102, Type-C: one CanSat flight computer and one USB-connected ground-station board.
- MicroPython is the selected development environment (D-017, supersedes Arduino C++ / D-003). The C++ code in `firmware/` is the reference implementation until the port in `micropython/` matches it on all 17 synthetic scenarios; then archive it, never delete it. Approver names and date for D-017 are still [TBD].
- Radio: **ESP-NOW directly between the two ESP32s** (D-020, user-directed 2026-11-24; approvers [TBD]). The HC-12 modules are not used. Bring-up/telemetry code lives in `esp32/` (D-021), outside the guarded `micropython/` tree.
- BMP280 pressure/temperature sensor; I2C address 0x76 or 0x77.
- MPU6050 / GY-521 IMU; I2C address 0x68.
- INA219 voltage/current monitor; I2C address 0x40, 0.1 Ω shunt, stated up to 3.2 A.
- Three SG90 180-degree servos are listed; exact mechanism assignments are not yet confirmed.
- Two 18650 1S cells, two single-cell holders, two TP4056 + DW01 boards, three MT3608 boost converters, two lever micro limit switches, two 5 V active buzzers, one SPI Micro-SD module and one 16 GB card are specified.

## Source-of-truth rules
1. User-confirmed component baseline in `docs/03_hardware_specification.md`.
2. Approved requirements and decisions in `docs/`.
3. Latest PDR as preliminary mission/design reference; some component choices are superseded by the confirmed baseline.
4. Recommendations must be labelled as recommendations.
Never treat invoice listings as proof of installation or test success.

## Unresolved items
- Exact ESP32-WROOM-32 development-board make/model/revision and GPIO pinout.
- ESP-NOW link performance (range, gap, enclosure attenuation) and the final Wi-Fi channel (OD-078). HC-12 items are moot while D-020 stands.
- Exact BMP280 address (0x76 or 0x77).
- Power topology for the two independent 1S cells, chargers, switches and boost converters.
- Servo-to-mechanism assignment and safe mechanical/electrical limits.
- Limit-switch roles and wiring.
- Buzzer roles and driver circuit.
- Solar panel electrical role and charging/regulation architecture.
- Final telemetry packet schema, rate and ground-station behaviour.

## Required working style
- Inspect relevant docs before proposing changes.
- For multi-file or architectural work, propose a plan first.
- Do not invent GPIOs, thresholds, sensor calibration, HC-12 AT settings, servo pulse widths, power topology or flight timing.
- Ask before changing hardware interfaces, flight logic or safety behaviour.
- Keep sensor drivers, flight-state logic, telemetry, persistence and actuator control modular.
- Use mock sensors and mock actuators for software tests.
- Keep simulator and hardware implementations separate.
- Physical actuator outputs must never be triggered by ordinary tests or simulation.
- Run tests and report exact commands and outcomes. Never claim tests passed unless run.
- Summarise files changed, assumptions, test results and open questions.
- Record important engineering decisions in `docs/decisions/DECISIONS.md`.
