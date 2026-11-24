// SensorValidator.h — decides which samples flight logic may use (SW-12).
//
// Health is judged from several independent kinds of evidence, not from the
// numbers alone (docs/OPEN_DECISIONS.md OD-066):
//   1. Communication: the driver reports the bus transaction failed (comm_ok).
//   2. Driver validity flag (valid).
//   3. Freshness: the chip's data-ready status (data_ready), timestamp advance,
//      and sample age (sample_stale_ms).
//   4. Stuck output (IMU): N consecutive samples with all six values identical
//      (imu_stuck_identical_samples) — relies on real sensor noise.
//   5. Value plausibility: non-finite, beyond the sensor's measuring
//      capability, or an all-zero read (one heuristic among the above, not the
//      sole health test).
// Bounds are sensor CAPABILITY limits, not flight thresholds. Boot-time
// identity (WHO_AM_I / chip ID) and the MPU6050 self-test are handled at boot
// (BootReport), not per sample.
#pragma once

#include <stdint.h>

#include "Types.h"
#include "config/FlightParams.h"

namespace cansat {

// [ASSUMPTION] BMP280 measuring range 300–1100 hPa (datasheet, recalled).
constexpr float kBaroMinPa = 30000.0f;
constexpr float kBaroMaxPa = 110000.0f;
// [ASSUMPTION] MPU6050 ±16 g full scale (datasheet, recalled); beyond it is impossible.
constexpr float kImuMaxAbsG = 16.0f;
// [UNVERIFIED] INA219 "up to 3.2 A" with 0.1 Ω shunt (docs/03); [ASSUMPTION] 26 V bus max.
constexpr float kPowerMaxAbsMa = 3200.0f;
constexpr float kPowerMaxBusV = 26.0f;

enum RejectReason : uint16_t {
  kRejectNone = 0,
  kRejectInvalidFlag = 1u << 0,
  kRejectNonFinite = 1u << 1,
  kRejectRange = 1u << 2,
  kRejectZeroRead = 1u << 3,
  kRejectStaleRepeat = 1u << 4,
  kRejectStaleAge = 1u << 5,
  kRejectComm = 1u << 6,      // bus transaction failed
  kRejectNotFresh = 1u << 7,  // chip says no new conversion (data-ready not set)
  kRejectStuck = 1u << 8      // output frozen: identical values for N samples
};

struct ValidatedFrame {
  uint32_t now_ms = 0;
  SensorFrame raw;
  bool baro_ok = false, imu_ok = false, power_ok = false, switches_ok = false;
  uint16_t baro_reject = 0, imu_reject = 0, power_reject = 0, switches_reject = 0;
};

class SensorValidator {
 public:
  explicit SensorValidator(const FlightParams& params) : params_(params) {}

  ValidatedFrame validate(const SensorFrame& f, uint32_t now_ms);

  uint32_t faultMask() const { return faults_; }
  uint32_t newlyFaulted() const { return newly_faulted_; }
  uint32_t newlyRecovered() const { return newly_recovered_; }

 private:
  uint16_t ageCheck(uint32_t t_ms, uint32_t now_ms, bool& has_last, uint32_t& last_t);
  uint16_t imuStuckCheck(const ImuSample& m);
  void setFault(uint32_t bit, bool bad);

  const FlightParams& params_;
  bool has_baro_ = false, has_imu_ = false, has_power_ = false, has_sw_ = false;
  uint32_t last_baro_ = 0, last_imu_ = 0, last_power_ = 0, last_sw_ = 0;
  bool has_prev_imu_values_ = false;
  float prev_imu_[6] = {0, 0, 0, 0, 0, 0};
  uint32_t imu_identical_run_ = 0;
  uint32_t faults_ = 0, newly_faulted_ = 0, newly_recovered_ = 0;
};

}  // namespace cansat
