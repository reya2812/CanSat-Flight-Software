# 05 — Flight State Machine (Draft Only)

The PDR page 19 refers to a flight-software state diagram and describes release detection, sampling/telemetry, deployment triggers and reset recovery. This file turns that intent into a reviewable placeholder. It is not flight-ready logic.

## Candidate states from the PDR flow
- BOOT / POWER_ON_SELF_CHECK
- READY_ON_DRONE
- ASCENT
- RELEASE_DETECTED
- PARACHUTE_DEPLOYMENT
- DESCENT
- LANDED
- FAULT (software safety state to be defined)

## PDR-described observations and events
- Release detection: mount switch opens plus GY-91 acceleration change.
- BME280 descent indication is mentioned as backup confirmation.
- Parachute release is described as occurring after confirmed separation.
- Solar panels are described as spring-assisted and unlocking after detachment.
- Reset recovery: restore last saved state and check sensor/mount status before resuming, to avoid repeated deployment commands.

## Transition table — intentionally incomplete
| Current state | Candidate event/condition | Next state | Action | Missing approval |
|---|---|---|---|---|
| BOOT | Startup begins | SELF_CHECK | Initialise safe outputs and peripherals | Exact safe output states |
| SELF_CHECK | All required checks pass | READY_ON_DRONE | Report ready | Definition of required checks |
| READY_ON_DRONE | Ascent identified | ASCENT | Record ascent state | Ascent detection definition |
| ASCENT | Separation confirmed | RELEASE_DETECTED | Record event/time | Switch wiring and confirmation logic |
| RELEASE_DETECTED | Approved deployment condition met | PARACHUTE_DEPLOYMENT | Request deployment through actuator interface | Exact policy, delay and safety constraints |
| PARACHUTE_DEPLOYMENT | Deployment outcome known | DESCENT | Record outcome | How outcome is sensed/confirmed |
| DESCENT | Landing condition confirmed | LANDED | Record landing | Landing detection definition |
| Any | Critical fault | FAULT or defined degraded behaviour | Record fault; safe response | Fault classification and recovery policy |

## Rules for implementation
- Do not implement thresholds or timers until the team approves them.
- Do not infer a deployment command from one noisy sensor sample.
- Define how contradictory or missing sensor observations are handled.
- Make deployment commands idempotent: a restart must not issue a second deployment command unintentionally.
- Unit tests must use a mock actuator.
- A simulated state transition is not evidence that the physical deployment mechanism is safe.

## Required next artifact
A signed-off transition specification with exact input signals, filtering/debounce, timing, transition guards, timeout behaviour, persistence semantics and test cases.
