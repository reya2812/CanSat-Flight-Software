// EventDetector.h — turns validated sensor frames into flight events.
//
// This is the ONLY flight module that looks at sensor values. The state
// machine consumes the events it emits and never reads sensors itself.
// Every threshold/time comes from FlightParams (no defaults). If the params
// are incomplete the detector emits nothing except SelfCheckFail.
//
// Release logic follows docs/PHASE1_PROPOSAL.md §3.2. The stuck-switch case
// (switch still "mounted" but free fall AND baro descent present) is resolved
// by the configured StuckSwitchPolicy (OD-060, undecided — no default):
//   StrictSwitchVeto (P-A): never confirm; emit ReleaseSensorsOnly (degraded).
//   SensorOverride   (P-B): confirm only if neither IMU nor baro had a
//                           rejected sample within the last confirm_window_ms.
//   Vote2of3         (P-C): confirm (free fall + baro = 2 of 3 indicators).
//   DelayedFallback  (P-G): emit ReleaseSensorsOnly; confirm once the evidence
//                           has persisted for fallback_delay_ms.
#pragma once

#include <stdint.h>

#include "HalInterfaces.h"
#include "SensorValidator.h"
#include "Types.h"
#include "config/FlightParams.h"

namespace cansat {

class EventDetector {
 public:
  EventDetector(const FlightParams& params, IEventSink& out);

  // Ground reference restored from the recovery record (after a reset).
  void restoreGroundReference(float pressure_pa);
  bool hasGroundReference() const { return has_ground_; }
  float groundPressurePa() const { return ground_pa_; }

  // Inputs from the state machine (read-only view of its decisions).
  void update(const ValidatedFrame& v, FlightState state, bool chute_requested);

  // Diagnostics for logs/tests.
  bool mountOpen() const { return mount_open_; }
  bool freefall() const { return freefall_; }
  bool baroDescent() const { return baro_desc_; }
  bool releaseLatched() const { return confirmed_; }
  bool paramsComplete() const { return complete_; }
  uint32_t faultMask() const { return faults_; }

  static constexpr int kBaroHistory = 128;  // [ASSUMPTION] sizing; must cover baro_window_ms

 private:
  void emit(EventType t, uint32_t now, uint32_t detail = 0);
  void updateSwitches(const ValidatedFrame& v);
  void updateFreefall(const ValidatedFrame& v);
  void updateBaro(const ValidatedFrame& v);
  void selfCheck(const ValidatedFrame& v);
  void ascent(const ValidatedFrame& v);
  void release(const ValidatedFrame& v);
  void chute(const ValidatedFrame& v, bool chute_requested);
  void descent(const ValidatedFrame& v);
  void landing(const ValidatedFrame& v);
  float accelMag(const ImuSample& m) const;

  const FlightParams& p_;
  IEventSink& out_;
  bool complete_;
  bool params_fail_emitted_ = false;

  // parameter copies (valid only when complete_)
  uint32_t t_db_ = 0, t_ff_ = 0, w_b_ = 0, t_confirm_ = 0, fallback_ = 0;
  uint32_t sc_samples_ = 0, asc_ms_ = 0, land_ms_ = 0, desc_ms_ = 0;
  uint32_t faults_ = 0;
  bool open_high_[kSwitchCount] = {false, false};
  bool sc_need_power_ = false;
  SwitchVote vote_ = SwitchVote::Unset;
  StuckSwitchPolicy policy_ = StuckSwitchPolicy::Unset;
  float a_ff_ = 0, dh_min_ = 0, asc_gain_ = 0, chute_g_ = 0, land_dalt_ = 0, land_tol_ = 0;
  float land_agl_ = 0;

  // ground reference
  bool has_ground_ = false;
  float ground_pa_ = 0.0f;
  bool has_local_ref_ = false;
  float local_ref_pa_ = 0.0f;

  // switches
  bool sw_known_[kSwitchCount] = {false, false};
  bool sw_stable_[kSwitchCount] = {false, false};
  bool sw_cand_[kSwitchCount] = {false, false};
  bool sw_cand_set_[kSwitchCount] = {false, false};
  uint32_t sw_cand_since_[kSwitchCount] = {0, 0};
  bool mount_known_ = false;
  bool mount_open_ = false;

  // free fall
  bool below_ = false;
  uint32_t below_since_ = 0;
  bool freefall_ = false;
  bool imu_ever_rejected_ = false;
  uint32_t last_imu_reject_ = 0;

  // baro
  uint32_t hist_t_[kBaroHistory] = {};
  float hist_alt_[kBaroHistory] = {};
  int hist_n_ = 0, hist_head_ = 0;
  bool baro_desc_ = false;
  bool alt_valid_ = false;
  float alt_now_ = 0.0f;
  bool baro_ever_rejected_ = false;
  uint32_t last_baro_reject_ = 0;

  // self-check
  uint32_t sc_count_ = 0;
  double sc_sum_pa_ = 0.0;
  bool sc_done_ = false;

  // ascent
  bool asc_above_ = false;
  uint32_t asc_since_ = 0;
  bool asc_done_ = false;

  // release
  bool cand_active_ = false, cand_emitted_ = false;
  uint32_t cand_t_ = 0;
  bool uncorroborated_emitted_ = false, sensors_only_emitted_ = false;
  bool so_active_ = false;
  uint32_t so_since_ = 0;
  bool confirmed_ = false;

  // chute
  bool chute_done_ = false;

  // descent confirmation (PANEL_DEPLOY -> DESCENT)
  bool desc_active_ = false;
  uint32_t desc_since_ = 0;
  bool desc_done_ = false;

  // landing
  bool unconfirmable_emitted_ = false;
  bool stable_ = false;
  uint32_t stable_since_ = 0;
  float stable_ref_alt_ = 0.0f;
  bool touchdown_done_ = false;
};

}  // namespace cansat
