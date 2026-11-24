# 09 — Open Questions and Verification Register

## Priority 0 — Required before hardware-dependent firmware
- [ ] Exact ESP32 DevKit board manufacturer/model/revision and pinout?
- [ ] Confirm board labels/markings on both flight and ground-station boards.
- [ ] Which GPIOs are allocated to I2C, HC-12 UART, SD SPI, servos, limit switches and buzzers?
- [ ] Which HC-12 module pins are exposed and what is its exact supply/logic specification?
- [ ] HC-12 AT configuration: channel, UART baud rate, air data rate, transmit power and FU mode?
- [ ] Which BMP280 address is actually present: 0x76 or 0x77?
- [ ] Verify MPU6050 address 0x68 and INA219 address 0x40 on the assembled I2C bus.
- [ ] Confirm whether I2C address conflicts exist on the final wiring.
- [ ] Draw the complete power tree for both 18650 cells, TP4056 boards, switches and MT3608 converters.
- [ ] Identify which power rail supplies the ESP32, HC-12, sensors, SD card, servos and buzzers.
- [ ] Confirm servo assignment: which SG90 operates which mechanism? Are all three flight hardware?
- [ ] Confirm whether the two limit switches are mount-release detection, mechanism end stops, or other signals.
- [ ] Confirm how the two buzzers are used and whether a transistor/driver is required.
- [ ] Confirm solar panel role: sensing only, charging, or another function? What regulation/charging hardware is used?
- [ ] Confirm SD module wiring, SPI pinout, level-shifter compatibility and filesystem approach.

## Priority 1 — Software behaviour and protocol
- [ ] Final sampling rate for each sensor?
- [ ] Final telemetry rate? PDR target is 4 Hz in several places, but its power table contains a 1 Hz label.
- [ ] Final telemetry packet fields, units, timestamp format, sequence counter and error handling?
- [ ] Does the ground station forward HC-12 packets to laptop USB serial, and at what baud rate?
- [ ] Does the ground station need commands sent back to the CanSat, or is it receive-only?
- [ ] What are the exact release-detection conditions and debounce/filtering rules?
- [ ] What are the approved parachute release conditions, timing and confirmation mechanism?
- [ ] Which servo is assigned to parachute release, if any?
- [ ] Is solar-panel deployment passive spring-assisted as the PDR says, or is a servo involved?
- [ ] What are the landing detection conditions and buzzer activation policy?
- [ ] What data must be logged to SD, and what happens if the card is missing/full?

## Priority 2 — Verification evidence
- [ ] Actual sensor readings and calibration/offset measurements?
- [ ] HC-12 range test and packet-loss results using the final antenna installation?
- [ ] Measured 5 V rail stability during simultaneous radio transmission and servo load?
- [ ] Measured battery runtime and brownout behaviour?
- [ ] SD write/read and power-interruption tests?
- [ ] Limit-switch debounce and repeatability tests?
- [ ] Servo mechanism bench-test evidence?
- [ ] Solar panel deployment and recovery buzzer tests?

## Reconciled source status
The user confirms there is no newer PDR. The latest available PDR remains the mission/design reference, but the current explicit hardware baseline supersedes:
- ESP-NOW 2.4 GHz with HC-12 433 MHz UART.
- GY-91 / MPU9250 with MPU6050 / GY-521.
- PDR pressure/temperature arrangement with BMP280 pressure + temperature.
- Generic ESP32 description with ESP32 DevKit boards for flight and ground station.

The PDR's mission profile, parachute design assumptions and descent targets remain source-derived design intent unless the team explicitly revises them.

## How to close an item
Record who confirmed it, date, evidence/source, exact part marking or datasheet, and affected docs/code. Do not convert an assumption into a confirmed fact.
