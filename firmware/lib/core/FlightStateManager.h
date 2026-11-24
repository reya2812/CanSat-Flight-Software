// FlightStateManager.h — the flight state machine ([PDR] slide 19).
//
// Consumes Events only. It never reads sensors and never touches hardware.
// It may EMIT ActuatorRequests into a queue; in Phase 2 nothing consumes that
// queue for actuation (actuator logic is disabled; requests are only logged).
//
// Permitted transitions (everything else is rejected and reported):
//   1 POWER_ON_SELF_CHECK --SelfCheckPass-------------> 2 READY_ON_DRONE
//   2 READY_ON_DRONE      --AscentDetected------------> 3 ASCENT
//   3 ASCENT              --ReleaseCandidate----------> 4 RELEASE_DETECTED   ("SEPARATION")
//   3 ASCENT              --ReleaseConfirmed----------> 4 then 5            (two legal steps)
//   4 RELEASE_DETECTED    --ReleaseConfirmed----------> 5 PARACHUTE_DEPLOY   ("CONFIRMED")
//   5 PARACHUTE_DEPLOY    --ChuteOpenDetected (sensed, after request)-----> 6 PANEL_DEPLOY
//   6 PANEL_DEPLOY        --DescentConfirmed (sustained baro descent)-----> 7 DESCENT
//   7 DESCENT             --TouchdownDetected---------> 8 LANDED
//   Abnormal, flagged (OD-065, provisional — needs team approval):
//   5 PARACHUTE_DEPLOY    --TouchdownDetected---------> 8 LANDED  (opening never sensed)
//   6 PANEL_DEPLOY        --TouchdownDetected---------> 8 LANDED  (descent never confirmed)
//
// Timeouts NEVER cause a transition and never imply success:
//   - chute_open_timeout_ms only raises ChuteOpenNotConfirmed + kFaultChuteOpenNotSensed;
//     the state stays PARACHUTE_DEPLOY and chuteStatus() reports OPENING_NOT_SENSED.
//   - panel deployment has no sensor: panelStatus() is always UnknownNoSensor.
//
// One-shot rules: release is latched once; the ReleaseParachute request is
// emitted at most once per boot, and across resets only if its one-shot flag
// was persisted (behaviour on persistence failure: PersistFailurePolicy, OD-067).
#pragma once

#include <stdint.h>

#include "HalInterfaces.h"
#include "RecoveryManager.h"
#include "Types.h"
#include "config/FlightParams.h"

namespace cansat {

class FlightStateManager {
 public:
  FlightStateManager(const FlightParams& params, RecoveryManager& recovery, IEventSink& out);

  void start(const RestoreResult& r, uint32_t now_ms);

  void onEvent(const Event& e);
  void tick(uint32_t now_ms);  // request timing and alarms only — never a transition

  FlightState state() const { return state_; }
  uint8_t oneShotFlags() const { return flags_; }
  bool chuteRequested() const { return (flags_ & kOneShotChuteRequested) != 0; }
  ChuteStatus chuteStatus() const;
  PanelStatus panelStatus() const { return PanelStatus::UnknownNoSensor; }
  uint32_t faultMask() const { return faults_; }
  // Read-only, for the downstream interlock (OD-070): local uptime at which
  // release was confirmed in this boot, or at which the state was resumed
  // after a reset (the separation timer restarts, see start()).
  uint32_t releaseTimerStartMs() const { return release_ms_; }

  bool popRequest(ActuatorRequest& out);
  uint32_t requestsEmitted() const { return requests_emitted_; }

  static bool isPermitted(FlightState from, FlightState to);

 private:
  bool transition(FlightState to, uint32_t now, EventType cause);
  void reject(FlightState to, uint32_t now, EventType cause);
  void emit(EventType t, uint32_t now, uint32_t detail);
  bool persist();
  void maybeRequestChute(uint32_t now);

  const FlightParams& p_;
  RecoveryManager& rec_;
  IEventSink& out_;
  bool complete_;
  uint32_t min_sep_ = 0, chute_timeout_ = 0;
  PersistFailurePolicy persist_policy_ = PersistFailurePolicy::Unset;

  FlightState state_ = FlightState::PowerOnSelfCheck;
  uint8_t flags_ = 0;
  uint32_t faults_ = 0;
  uint32_t release_ms_ = 0;  // local (this boot) time release was confirmed / resumed
  uint32_t request_ms_ = 0;
  bool opening_sensed_ = false;
  bool not_sensed_alarm_ = false;
  bool withheld_reported_ = false;

  static constexpr int kQueueCap = 4;
  ActuatorRequest queue_[kQueueCap] = {};
  int q_head_ = 0, q_count_ = 0;
  uint32_t requests_emitted_ = 0;
};

}  // namespace cansat
