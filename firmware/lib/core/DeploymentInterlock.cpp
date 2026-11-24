#include "DeploymentInterlock.h"

namespace cansat {

DeploymentInterlock::DeploymentInterlock(const FlightParams& flight, const DeploymentInterlockParams& il)
    : complete_(flight.isComplete() && il.isComplete()) {
  if (!complete_) return;
  flight.interlock.min_separation_ms.get(min_sep_ms_);
  il.connection_max_age_ms.get(max_age_ms_);
}

InterlockResult DeploymentInterlock::evaluate(const InterlockInputs& in) const {
  InterlockResult r;
  uint32_t why = 0;
  ActuatorDecision first = ActuatorDecision::ExecutedSimulated;  // placeholder until a gate fails
  auto fail = [&](uint32_t bit, ActuatorDecision d) {
    if (why == 0) first = d;
    why |= bit;
  };

  if (!complete_) fail(kIlParamsIncomplete, ActuatorDecision::BlockedParamsIncomplete);
  if (in.request != ActuatorRequest::ReleaseParachute) {
    // No interlock rule exists for any other actuator yet (OD-037, OD-052).
    fail(kIlUnsupportedRequest, ActuatorDecision::BlockedUnsupportedRequest);
  }
  if (in.state != FlightState::ParachuteDeploy) fail(kIlWrongState, ActuatorDecision::BlockedWrongState);
  if (!(in.one_shot_flags & kOneShotReleaseConfirmed)) {
    fail(kIlReleaseNotConfirmed, ActuatorDecision::BlockedReleaseNotConfirmed);
  }
  if (in.executed_this_boot) fail(kIlAlreadyDone, ActuatorDecision::BlockedAlreadyDone);
  if (complete_ && (in.now_ms < in.release_timer_start_ms ||
                    in.now_ms - in.release_timer_start_ms < min_sep_ms_)) {
    fail(kIlSeparationDelay, ActuatorDecision::BlockedSeparationDelay);
  }

  switch (in.arming.state) {
    case ArmState::Armed: break;
    case ArmState::Disarmed: fail(kIlNotArmed, ActuatorDecision::BlockedNotArmed); break;
    case ArmState::Unknown:
    default: fail(kIlArmUnknown, ActuatorDecision::BlockedNotArmed); break;
  }

  const ConnectionAssessmentSample& c = in.connection;
  switch (c.value) {
    case ConnectionAssessment::Separated: break;
    case ConnectionAssessment::Connected:
      fail(kIlConnConnected, ActuatorDecision::BlockedInterlockMounted);
      break;
    case ConnectionAssessment::Indeterminate:
      fail(kIlConnIndeterminate, ActuatorDecision::BlockedConnectionIndeterminate);
      break;
    case ConnectionAssessment::Invalid:
      fail(kIlConnInvalid, ActuatorDecision::BlockedConnectionInvalid);
      break;
    case ConnectionAssessment::Unavailable:
    default:
      fail(kIlConnUnavailable, ActuatorDecision::BlockedConnectionUnavailable);
      break;
  }
  // Time consistency applies to any assessment that claims a value.
  if (c.value != ConnectionAssessment::Unavailable) {
    if (c.t_ms > in.now_ms) {
      fail(kIlConnFutureTimestamp, ActuatorDecision::BlockedConnectionStale);
    } else if (complete_ && in.now_ms - c.t_ms > max_age_ms_) {
      fail(kIlConnStale, ActuatorDecision::BlockedConnectionStale);
    } else if (!complete_) {
      fail(kIlConnStale, ActuatorDecision::BlockedConnectionStale);  // no approved age limit exists
    }
  }

  r.reasons = why;
  r.permitted = (why == 0);
  r.decision = r.permitted ? ActuatorDecision::AuthorizedPendingExecution : first;
  return r;
}

}  // namespace cansat
