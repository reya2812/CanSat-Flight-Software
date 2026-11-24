# 04 — System Architecture (Initial Proposal)

This is a proposed software decomposition, not an approved flight design. The interfaces should be agreed before parallel implementation.

## Proposed modules

1. **Board / hardware configuration**
   - Board-specific pin definitions and peripheral setup.
   - Must be based on the exact board model and wiring.

2. **Sensor drivers**
   - GY-91 / IMU / pressure interface (exact chip identity TBD).
   - BME280 interface.
   - INA219 interface.

3. **Sensor data model and validation**
   - Common timestamped sample structures.
   - Validity, freshness and range checks.
   - No unverified calibration assumptions.

4. **Flight-state manager**
   - Owns the software state and approved state transitions.
   - Receives observations/events; should not directly manipulate hardware pins.

5. **Deployment / actuator interface**
   - Interface only at first.
   - Simulation/mock implementation is the default for development.
   - Physical actuator implementation requires confirmed wiring and an approved safety procedure.

6. **Telemetry**
   - Serialisation and ESP-NOW transmission.
   - Explicit packet schema, version and units.

7. **Onboard logging / persistence**
   - Store timestamped measurements, events and faults.
   - Storage medium and power-loss behaviour TBD.

8. **Ground-station interface**
   - PDR proposes an ESP32 USB receiver at 115200 baud and a Python GUI.
   - Receiver implementation and GUI protocol TBD.

9. **Diagnostics and fault handling**
   - Startup checks, sensor faults, radio faults, watchdog/restart policy and event history.

## Dependency direction
Hardware drivers provide readings to the data layer. The flight-state manager consumes validated observations. Telemetry and logging consume state/data snapshots. The state manager requests actions through an actuator abstraction; it should not depend on a particular servo library.

## Simulation-first principle
The same state-management logic should be testable with simulated sensor observations and mock actuators. A simulation must never be able to energise a physical servo.

## Architecture questions
- Which tasks run synchronously versus on separate FreeRTOS tasks?
- What is the approved sampling schedule?
- What is the time source and timestamp resolution?
- What persistence medium is available?
- What are the GCS packet framing and command requirements?
These remain open until the hardware and software interfaces are confirmed.
