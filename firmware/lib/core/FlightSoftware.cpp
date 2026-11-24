#include "FlightSoftware.h"

namespace cansat {

void FlightSoftware::Recorder::onEvent(const Event& e) {
  fs_.record(e);
  if (forward_) fs_.fsm_.onEvent(e);
}

void FlightSoftware::record(const Event& e) {
  if (n_events_ < kMaxEventsPerTick) {
    events_[n_events_++] = e;
  } else {
    ++dropped_events_;
  }
}

FlightSoftware::FlightSoftware(const FlightParams& params, IPersistentStore& store)
    : params_(params),
      recovery_(store),
      detector_sink_(*this, true),
      fsm_sink_(*this, false),
      validator_(params),
      detector_(params, detector_sink_),
      fsm_(params, recovery_, fsm_sink_) {}

uint32_t FlightSoftware::faultMask() const {
  return validator_.faultMask() | fsm_.faultMask() | detector_.faultMask() | boot_faults_;
}

void FlightSoftware::boot(const BootReport& report, uint32_t now_ms) {
  n_events_ = 0;
  restore_ = recovery_.restoreOnBoot();
  if (restore_.has_ground) {
    detector_.restoreGroundReference(restore_.ground_pressure_pa);
    recovery_.setGroundPressure(restore_.ground_pressure_pa);
  }
  fsm_.start(restore_, now_ms);

  // Sensor init failures: a sensor required by self-check that failed begin()
  // blocks the self-check (whether the mission may still arm is TBD, docs/07).
  if (!report.baro_ok) boot_faults_ |= kFaultBaroInvalid;
  if (!report.imu_ok) boot_faults_ |= kFaultImuInvalid;
  if (!report.power_ok) boot_faults_ |= kFaultPowerInvalid;
  // MPU6050 self-test (OD-066): a FAILED result blocks self-check; NOT RUN is
  // reported but does not block (no driver can run it yet). Provisional.
  if (report.imu_self_test == SelfTestResult::NotRun) boot_faults_ |= kFaultImuSelfTestNotRun;
  if (report.imu_self_test == SelfTestResult::Failed) boot_faults_ |= kFaultImuSelfTestFailed;
  if (!report.baro_ok || !report.imu_ok || report.imu_self_test == SelfTestResult::Failed) {
    boot_faults_ |= kFaultSelfCheck;
    Event e;
    e.type = EventType::SelfCheckFail;
    e.t_ms = now_ms;
    e.detail = boot_faults_;
    detector_sink_.onEvent(e);
  }
  if (!params_.isComplete()) boot_faults_ |= kFaultParamsIncomplete;
}

void FlightSoftware::tick(const SensorFrame& frame, uint32_t now_ms) {
  n_events_ = 0;
  const ValidatedFrame v = validator_.validate(frame, now_ms);
  for (uint32_t bit = 1; bit != 0; bit <<= 1) {
    if (validator_.newlyFaulted() & bit) {
      Event e;
      e.type = EventType::SensorFault;
      e.t_ms = now_ms;
      e.detail = bit;
      record(e);
    }
    if (validator_.newlyRecovered() & bit) {
      Event e;
      e.type = EventType::SensorRecovered;
      e.t_ms = now_ms;
      e.detail = bit;
      record(e);
    }
  }
  // A sensor that failed begin() stays failed until the next boot.
  const bool init_blocked = (boot_faults_ & kFaultSelfCheck) != 0;
  if (!(init_blocked && fsm_.state() == FlightState::PowerOnSelfCheck)) {
    detector_.update(v, fsm_.state(), fsm_.chuteRequested());
  }
  if (detector_.hasGroundReference()) recovery_.setGroundPressure(detector_.groundPressurePa());
  fsm_.tick(now_ms);
}

}  // namespace cansat
