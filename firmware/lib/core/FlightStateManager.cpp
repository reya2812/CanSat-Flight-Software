#include "FlightStateManager.h"

namespace cansat {

FlightStateManager::FlightStateManager(const FlightParams& params, RecoveryManager& recovery,
                                       IEventSink& out)
    : p_(params), rec_(recovery), out_(out), complete_(params.isComplete()) {
  if (!complete_) return;
  p_.interlock.min_separation_ms.get(min_sep_);
  p_.interlock.persist_failure_policy.get(persist_policy_);
  p_.transitions.chute_open_timeout_ms.get(chute_timeout_);
}

bool FlightStateManager::isPermitted(FlightState from, FlightState to) {
  const uint8_t f = static_cast<uint8_t>(from);
  const uint8_t t = static_cast<uint8_t>(to);
  if (!isValidFlightStateCode(f) || !isValidFlightStateCode(t)) return false;
  if (t == f + 1) return true;
  // Abnormal but explicit: touchdown confirmed before the chain completed (OD-065).
  return to == FlightState::Landed &&
         (from == FlightState::ParachuteDeploy || from == FlightState::PanelDeploy);
}

ChuteStatus FlightStateManager::chuteStatus() const {
  if (!chuteRequested()) return ChuteStatus::NotRequested;
  if (opening_sensed_) return ChuteStatus::OpeningSensed;
  if (not_sensed_alarm_) return ChuteStatus::OpeningNotSensedTimeout;
  return ChuteStatus::RequestedAwaitingOpening;
}

void FlightStateManager::emit(EventType t, uint32_t now, uint32_t detail) {
  Event e;
  e.type = t;
  e.t_ms = now;
  e.detail = detail;
  out_.onEvent(e);
}

bool FlightStateManager::persist() {
  const bool ok = rec_.persist(state_, flags_);
  if (!ok) faults_ |= kFaultPersistWrite;
  return ok;
}

void FlightStateManager::start(const RestoreResult& r, uint32_t now_ms) {
  state_ = r.state;
  flags_ = r.one_shot_flags;
  release_ms_ = now_ms;  // separation timer restarts after a reset (conservative)
  request_ms_ = now_ms;
  if (r.corrupt) faults_ |= kFaultRecoveryRecordCorrupt;
  // After a reset the opening (if any) was sensed in a previous boot; past
  // PARACHUTE_DEPLOY the state itself records that it was sensed.
  opening_sensed_ = chuteRequested() && state_ >= FlightState::PanelDeploy;
  if (r.resumed) emit(EventType::ResetRecovered, now_ms, static_cast<uint32_t>(state_));
  if (r.resumed && chuteRequested()) {
    emit(EventType::RequestSuppressed, now_ms, static_cast<uint32_t>(ActuatorRequest::ReleaseParachute));
  }
}

void FlightStateManager::reject(FlightState to, uint32_t now, EventType cause) {
  emit(EventType::TransitionRejected, now,
       (static_cast<uint32_t>(state_) << 16) | (static_cast<uint32_t>(to) << 8) |
           static_cast<uint32_t>(cause));
}

bool FlightStateManager::transition(FlightState to, uint32_t now, EventType cause) {
  if (!isPermitted(state_, to)) {
    reject(to, now, cause);
    return false;
  }
  const FlightState from = state_;
  state_ = to;
  persist();
  emit(EventType::StateChanged, now, (static_cast<uint32_t>(from) << 8) | static_cast<uint32_t>(to));
  return true;
}

void FlightStateManager::onEvent(const Event& e) {
  const uint32_t now = e.t_ms;
  switch (e.type) {
    case EventType::SelfCheckPass:
      transition(FlightState::ReadyOnDrone, now, e.type);
      break;
    case EventType::AscentDetected:
      transition(FlightState::Ascent, now, e.type);
      break;
    case EventType::ReleaseCandidate:
      if (state_ == FlightState::ReleaseDetected) break;  // already separated; nothing to do
      transition(FlightState::ReleaseDetected, now, e.type);
      break;
    case EventType::ReleaseConfirmed:
      if (flags_ & kOneShotReleaseConfirmed) break;  // duplicate: release is latched once
      if (state_ == FlightState::Ascent && !transition(FlightState::ReleaseDetected, now, e.type)) break;
      if (!transition(FlightState::ParachuteDeploy, now, e.type)) break;
      release_ms_ = now;
      flags_ |= kOneShotReleaseConfirmed;
      persist();
      break;
    case EventType::ChuteOpenDetected:
      if (state_ != FlightState::ParachuteDeploy || !chuteRequested()) {
        reject(FlightState::PanelDeploy, now, e.type);
        break;
      }
      opening_sensed_ = true;
      transition(FlightState::PanelDeploy, now, e.type);
      break;
    case EventType::DescentConfirmed:
      transition(FlightState::Descent, now, e.type);
      break;
    case EventType::TouchdownDetected:
      transition(FlightState::Landed, now, e.type);
      break;
    case EventType::ReleaseSensorsOnly:
    case EventType::ReleaseUncorroborated:
    case EventType::SwitchReverted:
      faults_ |= kFaultReleaseDegraded;
      break;
    case EventType::SelfCheckFail:
      faults_ |= kFaultSelfCheck | (e.detail & kFaultParamsIncomplete);
      break;
    default:
      break;  // informational events (faults, recovery, own outputs)
  }
}

void FlightStateManager::maybeRequestChute(uint32_t now) {
  if (!(flags_ & kOneShotReleaseConfirmed) || chuteRequested()) return;
  if (now - release_ms_ < min_sep_) return;
  // Persist the one-shot flag BEFORE queueing, so that a reset cannot cause a
  // second request. What happens when persisting fails is OD-067 (no default).
  flags_ |= kOneShotChuteRequested;
  if (!persist() && persist_policy_ == PersistFailurePolicy::WithholdUntilPersisted) {
    flags_ &= static_cast<uint8_t>(~kOneShotChuteRequested);  // retry next tick
    faults_ |= kFaultRequestWithheld;
    if (!withheld_reported_) {
      withheld_reported_ = true;
      emit(EventType::RequestWithheld, now, static_cast<uint32_t>(ActuatorRequest::ReleaseParachute));
    }
    return;
  }
  request_ms_ = now;
  if (q_count_ < kQueueCap) {
    queue_[(q_head_ + q_count_) % kQueueCap] = ActuatorRequest::ReleaseParachute;
    ++q_count_;
  } else {
    faults_ |= kFaultRequestQueueFull;
  }
  ++requests_emitted_;
  emit(EventType::RequestEmitted, now, static_cast<uint32_t>(ActuatorRequest::ReleaseParachute));
}

void FlightStateManager::tick(uint32_t now) {
  if (!complete_ || state_ != FlightState::ParachuteDeploy) return;
  maybeRequestChute(now);
  // Alarm only: the opening was not sensed in time. No transition, no assumed success.
  if (chuteRequested() && !opening_sensed_ && !not_sensed_alarm_ && now - request_ms_ >= chute_timeout_) {
    not_sensed_alarm_ = true;
    faults_ |= kFaultChuteOpenNotSensed;
    emit(EventType::ChuteOpenNotConfirmed, now, 0);
  }
}

bool FlightStateManager::popRequest(ActuatorRequest& out) {
  if (q_count_ == 0) return false;
  out = queue_[q_head_];
  q_head_ = (q_head_ + 1) % kQueueCap;
  --q_count_;
  return true;
}

}  // namespace cansat
