# 07 — Safety and Fault Handling

## PDR risks
The PDR identifies:
- Parachute failure or tangling.
- Solar-panel deployment failure or snagging.
- Telemetry dropout during descent.
- Premature or failed release detection.
- Insufficient battery capacity.
- Structural damage on landing.

The PDR suggests mitigations including anti-tangle line guides, repeated drop tests, mechanical end stops, ESP-NOW, onboard backup logging, multi-sensor release checks and battery margin. These are design proposals, not verified controls.

## Software fault cases to specify
| Fault | Detection mechanism | Required behaviour | Status |
|---|---|---|---|
| Sensor not detected at startup | Driver/init result | Report fault; define whether mission may arm | TBD |
| Sensor reading invalid/out of range | Validation layer | Mark invalid; do not silently use it | To implement/test |
| Sensor data stale | Timestamp/age check | Mark stale; apply approved degraded policy | TBD |
| ESP-NOW send failure | Radio API result/counters | Continue local logging; count/report failures | To implement/test |
| GCS link lost | Receive/ack policy TBD | Do not make safety-critical behaviour depend on GCS | Design principle; confirm |
| MCU reset | Boot/reset cause and persisted state | Restore safely; do not repeat one-shot action | PDR asks for state restore; design TBD |
| Storage full/failure | Storage API result | Report fault and define retention policy | TBD |
| Actuator command failure | Feedback signal TBD | Record failure; no assumed successful deployment | Feedback hardware TBD |

## Non-negotiable development constraints
- Mock actuators in unit tests and simulation.
- No physical deployment during software-only tests.
- No guessed servo angles, pulse widths, thresholds or delays.
- A lost telemetry link must not be treated as evidence of a flight-state transition.
- A commanded deployment is not the same as confirmed mechanical deployment.
- Reset recovery must be designed to avoid unintended repeated one-shot actions.
- Any hardware test must use a reviewed procedure and human supervision.

## Safety review required
Before any live deployment-related firmware is used, the team must review the actual mechanism, electrical design, safe states, arming/disarming process, fault response and test environment.
