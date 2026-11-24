#include "EventDetector.h"

#include <cmath>

#include "Altitude.h"

namespace cansat {

namespace {
constexpr float kOneG = 1.0f;  // accelerometer reading at rest (physics, not a threshold)
}

EventDetector::EventDetector(const FlightParams& params, IEventSink& out)
    : p_(params), out_(out), complete_(params.isComplete()) {
  if (!complete_) return;
  const ReleaseParams& r = p_.release;
  const TransitionParams& t = p_.transitions;
  r.switch_debounce_ms.get(t_db_);
  r.switch1_open_is_high.get(open_high_[0]);
  r.switch2_open_is_high.get(open_high_[1]);
  r.switch_vote.get(vote_);
  r.freefall_accel_max_g.get(a_ff_);
  r.freefall_min_ms.get(t_ff_);
  r.baro_min_drop_m.get(dh_min_);
  r.baro_window_ms.get(w_b_);
  r.confirm_window_ms.get(t_confirm_);
  p_.interlock.stuck_switch_policy.get(policy_);
  p_.interlock.fallback_delay_ms.get(fallback_);
  t.selfcheck_samples.get(sc_samples_);
  t.selfcheck_require_power.get(sc_need_power_);
  t.ascent_min_gain_m.get(asc_gain_);
  t.ascent_confirm_ms.get(asc_ms_);
  t.chute_open_accel_min_g.get(chute_g_);
  t.landed_window_ms.get(land_ms_);
  t.landed_max_alt_change_m.get(land_dalt_);
  t.landed_accel_tol_g.get(land_tol_);
  t.landed_max_alt_above_ground_m.get(land_agl_);
  t.descent_confirm_ms.get(desc_ms_);
}

void EventDetector::emit(EventType t, uint32_t now, uint32_t detail) {
  Event e;
  e.type = t;
  e.t_ms = now;
  e.detail = detail;
  out_.onEvent(e);
}

void EventDetector::restoreGroundReference(float pressure_pa) {
  has_ground_ = true;
  ground_pa_ = pressure_pa;
  sc_done_ = true;  // ground reference already captured in an earlier boot
}

float EventDetector::accelMag(const ImuSample& m) const {
  return std::sqrt(m.ax_g * m.ax_g + m.ay_g * m.ay_g + m.az_g * m.az_g);
}

void EventDetector::update(const ValidatedFrame& v, FlightState state, bool chute_requested) {
  if (!complete_) {
    if (!params_fail_emitted_) {
      emit(EventType::SelfCheckFail, v.now_ms, kFaultParamsIncomplete);
      params_fail_emitted_ = true;
    }
    return;
  }
  updateSwitches(v);
  updateFreefall(v);
  updateBaro(v);
  switch (state) {
    case FlightState::PowerOnSelfCheck: selfCheck(v); break;
    case FlightState::ReadyOnDrone: ascent(v); break;
    case FlightState::Ascent:
    case FlightState::ReleaseDetected: release(v); break;
    case FlightState::ParachuteDeploy:
      chute(v, chute_requested);
      landing(v);  // a CanSat whose opening was never sensed must still be able to report touchdown
      break;
    case FlightState::PanelDeploy:
      descent(v);
      landing(v);
      break;
    case FlightState::Descent: landing(v); break;
    case FlightState::Landed: break;
  }
}

void EventDetector::updateSwitches(const ValidatedFrame& v) {
  if (v.switches_ok) {
    for (uint8_t k = 0; k < kSwitchCount; ++k) {
      const bool level = v.raw.switches.raw[k];
      if (!sw_cand_set_[k] || level != sw_cand_[k]) {
        sw_cand_[k] = level;
        sw_cand_set_[k] = true;
        sw_cand_since_[k] = v.now_ms;
      }
      if (v.now_ms - sw_cand_since_[k] >= t_db_) {
        sw_stable_[k] = sw_cand_[k];
        sw_known_[k] = true;
      }
    }
  }
  const bool open1 = sw_known_[0] && sw_stable_[0] == open_high_[0];
  const bool open2 = sw_known_[1] && sw_stable_[1] == open_high_[1];
  switch (vote_) {
    case SwitchVote::Any:
      mount_known_ = sw_known_[0] && sw_known_[1];
      mount_open_ = open1 || open2;
      break;
    case SwitchVote::All:
      mount_known_ = sw_known_[0] && sw_known_[1];
      mount_open_ = open1 && open2;
      break;
    case SwitchVote::Sw1Only:
      mount_known_ = sw_known_[0];
      mount_open_ = open1;
      break;
    case SwitchVote::Unset:
      mount_known_ = false;
      mount_open_ = false;
      break;
  }
  if (!mount_known_) mount_open_ = false;
}

void EventDetector::updateFreefall(const ValidatedFrame& v) {
  if (!v.imu_ok) {
    below_ = false;
    freefall_ = false;
    imu_ever_rejected_ = true;
    last_imu_reject_ = v.now_ms;
    return;
  }
  if (accelMag(v.raw.imu) < a_ff_) {
    if (!below_) {
      below_ = true;
      below_since_ = v.now_ms;
    }
    freefall_ = (v.now_ms - below_since_ >= t_ff_);
  } else {
    below_ = false;
    freefall_ = false;
  }
}

void EventDetector::updateBaro(const ValidatedFrame& v) {
  baro_desc_ = false;
  alt_valid_ = false;
  if (!v.baro_ok) {
    baro_ever_rejected_ = true;
    last_baro_reject_ = v.now_ms;
    return;
  }
  const float p = v.raw.baro.pressure_pa;
  float ref = 0.0f;
  if (has_ground_) {
    ref = ground_pa_;
  } else {
    if (!has_local_ref_) {
      has_local_ref_ = true;
      local_ref_pa_ = p;  // provisional reference: only altitude *differences* use it
    }
    ref = local_ref_pa_;
  }
  alt_now_ = altitudeAboveReference(p, ref);
  alt_valid_ = true;

  hist_t_[hist_head_] = v.now_ms;
  hist_alt_[hist_head_] = alt_now_;
  hist_head_ = (hist_head_ + 1) % kBaroHistory;
  if (hist_n_ < kBaroHistory) ++hist_n_;

  // Most recent sample at least w_b_ old.
  bool found = false;
  float alt_then = 0.0f;
  for (int i = 0; i < hist_n_; ++i) {
    const int idx = (hist_head_ - 1 - i + kBaroHistory) % kBaroHistory;
    if (v.now_ms - hist_t_[idx] >= w_b_) {
      alt_then = hist_alt_[idx];
      found = true;
      break;
    }
  }
  baro_desc_ = found && (alt_then - alt_now_ >= dh_min_);
}

void EventDetector::selfCheck(const ValidatedFrame& v) {
  if (sc_done_) return;
  const bool good = v.baro_ok && v.imu_ok && v.switches_ok && mount_known_ && !mount_open_ &&
                    (!sc_need_power_ || v.power_ok);
  if (!good) {
    sc_count_ = 0;
    sc_sum_pa_ = 0.0;
    return;
  }
  ++sc_count_;
  sc_sum_pa_ += v.raw.baro.pressure_pa;
  if (sc_count_ >= sc_samples_) {
    ground_pa_ = static_cast<float>(sc_sum_pa_ / sc_count_);
    has_ground_ = true;
    sc_done_ = true;
    emit(EventType::SelfCheckPass, v.now_ms);
  }
}

void EventDetector::ascent(const ValidatedFrame& v) {
  if (asc_done_ || !has_ground_) return;
  if (alt_valid_ && alt_now_ >= asc_gain_) {
    if (!asc_above_) {
      asc_above_ = true;
      asc_since_ = v.now_ms;
    }
    if (v.now_ms - asc_since_ >= asc_ms_) {
      asc_done_ = true;
      emit(EventType::AscentDetected, v.now_ms);
    }
  } else {
    asc_above_ = false;
  }
}

void EventDetector::release(const ValidatedFrame& v) {
  if (confirmed_) return;
  const uint32_t now = v.now_ms;

  if (mount_open_ && !cand_active_ && !cand_emitted_) {
    cand_active_ = true;
    cand_emitted_ = true;
    cand_t_ = now;
    emit(EventType::ReleaseCandidate, now);
  }
  if (cand_active_ && !mount_open_) {
    cand_active_ = false;
    cand_emitted_ = false;  // a later re-opening is a new candidate
    emit(EventType::SwitchReverted, now);
  }

  if (mount_open_) {
    so_active_ = false;
    if (freefall_ || baro_desc_) {
      const uint32_t basis = (freefall_ && baro_desc_) ? kBasisSwitchFreefallBaro
                             : freefall_               ? kBasisSwitchAndFreefall
                                                       : kBasisSwitchAndBaro;
      confirmed_ = true;
      emit(EventType::ReleaseConfirmed, now, basis);
      return;
    }
    if (cand_active_ && !uncorroborated_emitted_ && now - cand_t_ > t_confirm_) {
      uncorroborated_emitted_ = true;
      emit(EventType::ReleaseUncorroborated, now);
    }
    return;
  }

  // Switch still reads "mounted" (or unknown): sensors-only evidence path (OD-060).
  if (!(freefall_ && baro_desc_)) {
    so_active_ = false;
    return;
  }
  if (!so_active_) {
    so_active_ = true;
    so_since_ = now;
  }
  bool accept = false;
  switch (policy_) {
    case StuckSwitchPolicy::StrictSwitchVeto:
      accept = false;
      break;
    case StuckSwitchPolicy::SensorOverride: {
      const bool imu_clean = !imu_ever_rejected_ || now - last_imu_reject_ >= t_confirm_;
      const bool baro_clean = !baro_ever_rejected_ || now - last_baro_reject_ >= t_confirm_;
      accept = imu_clean && baro_clean;
      break;
    }
    case StuckSwitchPolicy::Vote2of3:
      accept = true;
      break;
    case StuckSwitchPolicy::DelayedFallback:
      accept = (now - so_since_ >= fallback_);
      break;
    case StuckSwitchPolicy::Unset:
      accept = false;
      break;
  }
  if (!accept && !sensors_only_emitted_) {
    sensors_only_emitted_ = true;
    emit(EventType::ReleaseSensorsOnly, now, static_cast<uint32_t>(policy_));
  }
  if (accept) {
    confirmed_ = true;
    emit(EventType::ReleaseConfirmed, now, kBasisSensorsOnlyPolicy);
  }
}

void EventDetector::chute(const ValidatedFrame& v, bool chute_requested) {
  if (chute_done_ || !chute_requested || !v.imu_ok) return;
  if (v.raw.imu.saturated || accelMag(v.raw.imu) >= chute_g_) {
    chute_done_ = true;
    emit(EventType::ChuteOpenDetected, v.now_ms, 0u);  // sensed opening only
  }
}

void EventDetector::descent(const ValidatedFrame& v) {
  if (desc_done_) return;
  if (!baro_desc_) {
    desc_active_ = false;
    return;
  }
  if (!desc_active_) {
    desc_active_ = true;
    desc_since_ = v.now_ms;
  }
  if (v.now_ms - desc_since_ >= desc_ms_) {
    desc_done_ = true;
    emit(EventType::DescentConfirmed, v.now_ms);
  }
}

// TOUCHDOWN requires ALL of (OD-065):
//   - a ground reference from self-check (else touchdown is unconfirmable: flagged, never assumed),
//   - altitude within landed_max_alt_above_ground_m of that reference,
//   - altitude stable within landed_max_alt_change_m and |a| ~ 1 g for landed_window_ms,
//   - valid baro and IMU throughout the window.
// Time alone never establishes touchdown. A closed mount switch is reported in the event detail.
void EventDetector::landing(const ValidatedFrame& v) {
  if (touchdown_done_) return;
  if (!has_ground_) {
    faults_ |= kFaultLandingUnconfirmable;
    if (!unconfirmable_emitted_) {
      unconfirmable_emitted_ = true;
      emit(EventType::SensorFault, v.now_ms, kFaultLandingUnconfirmable);
    }
    return;
  }
  if (!alt_valid_ || !v.imu_ok || std::fabs(accelMag(v.raw.imu) - kOneG) > land_tol_ ||
      std::fabs(alt_now_) > land_agl_) {
    stable_ = false;
    return;
  }
  if (!stable_ || std::fabs(alt_now_ - stable_ref_alt_) > land_dalt_) {
    stable_ = true;
    stable_since_ = v.now_ms;
    stable_ref_alt_ = alt_now_;
  }
  if (v.now_ms - stable_since_ >= land_ms_) {
    touchdown_done_ = true;
    const bool closed = mount_known_ && !mount_open_;
    if (closed) faults_ |= kFaultLandedMountClosed;
    emit(EventType::TouchdownDetected, v.now_ms, closed ? kTouchdownMountReadsClosed : 0u);
  }
}

}  // namespace cansat
