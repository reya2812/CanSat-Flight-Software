# MicroPython flight software (port in progress, D-017)

The team switched the flight-software environment to MicroPython (D-017, approver names and date still [TBD]). This folder is the port. `../firmware/` (C++) stays as the **reference implementation** until this port matches it on all 17 synthetic scenarios; then it is archived, not deleted.

**Status:** modules 1-3 of 6.
- **Module 1:** config, types, HAL interfaces, clock, boot-time checks, build scan.
- **Module 2:** sensor validator, event detector (release detection), state machine, recovery manager, flight-software composition.
- **Module 3:** mock sensors, mock actuators, virtual clock, fault injection, flight profile, the 17 SYNTHETIC scenarios, simulation runner, flight-software hook, trace exporter, and the mock-only deployment interlock and actuator manager (OD-070).

On all 17 scenarios the Python simulator's output is byte-identical to the C++ reference: 221 CSV and trace files, plus the matrix.

All 157 C++ test cases in `firmware/test/` have a same-named Python test. `tests/test_cpp_port_coverage.py` enforces this. One case, a C++ compile-time type check, is ported as a test that pins the Python limitation instead.

Nothing here has run on an ESP32 or on MicroPython itself. Only CPython 3.14 on a laptop has been used. All results are **SIMULATED, not hardware validation**.

## Run (laptop, nothing to install)

```sh
cd micropython
python3 -m unittest discover -s tests -t .   # all tests (built-in unittest)
python3 tools/scan_guards.py                 # build-time source scan; exit 1 = fail
python3 tools/parity.py                      # replay C++ traces; exact event/state comparison
python3 tools/sim_runner.py matrix           # every scenario x policy (same commands as firmware sim_runner)
python3 tools/sim_runner.py run-fsw nominal A # one run, flight software in the loop; output under build/
python3 tools/parity.py --fma                # diagnosis: emulate the C++ build's fused multiply-add
```

C++ parity traces (reference outputs for later modules) come from `firmware/`:

```sh
cd firmware && make traces                   # build/trace/<scenario>__<policy>.trace and .csv
```

## Layout

| Path | Contents |
|---|---|
| `cansat/core/types.py` | Constants and sample classes. Same numeric codes as `firmware/lib/core/Types.h` (checked by tests that parse the C++ header) |
| `cansat/core/param.py` | `Param`: unset until assigned, no fallback |
| `cansat/core/num.py` | uint32/16/8 wrapping and `f32()` (round to a 32-bit float) |
| `cansat/core/clock.py` | `TicksUptimeClock`: turns a MicroPython ticks counter into the C++ uint32 uptime |
| `cansat/core/sensor_validator.py`, `event_detector.py`, `flight_state_manager.py`, `recovery_manager.py`, `flight_software.py` | Module 2 flight logic (ports of the C++ files of the same names) |
| `cansat/core/fmath.py` | Float32 altitude and acceleration magnitude. Flight code rounds every operation; `accel_mag_fma` reproduces the C++ laptop build's fused multiply-add for diagnosis only |
| `cansat/mock/persistent_store.py`, `cansat/sim/synthetic_flight_params.py` | Mock record store (corrupt/erase/write-failure injection) and the SYNTHETIC parameter set |
| `tools/parity.py`, `tools/gen_golden_m2.cpp`, `tests/golden_m2.txt` | Trace replay, and C++ reference values for float and CRC maths |
| `cansat/core/deployment_interlock.py`, `actuator_manager.py` | Mock-only downstream interlock and the only caller of `ActuatorDriver.apply()` (OD-070, [PROPOSED] gate rules) |
| `cansat/mock/` | `rng`, `virtual_clock`, `truth`, `fault_injector`, `sensors` (mock BMP280/MPU6050/INA219/switches), `actuators` (mock driver, scripted connection, mock arming), `memory_log`, `persistent_store`, `ticks` |
| `cansat/sim/` | `scenario`, `scenarios` (17 SYNTHETIC), `flight_profile`, `runner`, `fsw_hook`, `trace`, `file_log`, `synthetic_flight_params`, `sim_math` (laptop-only exact C++ float32: correctly rounded FMA and the C library `powf` via ctypes, used only so sensor frames match the C++ reference) |
| `tools/sim_runner.py` | Simulation CLI (`list`, `run`, `run-all`, `run-fsw`, `matrix`, `trace`, `trace-all`) |
| `cansat/config/` | `build_flags.py`, `hardware_config.py` (all pins TBD), `flight_params.py` (no defaults) |
| `cansat/hal/interfaces.py` | HAL base classes mirroring `HalInterfaces.h` |
| `cansat/mock/ticks.py` | CPython emulation of `time.ticks_ms()` / `ticks_diff()` |
| `cansat/guards.py`, `cansat/boot_checks.py` | Boot-time refusal checks and the shared source rules |
| `tools/scan_guards.py` | Build-time source scan |
| `tests/` | `unittest` tests; `tests/cpp_ref.py` reads the C++ headers for parity |

## The safety guards are WEAKER than in C++

C++ refuses to **compile** when physical actuators are enabled (`#error`), when a required pin is TBD on a hardware build (`static_assert`), or when flight parameters are unapproved. A program that does not compile cannot run. Python has no compile step, so this port uses:

1. **Boot-time checks** (`cansat/boot_checks.py`). They refuse to start when:
   - the physical-actuator flag is not False;
   - a registered actuator driver reports itself physical (or cannot answer);
   - the package source contains actuator output code:
     - `PWM` or DAC anywhere;
     - any reference to a `PIN_SERVO_*` or `PIN_BUZZER_*` pin outside `hardware_config.py`;
     - an `is_physical()` returning True;
     - a digital output (`Pin.OUT`, `Pin.OPEN_DRAIN`) anywhere except `cansat/hal_mp/`, and there only on a line that names exactly one of `PIN_SD_CS` or `PIN_HC12_SET`, with no literal pin number;
   - a resolved SD-CS or HC-12-SET pin shares a GPIO with an actuator pin (B5; skipped while pins are TBD);
   - any precompiled `.mpy` file is present (it cannot be scanned);
   - on hardware only: a required pin is TBD, the HC-12 baud is unset, or flight parameters are unapproved.
2. **A build scan** (`tools/scan_guards.py`, 15 rules) that exits 1 on any violation.

What makes them weaker:

- They only protect if they are run. Editing or skipping `enforce_boot_checks()` or the scan removes them.
- They match listed spellings only. Hardware access via `getattr`, `__import__`, aliases, `eval` or `exec` is not detected. A digital output set with a numeric mode (`Pin(x, 1)`) or a mode held in a variable is not detected, and an allowed output split across several lines is refused.
- The on-board scan reads `.py` sources only.
- MicroPython parsing of these files is **UNVERIFIED**: no `micropython` or `mpy-cross` is installed here, so only the CPython parser has checked them.

There is **no servo or buzzer output code** in this port, by decision (D-017). The actuator interface has mock implementations only.

## Clock

`TicksUptimeClock` converts `time.ticks_ms()` into the C++ uint32 uptime. It does not assume the tick period: it reads it from the running board with `ticks_add(0, -1) + 1`, the method the MicroPython documentation gives.

The semantics come from the MicroPython source (master, read 2026-11-18) and docs; references are in `cansat/core/clock.py`:
- On the ESP32 port the period comes out as 2^30 ms.
- `ticks_diff()` returns values in [-P/2, P/2 - 1].
- `ticks_add()` raises OverflowError for |delta| >= P/2.

`now_ms()` must run at least every `max_poll_interval_ms()` (P/2 - 1). The CPython emulation (`cansat/mock/ticks.py`) uses the same formulas and is tested at periods 2^4, 2^10 and 2^30.

## Precompiled .mpy files

These are refused at boot because the source scan cannot read them. A hash-manifest option that would allow them is described in docs/OPEN_DECISIONS.md OD-074; it is not implemented.

## Float margins

Run `python3 tools/float_margins.py`. It shows how close the parity scenarios come to each threshold, next to the largest C++/Python disagreement measured. One comparison, the baro drop (OD-075), comes closer than that disagreement.

## Portability rules

No `enum`, `dataclasses`, `typing` or `abc`, no `struct.Struct`, and no return-type annotations. `Param.get()` is always unpacked as `ok, value`; values that a completeness check guarantees are read with `require()`, which raises `ParamUnset`. Core code never imports `time` or MicroPython modules: MicroPython-only modules may appear only under `cansat/hal_mp/`, which does not exist yet. Integer wrap and float32 rounding are explicit (`num.py`). The scan enforces this.
