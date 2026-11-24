# 02 — System Requirements

This is an initial software-facing extraction of the PDR. It does not imply that any requirement has been implemented or demonstrated.

## Requirements

| ID | Requirement / design intent | PDR basis | Verification approach | Status |
|---|---|---|---|---|
| SW-01 | The firmware shall initialise the MCU and required peripherals and report startup/self-check status. | PDR p.19 mentions power-on self-check. | Bench test with recorded startup result. | Proposed; details TBD |
| SW-02 | The firmware shall acquire measurements from the approved sensor set. | PDR pp.15, 19. | Sensor bench test and data plausibility checks. | Sensor details TBD |
| SW-03 | The firmware shall support the PDR target of 4 Hz sensor sampling. | PDR pp.6, 19. | Timestamped sample-rate test. | Target; confirm per sensor |
| SW-04 | The flight computer shall transmit telemetry to the GCS using the HC-12 UART radio link. | User-confirmed hardware baseline; earlier PDR pp.16–17 superseded. | Two-device communication test. | User-confirmed radio component baseline; settings TBD |
| SW-05 | The telemetry design shall target 4 Hz transmission. | PDR pp.6, 17, 19. | Packet-rate and packet-loss test. | Target; conflicts with p.18 power table |
| SW-06 | Telemetry shall include a defined set of measurements, flight state and packet/time information. | PDR p.17. | Packet parser and field validation tests. | Format not final |
| SW-07 | The system shall retain onboard data when the radio link is unavailable. | PDR pp.18, 22; p.19 says onboard logging. | Disconnect/reconnect test and log integrity check. | Storage design TBD |
| SW-08 | The firmware shall detect and record separation/release using approved inputs and logic. | PDR p.19. | Hardware-in-loop or simulated input tests, followed by supervised bench tests. | Logic/thresholds TBD |
| SW-09 | Parachute deployment command shall occur only under an approved and verified deployment policy. | PDR pp.6–7, 10, 19. | Review plus actuator-isolated simulation and controlled bench procedure. | Safety-critical; policy TBD |
| SW-10 | The software shall not repeatedly issue a deployment command after reset or state restoration. | PDR p.19. | Restart/persistence tests with actuator mocked. | Persistence design TBD |
| SW-11 | The software shall record solar-panel deployment as a mission event if a software-observable signal exists. | PDR pp.12, 19. | Interface test after sensor/switch availability is confirmed. | Signal/interface TBD |
| SW-12 | The firmware shall handle missing, invalid or stale sensor readings without silently treating them as valid. | Derived software robustness requirement. | Unit tests with injected invalid/stale data. | To be specified |
| SW-13 | The firmware shall expose diagnostic state/fault information to logs and telemetry. | Derived from PDR risk and telemetry intent. | Fault-injection and packet inspection. | To be specified |

## System-level context from the PDR
- PocketQube form factor: 2P, stated as 50 × 50 × 100 mm.
- Suggested mass range: 300–500 g.
- PDR target descent rate: approximately 3 m/s.
- PDR target parachute opening time: approximately 2 seconds or less.
- PDR target operating sequence: release around 100 m AGL to ground recovery.

These are system/design targets, not firmware constants. Do not encode them as control thresholds without an approved engineering specification.

## Acceptance criteria still needed
For each requirement, the team must approve measurable pass/fail criteria, test conditions, instrumentation and responsible reviewer. In particular, release detection and deployment criteria must not be guessed.
