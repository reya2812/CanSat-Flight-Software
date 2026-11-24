#!/bin/sh
# Compile-time and source guard checks (Phase 2 steps 1-3, interlock).
# Verifies that unsafe or unresolved configurations FAIL to compile, with the
# expected message, and that the same file compiles in a normal native build.
# Run from firmware/:  sh test/guards/run_guard_checks.sh
set -u
CXX="${CXX:-c++}"
FLAGS="-std=c++17 -fsyntax-only -Iinclude -Iinclude/config -Ilib/core -Ilib/hal"
TU="test/guards/guard_tu.cpp"
pass=0
fail=0

ok()  { echo "[PASS] $1"; pass=$((pass + 1)); }
bad() { echo "[FAIL] $1"; fail=$((fail + 1)); }

# Positive control: native build compiles.
if $CXX $FLAGS "$TU" 2>/dev/null; then ok "native build compiles (control)"; else bad "native build compiles (control)"; fi

expect_fail() {
  name="$1"; pattern="$2"; shift 2
  out=$($CXX $FLAGS "$@" "$TU" 2>&1)
  status=$?
  if [ $status -ne 0 ] && printf '%s' "$out" | grep -q "$pattern"; then
    ok "$name"
  else
    bad "$name (exit=$status; expected error containing: $pattern)"
  fi
}

expect_fail "hardware build fails while pins are TBD" "unresolved (OD-054)" \
  -DCANSAT_TARGET_HARDWARE=1 -DCANSAT_FLIGHT_PARAMS_APPROVED
expect_fail "hardware build fails while HC-12 baud is TBD" "HC-12 UART baud unresolved" \
  -DCANSAT_TARGET_HARDWARE=1 -DCANSAT_FLIGHT_PARAMS_APPROVED
expect_fail "hardware build fails without approved flight params" "Flight parameters are not approved" \
  -DCANSAT_TARGET_HARDWARE=1
expect_fail "enabling physical actuators fails" "CANSAT_ENABLE_PHYSICAL_ACTUATORS=1 rejected" \
  -DCANSAT_ENABLE_PHYSICAL_ACTUATORS=1

# Core, HAL, mocks and simulator must stay Arduino-free (laptop-testable).
if grep -rn "Arduino.h" include lib/core lib/hal lib/hal_mock sim >/dev/null 2>&1; then
  bad "core/hal/mock/sim/config are free of Arduino.h"
else
  ok "core/hal/mock/sim/config are free of Arduino.h"
fi

# Actuator calls (revised with the mock-only ActuatorManager, OD-070):
# exactly one core file may call IActuatorDriver::apply(), and only after its
# interlock; the simulator must not reference the actuator path at all; the
# only mock driver must report isPhysical() == false.
apply_hits=$(grep -rln "\.apply(" lib/core lib/hal_mock sim 2>/dev/null)
if [ "$apply_hits" = "lib/core/ActuatorManager.cpp" ]; then
  ok "only ActuatorManager.cpp calls IActuatorDriver::apply()"
else
  bad "only ActuatorManager.cpp calls IActuatorDriver::apply() (found: $apply_hits)"
fi
if grep -rn "IActuatorDriver\|ActuatorManager\|DeploymentInterlock" sim >/dev/null 2>&1; then
  bad "simulator does not reference the actuator path"
else
  ok "simulator does not reference the actuator path"
fi
if grep -rn "isPhysical() const override { return true" lib include sim src >/dev/null 2>&1; then
  bad "no non-test code declares a physical actuator driver"
else
  ok "no non-test code declares a physical actuator driver"
fi
# The flight state machine must not reach the actuator path.
if grep -n "IActuatorDriver\|ActuatorManager\|DeploymentInterlock" \
     lib/core/FlightStateManager.h lib/core/FlightStateManager.cpp >/dev/null 2>&1; then
  bad "FlightStateManager does not reference the actuator path"
else
  ok "FlightStateManager does not reference the actuator path"
fi
# No core file may produce a connection assessment (method unresolved, OD-060/OD-068).
if grep -rn ": public IConnectionAssessmentSource\|: public IArmingSource" lib/core include src >/dev/null 2>&1; then
  bad "no firmware implementation of connection assessment or arming exists"
else
  ok "no firmware implementation of connection assessment or arming exists"
fi

# Step 3: the state machine consumes events only; it must not read sensors.
if grep -n "IBarometer\|IImu\|IPowerMonitor\|IDigitalInputs\|SensorFrame\|ValidatedFrame\|Sample" \
     lib/core/FlightStateManager.h lib/core/FlightStateManager.cpp >/dev/null 2>&1; then
  bad "FlightStateManager does not reference sensors or samples"
else
  ok "FlightStateManager does not reference sensors or samples"
fi

# No physical driver directory may exist yet.
if [ -d lib/hal_esp32 ]; then
  bad "no physical driver library (lib/hal_esp32) exists yet"
else
  ok "no physical driver library (lib/hal_esp32) exists yet"
fi

# SYNTHETIC_* values must never appear in firmware config or core code.
if grep -rn "SYNTHETIC_" include lib src >/dev/null 2>&1; then
  bad "no SYNTHETIC_ values outside test/ and sim/"
else
  ok "no SYNTHETIC_ values outside test/ and sim/"
fi

echo
echo "guard checks: $pass passed, $fail failed"
[ $fail -eq 0 ]
