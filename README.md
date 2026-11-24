# CanSat Flight Software

Initial documentation workspace for the CanSat onboard firmware and ground-station software.

## Current baseline
- Existing code: none; starting from scratch.
- Firmware: Arduino C++.
- Flight computer: ESP32 DevKit, 30-pin, CP2102, Type-C.
- Ground station: second matching ESP32 DevKit board connected to laptop USB.
- Radio: ESP-NOW directly between the two ESP32s (D-020, 2026-11-24). HC-12 modules not used.
- Board bring-up, ESP-NOW telemetry and diagnostics: `esp32/` — see `docs/10_esp32_espnow_bringup.md`.
- Sensors: BMP280, MPU6050/GY-521, INA219.
- Data logging: Micro-SD SPI module + 16 GB card.
- Actuators: 3 × SG90 servos; exact assignments TBD.
- Release detection: 2 × lever micro limit switches.
- Recovery indication: 2 × 5 V active buzzers.

## Start here
1. Read `CLAUDE.md`.
2. Read `docs/01_project_overview.md`.
3. Read `docs/02_system_requirements.md`.
4. Read `docs/03_hardware_specification.md`.
5. Resolve Priority 0 questions in `docs/09_open_questions.md`.
6. Do not write hardware-dependent firmware until GPIO mapping and power topology are confirmed.

## Folder map
- `docs/`: project and software specifications.
- `docs/decisions/`: engineering decision log.
- `hardware/`: pinout and wiring.
- `src/`: firmware.
- `tests/`: automated tests.
- `simulator/`: software-only simulation.
- `data/`: sample/synthetic data.
- `references/`: original PDR and procurement invoice photo.
- `demo/`: actual agent experiment logs and evidence.

## Source discipline
The latest available PDR remains the mission/design reference. The user's explicit hardware baseline supersedes selected PDR component choices. Clearly label Confirmed, PDR proposal, Assumption and TBD. Never invent hardware details or claim tests have passed without evidence.
