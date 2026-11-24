// MockSensors.h — mock BMP280, MPU6050, INA219 and limit switches. [SIMULATED]
//
// Each mock samples a TruthSource at the VirtualClock's truth time, adds
// deterministic synthetic noise, then applies active faults. Timestamps on the
// returned samples are device uptime (VirtualClock::nowMs()), as on hardware.
//
// These are NOT drivers and model no real chip behaviour beyond what is stated:
//   - MockImu clips each accel axis at the MPU6050 full scale (±16 g,
//     [ASSUMPTION] datasheet value recalled, see PHASE1_PROPOSAL §2.2) and
//     sets `saturated`.
//   - Fault precedence in read(): not initialised / NotDetected / Dropout
//     (invalid) > CommFailure (invalid, comm_ok=false) > Stale (repeat last
//     sample incl. old timestamp) > NotReady (previous values, new timestamp,
//     data_ready=false) > StuckOutput (previous values, new timestamp,
//     data_ready=true) > fresh value + noise > ZeroRead > NaNValue > OutOfRange
//     (value overrides, reported VALID so the validation layer must catch them).
//   - Fresh samples carry comm_ok=true and data_ready=true.
#pragma once

#include <stdint.h>

#include <cmath>

#include "FaultInjector.h"
#include "HalInterfaces.h"
#include "Rng.h"
#include "TruthSource.h"
#include "Types.h"
#include "VirtualClock.h"

namespace cansat {
namespace mock {

// Baseline sensor noise amplitudes (uniform ±amplitude). Values are supplied
// by scenarios and are SYNTHETIC; the default is no noise.
struct SensorNoise {
  float pressure_pa = 0.0f;
  float temp_c = 0.0f;
  float accel_g = 0.0f;
  float gyro_dps = 0.0f;
  float bus_v = 0.0f;
  float current_ma = 0.0f;
};

constexpr float kMpu6050FullScaleG = 16.0f;  // [ASSUMPTION] MPU6050 max range, datasheet recalled

class MockBarometer : public IBarometer {
 public:
  MockBarometer(VirtualClock& clock, const ITruthSource& truth, const FaultInjector& faults,
                const SensorNoise& noise, uint32_t seed)
      : clock_(clock), truth_(truth), faults_(faults), noise_(noise), rng_(seed) {}

  bool begin() override {
    initialized_ = !faults_.query(FaultTarget::Baro, clock_.truthMs()).not_detected;
    has_last_ = false;
    return initialized_;
  }

  BaroSample read() override {
    BaroSample s;
    s.t_ms = clock_.nowMs();
    const ActiveFaults a = faults_.query(FaultTarget::Baro, clock_.truthMs());
    if (!initialized_ || a.not_detected || a.dropout) return s;  // valid=false
    if (a.comm_failure) return s;  // comm_ok=false, valid=false
    if (a.stale) return has_last_ ? last_ : s;
    if ((a.not_ready || a.stuck_output) && has_last_) {
      auto repeated = last_;
      repeated.t_ms = s.t_ms;
      repeated.data_ready = !a.not_ready;
      return repeated;
    }
    const TruthState t = truth_.truthAt(clock_.truthMs());
    s.pressure_pa = t.pressure_pa + rng_.uniform(noise_.pressure_pa + a.noise_amp);
    s.temp_c = t.temp_c + rng_.uniform(noise_.temp_c);
    s.valid = true;
    s.comm_ok = true;
    s.data_ready = true;
    if (a.zero) s.pressure_pa = s.temp_c = 0.0f;
    if (a.nan) s.pressure_pa = s.temp_c = std::nanf("");
    if (a.out_of_range) s.pressure_pa = a.out_of_range_value;
    last_ = s;
    has_last_ = true;
    return s;
  }

 private:
  VirtualClock& clock_;
  const ITruthSource& truth_;
  const FaultInjector& faults_;
  SensorNoise noise_;
  Rng rng_;
  bool initialized_ = false;
  bool has_last_ = false;
  BaroSample last_;
};

class MockImu : public IImu {
 public:
  MockImu(VirtualClock& clock, const ITruthSource& truth, const FaultInjector& faults,
          const SensorNoise& noise, uint32_t seed)
      : clock_(clock), truth_(truth), faults_(faults), noise_(noise), rng_(seed) {}

  bool begin() override {
    initialized_ = !faults_.query(FaultTarget::Imu, clock_.truthMs()).not_detected;
    has_last_ = false;
    return initialized_;
  }

  ImuSample read() override {
    ImuSample s;
    s.t_ms = clock_.nowMs();
    const ActiveFaults a = faults_.query(FaultTarget::Imu, clock_.truthMs());
    if (!initialized_ || a.not_detected || a.dropout) return s;
    if (a.comm_failure) return s;  // comm_ok=false, valid=false
    if (a.stale) return has_last_ ? last_ : s;
    if ((a.not_ready || a.stuck_output) && has_last_) {
      auto repeated = last_;
      repeated.t_ms = s.t_ms;
      repeated.data_ready = !a.not_ready;
      return repeated;
    }
    const TruthState t = truth_.truthAt(clock_.truthMs());
    float acc[3];
    float gyr[3];
    for (int i = 0; i < 3; ++i) {
      acc[i] = t.accel_g[i] + rng_.uniform(noise_.accel_g + a.noise_amp);
      gyr[i] = t.gyro_dps[i] + rng_.uniform(noise_.gyro_dps);
      if (acc[i] > kMpu6050FullScaleG) {
        acc[i] = kMpu6050FullScaleG;
        s.saturated = true;
      } else if (acc[i] < -kMpu6050FullScaleG) {
        acc[i] = -kMpu6050FullScaleG;
        s.saturated = true;
      }
    }
    s.ax_g = acc[0];
    s.ay_g = acc[1];
    s.az_g = acc[2];
    s.gx_dps = gyr[0];
    s.gy_dps = gyr[1];
    s.gz_dps = gyr[2];
    s.valid = true;
    s.comm_ok = true;
    s.data_ready = true;
    if (a.zero) {
      s.ax_g = s.ay_g = s.az_g = s.gx_dps = s.gy_dps = s.gz_dps = 0.0f;
      s.saturated = false;
    }
    if (a.nan) s.ax_g = s.ay_g = s.az_g = std::nanf("");
    if (a.out_of_range) s.ax_g = a.out_of_range_value;
    last_ = s;
    has_last_ = true;
    return s;
  }

 private:
  VirtualClock& clock_;
  const ITruthSource& truth_;
  const FaultInjector& faults_;
  SensorNoise noise_;
  Rng rng_;
  bool initialized_ = false;
  bool has_last_ = false;
  ImuSample last_;
};

class MockPowerMonitor : public IPowerMonitor {
 public:
  MockPowerMonitor(VirtualClock& clock, const ITruthSource& truth, const FaultInjector& faults,
                   const SensorNoise& noise, uint32_t seed)
      : clock_(clock), truth_(truth), faults_(faults), noise_(noise), rng_(seed) {}

  bool begin() override {
    initialized_ = !faults_.query(FaultTarget::Power, clock_.truthMs()).not_detected;
    has_last_ = false;
    return initialized_;
  }

  PowerSample read() override {
    PowerSample s;
    s.t_ms = clock_.nowMs();
    const ActiveFaults a = faults_.query(FaultTarget::Power, clock_.truthMs());
    if (!initialized_ || a.not_detected || a.dropout) return s;
    if (a.comm_failure) return s;  // comm_ok=false, valid=false
    if (a.stale) return has_last_ ? last_ : s;
    if ((a.not_ready || a.stuck_output) && has_last_) {
      auto repeated = last_;
      repeated.t_ms = s.t_ms;
      repeated.data_ready = !a.not_ready;
      return repeated;
    }
    const TruthState t = truth_.truthAt(clock_.truthMs());
    s.bus_v = t.bus_v + rng_.uniform(noise_.bus_v);
    s.current_ma = t.current_ma + rng_.uniform(noise_.current_ma + a.noise_amp);
    s.valid = true;
    s.comm_ok = true;
    s.data_ready = true;
    if (a.zero) s.bus_v = s.current_ma = 0.0f;
    if (a.nan) s.bus_v = s.current_ma = std::nanf("");
    if (a.out_of_range) s.current_ma = a.out_of_range_value;
    last_ = s;
    has_last_ = true;
    return s;
  }

 private:
  VirtualClock& clock_;
  const ITruthSource& truth_;
  const FaultInjector& faults_;
  SensorNoise noise_;
  Rng rng_;
  bool initialized_ = false;
  bool has_last_ = false;
  PowerSample last_;
};

// Two limit switches. Truth "mounted" means both switches mechanically closed.
// `closed_level_high[k]` is the SYNTHETIC wiring assumption for the electrical
// level that represents "closed" (real NO/NC wiring is TBD, OD-051).
class MockSwitches : public IDigitalInputs {
 public:
  MockSwitches(VirtualClock& clock, const ITruthSource& truth, const FaultInjector& faults,
               bool closed_level_high_1, bool closed_level_high_2)
      : clock_(clock), truth_(truth), faults_(faults) {
    closed_high_[0] = closed_level_high_1;
    closed_high_[1] = closed_level_high_2;
  }

  SwitchSample read() override {
    SwitchSample s;
    s.t_ms = clock_.nowMs();
    const uint32_t t = clock_.truthMs();
    const FaultTarget targets[kSwitchCount] = {FaultTarget::Switch1, FaultTarget::Switch2};
    const TruthState truth = truth_.truthAt(t);
    bool any_dropout = false;
    for (uint8_t k = 0; k < kSwitchCount; ++k) {
      const ActiveFaults a = faults_.query(targets[k], t);
      if (a.dropout || a.not_detected) any_dropout = true;
      bool closed = truth.mounted;
      if (a.stuck_closed) closed = true;
      if (a.stuck_open) closed = false;
      if (a.bounce && ((t - a.bounce_start_ms) / a.bounce_period_ms) % 2u == 1u) closed = !closed;
      s.raw[k] = closed ? closed_high_[k] : !closed_high_[k];
    }
    s.valid = !any_dropout;
    if (!s.valid) s.raw[0] = s.raw[1] = false;
    return s;
  }

  // Helper for logs/tests only (flight code must interpret raw levels itself).
  bool levelMeansClosed(uint8_t k, bool level) const { return level == closed_high_[k]; }

 private:
  VirtualClock& clock_;
  const ITruthSource& truth_;
  const FaultInjector& faults_;
  bool closed_high_[kSwitchCount];
};

}  // namespace mock
}  // namespace cansat
