// DeploymentInterlock.h — downstream deployment interlock (OD-070). [PROPOSED]
//
// Re-evaluates, at the moment a request would be acted on, whether a
// ReleaseParachute request may proceed. It is independent of the release
// detector: it never sees sensor samples and never trusts the detector's
// latched result. Its only connection input is an ABSTRACT assessment
// (ConnectionAssessmentSample). How that assessment is established is
// unresolved (OD-060, OD-068; candidate architectures A1–A5 all remain open).
//
// Rule: permit only if EVERY gate passes. Each failing gate adds a reason bit;
// the decision code reports the first failing gate in a fixed order.
//   params complete → supported request → state is PARACHUTE_DEPLOY →
//   release confirmed → not already executed → separation delay elapsed →
//   armed → connection assessment is Separated, fresh and time-consistent.
// Unavailable, Invalid, Indeterminate, Connected, stale or future-dated
// assessments all block. [PROPOSED — needs team approval, OD-070]
//
// The interlock decides; it never actuates. ActuatorManager calls it.
#pragma once

#include <stdint.h>

#include "Types.h"
#include "config/FlightParams.h"

namespace cansat {

// Snapshot of what the interlock looks at. Filled by ActuatorManager.
struct InterlockInputs {
  ActuatorRequest request = ActuatorRequest::ReleaseParachute;
  uint32_t now_ms = 0;
  FlightState state = FlightState::PowerOnSelfCheck;
  uint8_t one_shot_flags = 0;            // as held by the state machine
  uint32_t release_timer_start_ms = 0;   // FlightStateManager::releaseTimerStartMs()
  bool executed_this_boot = false;       // ActuatorManager's own one-shot record
  ArmingSample arming;
  ConnectionAssessmentSample connection;
};

struct InterlockResult {
  bool permitted = false;
  ActuatorDecision decision = ActuatorDecision::BlockedParamsIncomplete;
  uint32_t reasons = 0;  // InterlockReason bits
};

class DeploymentInterlock {
 public:
  DeploymentInterlock(const FlightParams& flight, const DeploymentInterlockParams& il);

  InterlockResult evaluate(const InterlockInputs& in) const;
  bool configured() const { return complete_; }

 private:
  bool complete_ = false;
  uint32_t min_sep_ms_ = 0;
  uint32_t max_age_ms_ = 0;
};

}  // namespace cansat
