#include "ActuatorManager.h"

namespace cansat {

ActuatorManager::ActuatorManager(const FlightParams& flight, const DeploymentInterlockParams& il,
                                 IConnectionAssessmentSource& connection, IArmingSource& arming,
                                 IActuatorDriver& driver, IEventSink& events, uint16_t boot_count)
    : interlock_(flight, il),
      connection_(connection),
      arming_(arming),
      driver_(driver),
      events_(events),
      boot_count_(boot_count) {}

void ActuatorManager::report(int phase, ActuatorRequest request, ActuatorDecision d, uint32_t reasons,
                             uint32_t now) {
  Event e;
  e.type = EventType::ActuatorDecided;
  e.t_ms = now;
  e.detail = packActuatorDecision(phase, request, d, reasons);
  events_.onEvent(e);
}

InterlockResult ActuatorManager::check(ActuatorRequest request, const FlightStatusView& fs, uint32_t now) {
  InterlockInputs in;
  in.request = request;
  in.now_ms = now;
  in.state = fs.state;
  in.one_shot_flags = fs.one_shot_flags;
  in.release_timer_start_ms = fs.release_timer_start_ms;
  in.executed_this_boot = executed_;
  in.arming = arming_.read(now);           // fresh read every evaluation
  in.connection = connection_.assess(now);  // fresh read every evaluation
  InterlockResult r = interlock_.evaluate(in);
  if (driver_.isPhysical()) {
    // Physical actuation is disabled (OD-059): refuse regardless of the interlock.
    r.reasons |= kIlPhysicalDriverRefused;
    r.permitted = false;
    r.decision = ActuatorDecision::BlockedBuildDisabled;
  }
  last_ = r;
  return r;
}

Authorization ActuatorManager::authorize(ActuatorRequest request, const FlightStatusView& fs, uint32_t now) {
  Authorization a;
  const InterlockResult r = check(request, fs, now);
  report(0, request, r.decision, r.reasons, now);
  if (!r.permitted) return a;
  a.valid = true;
  a.request = request;
  a.t_ms = now;
  a.boot_count = boot_count_;
  a.serial = next_serial_++;
  outstanding_serial_ = a.serial;  // a newer authorization supersedes an older one
  return a;
}

ActuatorDecision ActuatorManager::execute(const Authorization& auth, const FlightStatusView& fs, uint32_t now) {
  ActuatorDecision d;
  uint32_t reasons = 0;
  if (!auth.valid) {
    d = ActuatorDecision::BlockedNotAuthorized;
  } else if (auth.boot_count != boot_count_) {
    d = ActuatorDecision::BlockedStaleAuthorization;
  } else if (auth.serial != outstanding_serial_) {
    // Already consumed (duplicate execute) or superseded.
    d = executed_ ? ActuatorDecision::BlockedAlreadyDone : ActuatorDecision::BlockedNotAuthorized;
  } else {
    outstanding_serial_ = 0;  // single use, whatever the outcome
    const InterlockResult r = check(auth.request, fs, now);
    reasons = r.reasons;
    if (!r.permitted) {
      d = r.decision;
    } else {
      executed_ = true;  // record the one-shot BEFORE acting on it
      ++executed_count_;
      driver_.apply(auth.request);  // mock driver only (isPhysical() checked in check())
      d = ActuatorDecision::ExecutedSimulated;
    }
  }
  report(1, auth.request, d, reasons, now);
  return d;
}

ActuatorDecision ActuatorManager::handle(ActuatorRequest request, const FlightStatusView& fs, uint32_t now) {
  const Authorization a = authorize(request, fs, now);
  if (!a.valid) return last_.decision;
  return execute(a, fs, now);
}

}  // namespace cansat
