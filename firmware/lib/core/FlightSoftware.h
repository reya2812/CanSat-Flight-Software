// FlightSoftware.h — composition of the flight logic for one boot.
//
//   SensorFrame → SensorValidator → EventDetector → events → FlightStateManager
//                                                            → ActuatorRequest queue
//
// The ActuatorRequest queue is exposed for logging only. [TEAM DECISION]
// Phase 2: no code consumes it for actuation; there is no ActuatorManager and
// no actuator driver is referenced anywhere in this module.
//
// A reset is modelled by destroying this object and constructing a new one
// with the same IPersistentStore (RAM lost, persisted record kept).
#pragma once

#include <stdint.h>

#include "EventDetector.h"
#include "FlightStateManager.h"
#include "HalInterfaces.h"
#include "RecoveryManager.h"
#include "SensorValidator.h"
#include "Types.h"
#include "config/FlightParams.h"

namespace cansat {

// Results of sensor initialisation. On hardware `*_ok` would combine: bus
// response, chip identity (WHO_AM_I / chip-ID register) and configuration
// read-back. [TBD] No physical driver exists yet (OD-066).
struct BootReport {
  bool baro_ok = false;
  bool imu_ok = false;
  bool power_ok = false;
  SelfTestResult imu_self_test = SelfTestResult::NotRun;
};

class FlightSoftware {
 public:
  static constexpr int kMaxEventsPerTick = 32;

  FlightSoftware(const FlightParams& params, IPersistentStore& store);

  void boot(const BootReport& report, uint32_t now_ms);
  void tick(const SensorFrame& frame, uint32_t now_ms);

  FlightState state() const { return fsm_.state(); }
  uint32_t faultMask() const;
  const RestoreResult& restore() const { return restore_; }
  bool popRequest(ActuatorRequest& out) { return fsm_.popRequest(out); }
  uint32_t requestsEmitted() const { return fsm_.requestsEmitted(); }
  ChuteStatus chuteStatus() const { return fsm_.chuteStatus(); }
  const FlightStateManager& fsm() const { return fsm_; }
  const EventDetector& detector() const { return detector_; }

  // Events produced during the last boot()/tick() (detector + state machine), in order.
  int eventCount() const { return n_events_; }
  const Event& eventAt(int i) const { return events_[i]; }

 private:
  class Recorder : public IEventSink {
   public:
    explicit Recorder(FlightSoftware& fs, bool forward) : fs_(fs), forward_(forward) {}
    void onEvent(const Event& e) override;

   private:
    FlightSoftware& fs_;
    bool forward_;  // detector events are forwarded to the state machine
  };
  void record(const Event& e);

  const FlightParams& params_;
  RecoveryManager recovery_;
  Recorder detector_sink_;
  Recorder fsm_sink_;
  SensorValidator validator_;
  EventDetector detector_;
  FlightStateManager fsm_;
  RestoreResult restore_;
  uint32_t boot_faults_ = 0;
  Event events_[kMaxEventsPerTick];
  int n_events_ = 0;
  uint32_t dropped_events_ = 0;
};

}  // namespace cansat
