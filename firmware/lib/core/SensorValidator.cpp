#include "SensorValidator.h"

#include <cmath>

namespace cansat {

uint16_t SensorValidator::ageCheck(uint32_t t_ms, uint32_t now_ms, bool& has_last, uint32_t& last_t) {
  uint16_t r = 0;
  if (has_last && t_ms <= last_t) r |= kRejectStaleRepeat;
  uint32_t stale_ms = 0;
  if (params_.release.sample_stale_ms.get(stale_ms) && now_ms >= t_ms && now_ms - t_ms > stale_ms) {
    r |= kRejectStaleAge;
  }
  if (r == 0) {
    has_last = true;
    last_t = t_ms;
  }
  return r;
}

uint16_t SensorValidator::imuStuckCheck(const ImuSample& m) {
  const float v[6] = {m.ax_g, m.ay_g, m.az_g, m.gx_dps, m.gy_dps, m.gz_dps};
  bool same = has_prev_imu_values_;
  for (int i = 0; i < 6 && same; ++i) same = (v[i] == prev_imu_[i]);
  imu_identical_run_ = same ? imu_identical_run_ + 1 : 1;
  for (int i = 0; i < 6; ++i) prev_imu_[i] = v[i];
  has_prev_imu_values_ = true;
  uint32_t limit = 0;
  if (params_.validation.imu_stuck_identical_samples.get(limit) && limit > 0 &&
      imu_identical_run_ >= limit) {
    return kRejectStuck;
  }
  return 0;
}

void SensorValidator::setFault(uint32_t bit, bool bad) {
  const bool was = (faults_ & bit) != 0;
  if (bad && !was) {
    faults_ |= bit;
    newly_faulted_ |= bit;
  } else if (!bad && was) {
    faults_ &= ~bit;
    newly_recovered_ |= bit;
  }
}

ValidatedFrame SensorValidator::validate(const SensorFrame& f, uint32_t now_ms) {
  newly_faulted_ = newly_recovered_ = 0;
  ValidatedFrame v;
  v.now_ms = now_ms;
  v.raw = f;

  // ---- barometer ----
  uint16_t r = 0;
  if (!f.baro.comm_ok) r |= kRejectComm;
  if (!f.baro.valid) r |= kRejectInvalidFlag;
  if (r == 0) {
    if (!f.baro.data_ready) {
      r |= kRejectNotFresh;
    } else if (!std::isfinite(f.baro.pressure_pa) || !std::isfinite(f.baro.temp_c)) {
      r |= kRejectNonFinite;
    } else if (f.baro.pressure_pa == 0.0f && f.baro.temp_c == 0.0f) {
      r |= kRejectZeroRead;
    } else if (f.baro.pressure_pa < kBaroMinPa || f.baro.pressure_pa > kBaroMaxPa) {
      r |= kRejectRange;
    }
  }
  if (r == 0) r |= ageCheck(f.baro.t_ms, now_ms, has_baro_, last_baro_);
  v.baro_reject = r;
  v.baro_ok = (r == 0);
  setFault(kFaultBaroInvalid, !v.baro_ok);

  // ---- IMU ----
  r = 0;
  const ImuSample& m = f.imu;
  if (!m.comm_ok) r |= kRejectComm;
  if (!m.valid) r |= kRejectInvalidFlag;
  if (r == 0) {
    if (!m.data_ready) {
      r |= kRejectNotFresh;
    } else if (!std::isfinite(m.ax_g) || !std::isfinite(m.ay_g) || !std::isfinite(m.az_g) ||
               !std::isfinite(m.gx_dps) || !std::isfinite(m.gy_dps) || !std::isfinite(m.gz_dps)) {
      r |= kRejectNonFinite;
    } else if (m.ax_g == 0.0f && m.ay_g == 0.0f && m.az_g == 0.0f && m.gx_dps == 0.0f &&
               m.gy_dps == 0.0f && m.gz_dps == 0.0f) {
      r |= kRejectZeroRead;  // heuristic: exactly zero on all six axes
    } else if (std::fabs(m.ax_g) > kImuMaxAbsG || std::fabs(m.ay_g) > kImuMaxAbsG ||
               std::fabs(m.az_g) > kImuMaxAbsG) {
      r |= kRejectRange;
    }
    if (r == 0 || r == kRejectZeroRead) r |= imuStuckCheck(m);
  }
  if (r == 0) r |= ageCheck(m.t_ms, now_ms, has_imu_, last_imu_);
  v.imu_reject = r;
  v.imu_ok = (r == 0);
  setFault(kFaultImuInvalid, !v.imu_ok);
  setFault(kFaultImuSaturated, v.imu_ok && m.saturated);

  // ---- power ----
  r = 0;
  if (!f.power.comm_ok) r |= kRejectComm;
  if (!f.power.valid) r |= kRejectInvalidFlag;
  if (r == 0) {
    if (!f.power.data_ready) {
      r |= kRejectNotFresh;
    } else if (!std::isfinite(f.power.bus_v) || !std::isfinite(f.power.current_ma)) {
      r |= kRejectNonFinite;
    } else if (std::fabs(f.power.current_ma) > kPowerMaxAbsMa || f.power.bus_v < 0.0f ||
               f.power.bus_v > kPowerMaxBusV) {
      r |= kRejectRange;
    }
  }
  if (r == 0) r |= ageCheck(f.power.t_ms, now_ms, has_power_, last_power_);
  v.power_reject = r;
  v.power_ok = (r == 0);
  setFault(kFaultPowerInvalid, !v.power_ok);

  // ---- switches (GPIO: no bus, no data-ready; validity + age only) ----
  r = 0;
  if (!f.switches.valid) r |= kRejectInvalidFlag;
  if (r == 0) r |= ageCheck(f.switches.t_ms, now_ms, has_sw_, last_sw_);
  v.switches_reject = r;
  v.switches_ok = (r == 0);
  setFault(kFaultSwitchInvalid, !v.switches_ok);

  return v;
}

}  // namespace cansat
