// SyntheticFlightParams.cpp
//
// !!! EVERY VALUE IN THIS FILE IS SYNTHETIC !!!
// Chosen only so the SYNTHETIC scenarios exercise each code path. They are not
// derived from test data and are NOT candidate flight values (OD-057, OD-060).
#include "SyntheticFlightParams.h"

#include <stdint.h>

namespace cansat {
namespace sim {
namespace {
const uint32_t SYNTHETIC_DEBOUNCE_MS = 100;
const bool SYNTHETIC_SWITCH_OPEN_IS_HIGH = true;  // matches the SYNTHETIC mock wiring (closed = LOW)
const float SYNTHETIC_FREEFALL_MAX_G = 0.3f;
const uint32_t SYNTHETIC_FREEFALL_MIN_MS = 150;
const float SYNTHETIC_BARO_MIN_DROP_M = 1.0f;
const uint32_t SYNTHETIC_BARO_WINDOW_MS = 500;
const uint32_t SYNTHETIC_CONFIRM_WINDOW_MS = 1000;
const uint32_t SYNTHETIC_STALE_MS = 200;
const uint32_t SYNTHETIC_MIN_SEPARATION_MS = 300;
const uint32_t SYNTHETIC_FALLBACK_DELAY_MS = 300;
const uint32_t SYNTHETIC_SELFCHECK_SAMPLES = 10;
const bool SYNTHETIC_SELFCHECK_REQUIRE_POWER = false;
const float SYNTHETIC_ASCENT_GAIN_M = 20.0f;
const uint32_t SYNTHETIC_ASCENT_CONFIRM_MS = 500;
const float SYNTHETIC_CHUTE_OPEN_G = 3.0f;
const uint32_t SYNTHETIC_CHUTE_TIMEOUT_MS = 3000;
const uint32_t SYNTHETIC_DESCENT_CONFIRM_MS = 1000;
const float SYNTHETIC_LANDED_MAX_ALT_ABOVE_GROUND_M = 5.0f;
const uint32_t SYNTHETIC_IMU_STUCK_IDENTICAL_SAMPLES = 5;
// The store never fails in the scenarios, so this choice has no effect there;
// unit tests exercise BOTH persist-failure policies explicitly (OD-067 undecided).
const PersistFailurePolicy SYNTHETIC_SCENARIO_PERSIST_POLICY = PersistFailurePolicy::RequestAnyway;
const uint32_t SYNTHETIC_LANDED_WINDOW_MS = 3000;
const float SYNTHETIC_LANDED_MAX_ALT_CHANGE_M = 2.0f;
const float SYNTHETIC_LANDED_ACCEL_TOL_G = 0.3f;
}  // namespace

FlightParams syntheticFlightParams(StuckSwitchPolicy policy) {
  FlightParams p;
  p.release.switch_debounce_ms.set(SYNTHETIC_DEBOUNCE_MS);
  p.release.switch1_open_is_high.set(SYNTHETIC_SWITCH_OPEN_IS_HIGH);
  p.release.switch2_open_is_high.set(SYNTHETIC_SWITCH_OPEN_IS_HIGH);
  p.release.switch_vote.set(SwitchVote::Any);
  p.release.freefall_accel_max_g.set(SYNTHETIC_FREEFALL_MAX_G);
  p.release.freefall_min_ms.set(SYNTHETIC_FREEFALL_MIN_MS);
  p.release.baro_min_drop_m.set(SYNTHETIC_BARO_MIN_DROP_M);
  p.release.baro_window_ms.set(SYNTHETIC_BARO_WINDOW_MS);
  p.release.confirm_window_ms.set(SYNTHETIC_CONFIRM_WINDOW_MS);
  p.release.sample_stale_ms.set(SYNTHETIC_STALE_MS);
  p.interlock.min_separation_ms.set(SYNTHETIC_MIN_SEPARATION_MS);
  p.interlock.stuck_switch_policy.set(policy);
  p.interlock.fallback_delay_ms.set(SYNTHETIC_FALLBACK_DELAY_MS);
  p.transitions.selfcheck_samples.set(SYNTHETIC_SELFCHECK_SAMPLES);
  p.transitions.selfcheck_require_power.set(SYNTHETIC_SELFCHECK_REQUIRE_POWER);
  p.transitions.ascent_min_gain_m.set(SYNTHETIC_ASCENT_GAIN_M);
  p.transitions.ascent_confirm_ms.set(SYNTHETIC_ASCENT_CONFIRM_MS);
  p.transitions.chute_open_accel_min_g.set(SYNTHETIC_CHUTE_OPEN_G);
  p.transitions.chute_open_timeout_ms.set(SYNTHETIC_CHUTE_TIMEOUT_MS);
  p.transitions.descent_confirm_ms.set(SYNTHETIC_DESCENT_CONFIRM_MS);
  p.transitions.landed_max_alt_above_ground_m.set(SYNTHETIC_LANDED_MAX_ALT_ABOVE_GROUND_M);
  p.validation.imu_stuck_identical_samples.set(SYNTHETIC_IMU_STUCK_IDENTICAL_SAMPLES);
  p.interlock.persist_failure_policy.set(SYNTHETIC_SCENARIO_PERSIST_POLICY);
  p.transitions.landed_window_ms.set(SYNTHETIC_LANDED_WINDOW_MS);
  p.transitions.landed_max_alt_change_m.set(SYNTHETIC_LANDED_MAX_ALT_CHANGE_M);
  p.transitions.landed_accel_tol_g.set(SYNTHETIC_LANDED_ACCEL_TOL_G);
  return p;
}

std::vector<StuckSwitchPolicy> candidatePolicies() {
  return {StuckSwitchPolicy::StrictSwitchVeto, StuckSwitchPolicy::SensorOverride,
          StuckSwitchPolicy::Vote2of3, StuckSwitchPolicy::DelayedFallback};
}

}  // namespace sim
}  // namespace cansat
