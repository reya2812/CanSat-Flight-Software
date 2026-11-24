# 08 — Test and Validation Plan

The PDR proposes bench tests, range tests, solar-panel deployment tests, parachute/drop tests, an integrated 100 m drop and a drone fit check. It lists targets including 4 Hz telemetry, no link gaps over 1 second, at least 150 m range, 10/10 panel deployments under 1 second, parachute inflation within 2 seconds and descent near 3 m/s. The PDR compliance table says these demonstrations were still pending at the time of the review.

## Software-first test stages

### Stage 1 — Pure unit tests
- Sensor data validation: valid, missing, stale and out-of-range samples.
- State manager: every approved transition and rejected transition.
- Telemetry: serialisation/parsing, units, malformed packets and sequence numbers.
- Persistence: save/restore and interrupted-write behaviour.
- Actuator abstraction: mock-only tests; verify no physical output is invoked.

### Stage 2 — Simulation and fault injection
- Replay synthetic ascent, separation, descent and landing traces.
- Inject missing sensor samples, spikes, stale readings and radio loss.
- Verify state transitions and event logging.
- Verify that simulated faults do not trigger physical actuators.

Synthetic traces are useful for software verification, but they do not validate real flight thresholds or parachute behaviour.

### Stage 3 — Hardware bench tests
- Confirm board, sensor wiring, addresses and voltage levels.
- Check sensor values against independent references where practical.
- Measure actual sampling and telemetry rates.
- Test onboard logging and radio interruption/recovery.
- Test actuator interface with a safe, physically isolated setup and reviewed procedure.

### Stage 4 — Integrated and physical validation
Only after design review and appropriate supervision:
- Integrated bench test.
- Mechanical fit and interference checks.
- Controlled deployment tests.
- Drop tests and flight tests under an approved safety plan.

## Test evidence log
For each test record:
- Test ID and requirement IDs.
- Firmware commit/version.
- Hardware revision and wiring.
- Test setup and instruments.
- Input data / conditions.
- Expected result and measured result.
- Pass/fail and reviewer.
- Logs, photos or other evidence.
- Deviations and follow-up actions.

## PDR status note
The PDR compliance table (page 21) marks structure demonstration, solar-panel deployment, live telemetry reception and parachute recovery as not yet compliant/demonstrated; final dimensions and mass were still pending verification. Do not describe these as completed tests without newer evidence.
