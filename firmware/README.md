# Firmware (CanSat flight computer)

**Current state:**
- **Phase 2 step 1:** config, common types and HAL interfaces.
- **Phase 2 step 2:** sensor mocks and the simulation environment.
- **Phase 2 step 3:** the flight state machine, run against simulated inputs only.
- **Rev 5:** a mock-only downstream deployment interlock and actuator manager (OD-070), and recovery-fault scenarios (OD-069). This is isolated software work, **not** hardware integration.

There are still no physical sensor drivers and no physical actuator code. **Physical actuation is disabled:** the state machine can emit a `ReleaseParachute` *request*. The simulator only logs it as `NOT_EXECUTED`. `ActuatorManager` exists only for tests with `MockActuatorDriver`; it refuses any driver that reports `isPhysical()`, and the simulator does not use it.

## Run (laptop, no hardware, nothing to install)

```sh
cd firmware
make all-checks          # unit tests (steps 1-3) + compile-time guard checks
make sim                 # run every SYNTHETIC scenario -> build/sim/<name>.csv + summaries
make sim-one SCEN=nominal
make matrix              # every scenario x every OD-060 policy, flight software in the loop
./build/sim_runner run-fsw stuck_switch_released A   # one run, policy A/B/C/G
./build/sim_runner list  # list scenarios
make traces              # parity traces for the MicroPython port (D-017) -> build/trace/
```

Every simulation result is **SIMULATED, not hardware validation**. All sensor values in scenarios are **SYNTHETIC**.

## Layout

| Path | Contents |
|---|---|
| `include/config/` | `BuildFlags.h`, `HardwareConfig.h` (all pins TBD), `FlightParams.h` (no defaults) |
| `lib/core/` | `Param.h`, `Types.h`, `Altitude.h`, `SensorValidator`, `EventDetector`, `RecoveryManager`, `FlightStateManager`, `FlightSoftware` (composition), `DeploymentInterlock` and `ActuatorManager` (mock-only, OD-070) |
| `lib/hal/` | `HalInterfaces.h` |
| `lib/hal_mock/` | `MockPersistentStore` (record survives simulated resets), `VirtualClock` (truth time + device uptime, simulated reset), `Rng`, `TruthSource`, `FaultInjector`, `MockSensors` (BMP280, MPU6050, INA219, switches), `MemoryLogSink`, `MockActuators` (mock driver, scripted connection assessment, mock arming) |
| `sim/` | `Scenario`, `FlightProfile` (scripted truth trajectory), `SimRunner` (CSV log + summary, optional hook), `FswHook` (flight software in the loop; requests logged only), `FileLogSink`, `sim_main.cpp` (CLI) |
| `sim/scenarios/` | `SyntheticScenarios.cpp` (13 scenarios + 4 recovery-fault HAZARD scenarios) and `SyntheticFlightParams.cpp`: the only places that hold numbers, all named `SYNTHETIC_*` |
| `test/` | Test harness, `test_step1_config_types.cpp`, `test_step2_sim.cpp`, `test_step3_fsm.cpp`, `test_step3_review.cpp`, `test_interlock.cpp`, `test_recovery_faults.cpp` (INVARIANT_ vs HAZARD_ tests), `guards/` |

## Log format (`build/sim/<scenario>.csv`)

- **Header:** `#` comment lines (SIMULATED/SYNTHETIC banner, scenario, description), then a CSV header.
- **One row per simulated tick**, with these columns:
  - truth time, boot count and device uptime;
  - the scripted segment, plus truth altitude, vertical speed and mounted state (simulation ground truth only; flight software never sees these);
  - each sensor's reading and validity flag (IMU also has a saturation flag);
  - raw switch levels;
  - active faults;
  - events (`SEGMENT`, `MARK`, `FAULT_ON`/`FAULT_OFF`, `RESET`, `BOOTING`, `BOOT_COMPLETE`, `BEGIN`).
- **`MARK:` lines are script annotations**, not flight-software events.
- **Health columns (Rev 6):** `baro_comm_ok`, `baro_data_ready`, `imu_comm_ok`, `imu_data_ready`, `pwr_comm_ok`, `pwr_data_ready` sit between `sw2_raw` and `active_faults`.

## Parity trace (`build/trace/<scenario>__<policy>.trace`, Rev 6)

Machine-readable reference output for the MicroPython port: every sensor frame at full float32 precision, boots, resets, store faults, every flight-software event and the state after each tick. Format: `sim/TraceExporter.h`. The C++ code is the reference implementation until the port matches it (D-017).
