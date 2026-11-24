// ActuatorManager.h — the ONLY caller of IActuatorDriver (OD-070). [PROPOSED]
//
// Mock-only. Physical actuation is disabled at compile time (BuildFlags.h,
// OD-059) and, independently, at run time: a driver whose isPhysical() is
// true is refused and never called.
//
// Two-phase protocol, so that evidence is checked twice:
//   authorize(request)  → runs the DeploymentInterlock; on success returns an
//                         Authorization token (nothing is executed).
//   execute(token)      → re-reads arming and the connection assessment and
//                         runs the interlock AGAIN; only then calls the driver.
// A token is single-use and valid only within the boot that issued it.
// Entering a deployment state never actuates: only a request that passes
// both phases reaches the driver.
//
// Known gap (OD-070): the "executed" record is RAM-only. Cross-reset
// duplicate prevention still relies on the state machine's persisted
// request flag (set before queueing), so a reset between authorization and
// execution means the request is never executed. Persisting execution would
// change the recovery implementation, which is not approved.
#pragma once

#include <stdint.h>

#include "DeploymentInterlock.h"
#include "HalInterfaces.h"
#include "Types.h"
#include "config/BuildFlags.h"
#include "config/FlightParams.h"

namespace cansat {

static_assert(!build::kPhysicalActuatorsEnabled, "ActuatorManager is mock-only (OD-059)");

// Flight-state view the manager needs (from FlightStateManager).
struct FlightStatusView {
  FlightState state = FlightState::PowerOnSelfCheck;
  uint8_t one_shot_flags = 0;
  uint32_t release_timer_start_ms = 0;
};

struct Authorization {
  bool valid = false;
  ActuatorRequest request = ActuatorRequest::ReleaseParachute;
  uint32_t t_ms = 0;
  uint16_t boot_count = 0;
  uint32_t serial = 0;
};

class ActuatorManager {
 public:
  ActuatorManager(const FlightParams& flight, const DeploymentInterlockParams& il,
                  IConnectionAssessmentSource& connection, IArmingSource& arming,
                  IActuatorDriver& driver, IEventSink& events, uint16_t boot_count);

  Authorization authorize(ActuatorRequest request, const FlightStatusView& fs, uint32_t now_ms);
  ActuatorDecision execute(const Authorization& auth, const FlightStatusView& fs, uint32_t now_ms);
  // authorize() immediately followed by execute(), for callers with no gap.
  ActuatorDecision handle(ActuatorRequest request, const FlightStatusView& fs, uint32_t now_ms);

  uint32_t executedCount() const { return executed_count_; }
  bool executedThisBoot() const { return executed_; }
  const InterlockResult& lastResult() const { return last_; }

 private:
  InterlockResult check(ActuatorRequest request, const FlightStatusView& fs, uint32_t now_ms);
  void report(int phase, ActuatorRequest request, ActuatorDecision d, uint32_t reasons, uint32_t now);

  DeploymentInterlock interlock_;
  IConnectionAssessmentSource& connection_;
  IArmingSource& arming_;
  IActuatorDriver& driver_;
  IEventSink& events_;
  uint16_t boot_count_;
  uint32_t next_serial_ = 1;
  uint32_t outstanding_serial_ = 0;  // 0 = no live authorization
  bool executed_ = false;
  uint32_t executed_count_ = 0;
  InterlockResult last_;
};

inline uint32_t packActuatorDecision(int phase, ActuatorRequest r, ActuatorDecision d, uint32_t reasons) {
  return (reasons & 0xFFFFu) | (static_cast<uint32_t>(d) << 16) |
         ((static_cast<uint32_t>(r) & 0x7Fu) << 24) | (phase ? (1u << 31) : 0u);
}

}  // namespace cansat
