# 01 — Project Overview

## Mission
Develop the onboard software for a CanSat/PocketQube mission that collects flight data, transmits telemetry to a ground station, supports recovery and manages the approved mission mechanisms.

The latest available PDR describes a drone carrying the CanSat to approximately 100 m AGL before release. The PDR remains the mission reference; the user's confirmed component baseline supersedes several PDR component choices.

## Confirmed development setup
- Existing code: none; starting from scratch.
- Firmware language/framework: Arduino C++.
- CanSat flight computer: ESP32 DevKit, 30-pin, CP2102, Type-C.
- Ground station: second matching ESP32 DevKit board connected to laptop USB.
- Radio: HC-12 433 MHz UART modules, one at each end.
- Sensors: BMP280 (pressure/temperature), MPU6050/GY-521 (IMU), INA219 (voltage/current).
- Storage: Micro-SD SPI module and 16 GB card.
- Actuators: three SG90 servos listed; exact mechanism assignments TBD.
- Release detection: two lever micro limit switches listed.
- Recovery: two 5 V active buzzers listed.

## Software scope
1. Initialise the flight computer and peripherals.
2. Acquire, timestamp and validate sensor readings.
3. Manage the approved flight-state machine.
4. Record release and deployment events.
5. Control approved mechanisms through an actuator abstraction.
6. Transmit telemetry over HC-12 UART to the ground-station ESP32.
7. Forward received telemetry from the ground station to the laptop over USB serial.
8. Log flight data to Micro-SD.
9. Handle faults, radio interruptions and restart recovery.

## Important boundaries
- The exact GPIO map and power wiring are not yet confirmed.
- Servo assignments and deployment rules are not yet confirmed.
- HC-12 settings and final telemetry schema are not yet confirmed.
- Do not assume a solar charging topology merely because solar panels are listed.
- No physical deployment testing without a reviewed procedure and responsible supervision.
