// FlightParams.h — flight thresholds, timings and safety policies.
//
// [TBD] Every value here is undecided (OD-057, OD-060). None has a default.
// Values must come from test data plus team approval. Tests and simulation
// may set them only with constants named SYNTHETIC_*, which live under
// firmware/test or sim/ and are never copied into firmware defaults.
//
// A hardware build fails unless CANSAT_FLIGHT_PARAMS_APPROVED is defined,
// which will only happen once an approved parameter source exists.
#pragma once

#include <stdint.h>

#include "BuildFlags.h"
#include "Param.h"

#if CANSAT_TARGET_HARDWARE && !defined(CANSAT_FLIGHT_PARAMS_APPROVED)
#error "Flight parameters are not approved (OD-057) and the stuck-switch policy is undecided (OD-060). Hardware build refused."
#endif

namespace cansat {

// How the two limit switches combine into "mount open". [TBD] OD-015.
enum class SwitchVote : uint8_t {
  Unset = 0,
  Any = 1,     // either switch open
  All = 2,     // both switches open
  Sw1Only = 3  // second switch has another role
};

// Stuck-switch policy candidates from docs/OPEN_DECISIONS.md §H.
// [TBD] OD-060 — CRITICAL, undecided. No default; Unset is never valid.
// P-D (redundant switches) is expressed via SwitchVote; P-E (external
// confirmation) and P-F (mechanical lanyard) are not software-only policies.
enum class StuckSwitchPolicy : uint8_t {
  Unset = 0,
  StrictSwitchVeto = 1,  // P-A
  SensorOverride = 2,    // P-B
  Vote2of3 = 3,          // P-C
  DelayedFallback = 4    // P-G
};

inline const char* toString(StuckSwitchPolicy p) {
  switch (p) {
    case StuckSwitchPolicy::Unset: return "Unset";
    case StuckSwitchPolicy::StrictSwitchVeto: return "P-A_StrictSwitchVeto";
    case StuckSwitchPolicy::SensorOverride: return "P-B_SensorOverride";
    case StuckSwitchPolicy::Vote2of3: return "P-C_Vote2of3";
    case StuckSwitchPolicy::DelayedFallback: return "P-G_DelayedFallback";
  }
  return "?";
}

// What to do when the parachute-request one-shot flag cannot be persisted
// (OD-067, undecided — no default).
enum class PersistFailurePolicy : uint8_t {
  Unset = 0,
  RequestAnyway = 1,          // queue once; a reset may then lead to a SECOND request
  WithholdUntilPersisted = 2  // retry each tick; no request while storage fails
};

inline const char* toString(PersistFailurePolicy p) {
  switch (p) {
    case PersistFailurePolicy::Unset: return "Unset";
    case PersistFailurePolicy::RequestAnyway: return "RequestAnyway";
    case PersistFailurePolicy::WithholdUntilPersisted: return "WithholdUntilPersisted";
  }
  return "?";
}

// Sensor-health parameters for the validator. All [TBD] (OD-066).
struct ValidationParams {
  // Consecutive IMU samples with all six raw values identical that mark the
  // output as stuck. Relies on real sensor noise ([ASSUMPTION], needs bench data).
  Param<uint32_t> imu_stuck_identical_samples;
  bool isComplete() const { return imu_stuck_identical_samples.isSet(); }
};

// Release-detection parameters. docs/PHASE1_PROPOSAL.md §3.2. All [TBD].
struct ReleaseParams {
  Param<uint32_t> switch_debounce_ms;   // T_DB_SW
  Param<bool> switch1_open_is_high;     // SW_POLARITY[0] (wiring, OD-051)
  Param<bool> switch2_open_is_high;     // SW_POLARITY[1] (wiring, OD-051)
  Param<SwitchVote> switch_vote;        // SW_VOTE
  Param<float> freefall_accel_max_g;    // A_FF
  Param<uint32_t> freefall_min_ms;      // T_FF
  Param<float> baro_min_drop_m;         // DH_MIN
  Param<uint32_t> baro_window_ms;       // W_B
  Param<uint32_t> confirm_window_ms;    // T_CONFIRM
  Param<uint32_t> sample_stale_ms;      // T_STALE

  bool isComplete() const {
    SwitchVote v = SwitchVote::Unset;
    return switch_debounce_ms.isSet() && switch1_open_is_high.isSet() &&
           switch2_open_is_high.isSet() && switch_vote.get(v) && v != SwitchVote::Unset &&
           freefall_accel_max_g.isSet() && freefall_min_ms.isSet() &&
           baro_min_drop_m.isSet() && baro_window_ms.isSet() &&
           confirm_window_ms.isSet() && sample_stale_ms.isSet();
  }
};

// Parachute-request interlock parameters. All [TBD].
struct InterlockParams {
  Param<uint32_t> min_separation_ms;           // T_SEP_MIN [PDR] slide 10 "safe distance"; value TBD (H4)
  Param<StuckSwitchPolicy> stuck_switch_policy;  // OD-060
  Param<uint32_t> fallback_delay_ms;            // T_FALLBACK; required only for DelayedFallback
  Param<PersistFailurePolicy> persist_failure_policy;  // OD-067

  bool isComplete() const {
    StuckSwitchPolicy p = StuckSwitchPolicy::Unset;
    if (!min_separation_ms.isSet() || !stuck_switch_policy.get(p) ||
        p == StuckSwitchPolicy::Unset) {
      return false;
    }
    PersistFailurePolicy pf = PersistFailurePolicy::Unset;
    if (!persist_failure_policy.get(pf) || pf == PersistFailurePolicy::Unset) return false;
    if (p == StuckSwitchPolicy::DelayedFallback && !fallback_delay_ms.isSet()) return false;
    return true;
  }
};

// Non-release state-transition parameters. All [TBD] (MEETING_BRIEF G1).
// The transition *signals* chosen here are a provisional software structure
// pending Gautam's decision; the *values* are undecided and have no defaults.
struct TransitionParams {
  Param<uint32_t> selfcheck_samples;       // consecutive good frames needed for self-check / ground ref
  Param<bool> selfcheck_require_power;     // must INA219 be healthy to pass self-check?
  Param<float> ascent_min_gain_m;          // altitude gain over ground ref that indicates TAKEOFF
  Param<uint32_t> ascent_confirm_ms;       // gain must persist this long
  Param<float> chute_open_accel_min_g;     // |a| at/above this after the request = opening sensed
  Param<uint32_t> chute_open_timeout_ms;   // ALARM ONLY: raise "opening not sensed"; never a transition
  Param<uint32_t> descent_confirm_ms;      // baro descent must persist this long for PANEL_DEPLOY -> DESCENT
  Param<uint32_t> landed_window_ms;        // stability window for TOUCHDOWN
  Param<float> landed_max_alt_change_m;    // altitude band during the window
  Param<float> landed_accel_tol_g;         // | |a| - 1 g | tolerance during the window
  Param<float> landed_max_alt_above_ground_m;  // must be this close to the self-check ground reference

  bool isComplete() const {
    return selfcheck_samples.isSet() && selfcheck_require_power.isSet() &&
           ascent_min_gain_m.isSet() && ascent_confirm_ms.isSet() &&
           chute_open_accel_min_g.isSet() && chute_open_timeout_ms.isSet() &&
           descent_confirm_ms.isSet() && landed_window_ms.isSet() &&
           landed_max_alt_change_m.isSet() && landed_accel_tol_g.isSet() &&
           landed_max_alt_above_ground_m.isSet();
  }
};

// Downstream deployment-interlock parameters (OD-070). All [TBD], no defaults.
// Deliberately NOT part of FlightParams::isComplete(), so the existing
// detector / state-machine completeness rules are unchanged. The interlock
// requires BOTH FlightParams and these to be complete before it can permit.
struct DeploymentInterlockParams {
  // Oldest connection assessment the interlock accepts at authorization and
  // again at execution. Value depends on the assessment method (OD-060/OD-068).
  Param<uint32_t> connection_max_age_ms;
  bool isComplete() const { return connection_max_age_ms.isSet(); }
};

struct FlightParams {
  ReleaseParams release;
  InterlockParams interlock;
  TransitionParams transitions;
  ValidationParams validation;
  bool isComplete() const {
    return release.isComplete() && interlock.isComplete() && transitions.isComplete() &&
           validation.isComplete();
  }
};

}  // namespace cansat
