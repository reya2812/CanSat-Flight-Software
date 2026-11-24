// Phase 2 step 3 tests: validator, event detector, recovery, state machine,
// and every SYNTHETIC scenario x every OD-060 candidate policy.
// [SIMULATED] Software behaviour only. Actuator logic is disabled throughout:
// "requests" are queued/logged and never executed.
#include <cmath>
#include <string>
#include <vector>

#include "EventDetector.h"
#include "FlightSoftware.h"
#include "FlightStateManager.h"
#include "FswHook.h"
#include "MemoryLogSink.h"
#include "MockPersistentStore.h"
#include "RecoveryManager.h"
#include "SensorValidator.h"
#include "SimRunner.h"
#include "TestHarness.h"
#include "scenarios/SyntheticFlightParams.h"
#include "scenarios/SyntheticScenarios.h"

using namespace cansat;
using namespace cansat::mock;
using namespace cansat::sim;

// ---------- SYNTHETIC test values ----------
static const float SYNTHETIC_P_PA = 100000.0f;
static const float SYNTHETIC_DROP_PA = 400.0f;  // ~ 33 m at sea level, well above any SYNTHETIC drop threshold
static const uint32_t SYNTHETIC_DT = 50;

namespace {

class CollectSink : public IEventSink {
 public:
  std::vector<Event> events;
  void onEvent(const Event& e) override { events.push_back(e); }
  int count(EventType t) const {
    int n = 0;
    for (const Event& e : events) n += (e.type == t);
    return n;
  }
  void clear() { events.clear(); }
};

Event ev(EventType t, uint32_t now, uint32_t detail = 0) {
  Event e;
  e.type = t;
  e.t_ms = now;
  e.detail = detail;
  return e;
}

// Fresh FSM bundle with SYNTHETIC complete params (policy irrelevant to FSM).
struct FsmRig {
  FlightParams params = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  MockPersistentStore store;
  RecoveryManager rec{store};
  CollectSink out;
  FlightStateManager fsm{params, rec, out};
  void start(uint32_t now = 0) { fsm.start(rec.restoreOnBoot(), now); }
  int drainRequests() {
    int n = 0;
    ActuatorRequest r;
    while (fsm.popRequest(r)) {
      CHECK(r == ActuatorRequest::ReleaseParachute);
      ++n;
    }
    return n;
  }
};

void driveTo(FsmRig& r, FlightState target) {
  uint32_t t = 0;
  if (target >= FlightState::ReadyOnDrone) r.fsm.onEvent(ev(EventType::SelfCheckPass, t += 10));
  if (target >= FlightState::Ascent) r.fsm.onEvent(ev(EventType::AscentDetected, t += 10));
  if (target >= FlightState::ReleaseDetected) r.fsm.onEvent(ev(EventType::ReleaseCandidate, t += 10));
  if (target >= FlightState::ParachuteDeploy) r.fsm.onEvent(ev(EventType::ReleaseConfirmed, t += 10, 1));
}

ValidatedFrame vf(uint32_t now, bool sw_open, float amag_g, float pressure_pa, bool imu_ok = true,
                  bool baro_ok = true) {
  ValidatedFrame v;
  v.now_ms = now;
  v.baro_ok = baro_ok;
  v.imu_ok = imu_ok;
  v.power_ok = true;
  v.switches_ok = true;
  v.raw.baro.valid = baro_ok;
  v.raw.baro.t_ms = now;
  v.raw.baro.pressure_pa = pressure_pa;
  v.raw.imu.valid = imu_ok;
  v.raw.imu.t_ms = now;
  v.raw.imu.az_g = amag_g;
  v.raw.switches.valid = true;
  v.raw.switches.raw[0] = sw_open;  // SYNTHETIC wiring: open = HIGH
  v.raw.switches.raw[1] = sw_open;
  return v;
}

SensorFrame goodFrame(uint32_t now) {
  SensorFrame f;
  f.baro.valid = true;
  f.baro.t_ms = now;
  f.baro.pressure_pa = SYNTHETIC_P_PA;
  f.baro.temp_c = 20.0f;
  f.baro.comm_ok = f.baro.data_ready = true;
  f.imu.valid = true;
  f.imu.t_ms = now;
  f.imu.az_g = 1.0f;
  f.imu.comm_ok = f.imu.data_ready = true;
  f.power.valid = true;
  f.power.t_ms = now;
  f.power.bus_v = 3.8f;
  f.power.current_ma = 100.0f;
  f.power.comm_ok = f.power.data_ready = true;
  f.switches.valid = true;
  f.switches.t_ms = now;
  return f;
}

struct MatrixRun {
  FswStats stats;
  MemoryLogSink log;
};

void runFsw(const std::string& scenario, StuckSwitchPolicy pol, MatrixRun& out) {
  Scenario sc;
  CHECK(findSyntheticScenario(scenario, sc));
  FlightSoftwareHook hook(syntheticFlightParams(pol));
  SimRunner r;
  r.run(sc, out.log, &hook);
  out.stats = hook.stats();
}

std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> o;
  std::string c;
  for (char ch : s) {
    if (ch == sep) {
      o.push_back(c);
      c.clear();
    } else {
      c += ch;
    }
  }
  o.push_back(c);
  return o;
}

// truth_mounted column (index 6) of the row in which a request was logged; -1 if none.
int truthMountedAtRequest(const MemoryLogSink& log) {
  for (const std::string& l : log.lines) {
    if (l.empty() || l[0] == '#' || l.find("REQUEST:") == std::string::npos) continue;
    const std::vector<std::string> c = split(l, ',');
    return c[6] == "1" ? 1 : 0;
  }
  return -1;
}

}  // namespace

// ======================= State machine: transition table =======================
TEST_CASE(fsm_permitted_transitions_are_the_slide19_chain_plus_two_flagged_landings) {
  int permitted = 0;
  for (uint8_t f = 1; f <= kFlightStateCount; ++f) {
    for (uint8_t t = 1; t <= kFlightStateCount; ++t) {
      const bool ok = FlightStateManager::isPermitted(static_cast<FlightState>(f), static_cast<FlightState>(t));
      const bool abnormal_landing = (t == 8) && (f == 5 || f == 6);  // OD-065, flagged
      CHECK(ok == (t == f + 1 || abnormal_landing));
      permitted += ok;
    }
  }
  CHECK(permitted == 9);
  CHECK(!FlightStateManager::isPermitted(FlightState::Landed, FlightState::PowerOnSelfCheck));
  CHECK(!FlightStateManager::isPermitted(static_cast<FlightState>(0), FlightState::PowerOnSelfCheck));
}

TEST_CASE(fsm_nominal_event_sequence_reaches_landed_with_one_request) {
  FsmRig r;
  r.start();
  CHECK(r.fsm.state() == FlightState::PowerOnSelfCheck);
  r.fsm.onEvent(ev(EventType::SelfCheckPass, 100));
  r.fsm.onEvent(ev(EventType::AscentDetected, 200));
  r.fsm.onEvent(ev(EventType::ReleaseCandidate, 300));
  CHECK(r.fsm.state() == FlightState::ReleaseDetected);
  r.fsm.onEvent(ev(EventType::ReleaseConfirmed, 350, kBasisSwitchAndFreefall));
  CHECK(r.fsm.state() == FlightState::ParachuteDeploy);
  r.fsm.tick(600);  // 250 ms < SYNTHETIC 300 ms separation
  CHECK(r.drainRequests() == 0);
  r.fsm.tick(650);
  CHECK(r.drainRequests() == 1);
  r.fsm.onEvent(ev(EventType::ChuteOpenDetected, 900));
  CHECK(r.fsm.state() == FlightState::PanelDeploy);
  CHECK(r.fsm.chuteStatus() == ChuteStatus::OpeningSensed);
  for (uint32_t t = 900; t < 60000; t += 1000) r.fsm.tick(t);  // time alone never advances
  CHECK(r.fsm.state() == FlightState::PanelDeploy);
  CHECK(r.fsm.panelStatus() == PanelStatus::UnknownNoSensor);
  r.fsm.onEvent(ev(EventType::DescentConfirmed, 60000));
  CHECK(r.fsm.state() == FlightState::Descent);
  r.fsm.onEvent(ev(EventType::TouchdownDetected, 65000));
  CHECK(r.fsm.state() == FlightState::Landed);
  CHECK(r.out.count(EventType::TransitionRejected) == 0);
  CHECK(r.out.count(EventType::StateChanged) == 7);
  CHECK(r.fsm.requestsEmitted() == 1);
}

TEST_CASE(fsm_confirm_from_ascent_takes_two_legal_steps) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::Ascent);
  r.fsm.onEvent(ev(EventType::ReleaseConfirmed, 500, kBasisSensorsOnlyPolicy));
  CHECK(r.fsm.state() == FlightState::ParachuteDeploy);
  CHECK(r.out.count(EventType::StateChanged) == 4);
}

TEST_CASE(fsm_rejects_events_in_wrong_state_and_does_not_move) {
  FsmRig r;
  r.start();
  r.fsm.onEvent(ev(EventType::AscentDetected, 10));
  r.fsm.onEvent(ev(EventType::TouchdownDetected, 20));
  r.fsm.onEvent(ev(EventType::ReleaseCandidate, 30));
  r.fsm.onEvent(ev(EventType::ReleaseConfirmed, 40));
  CHECK(r.fsm.state() == FlightState::PowerOnSelfCheck);
  CHECK(r.out.count(EventType::TransitionRejected) == 4);
  CHECK(r.fsm.requestsEmitted() == 0);
  // From LANDED nothing moves.
  FsmRig l;
  l.start();
  driveTo(l, FlightState::ParachuteDeploy);
  l.fsm.tick(10000);
  l.fsm.onEvent(ev(EventType::ChuteOpenDetected, 10001));
  l.fsm.tick(20000);
  l.fsm.onEvent(ev(EventType::TouchdownDetected, 20001));
  CHECK(l.fsm.state() == FlightState::Landed);
  l.out.clear();
  l.fsm.onEvent(ev(EventType::SelfCheckPass, 20002));
  l.fsm.onEvent(ev(EventType::TouchdownDetected, 20003));
  CHECK(l.fsm.state() == FlightState::Landed);
  CHECK(l.out.count(EventType::TransitionRejected) == 2);
}

TEST_CASE(fsm_chute_open_before_request_is_rejected) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  r.fsm.onEvent(ev(EventType::ChuteOpenDetected, 45));  // before T_SEP_MIN request
  CHECK(r.fsm.state() == FlightState::ParachuteDeploy);
  CHECK(r.out.count(EventType::TransitionRejected) == 1);
}

TEST_CASE(fsm_duplicate_release_events_and_ticks_give_exactly_one_request) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  for (int i = 0; i < 5; ++i) {
    r.fsm.onEvent(ev(EventType::ReleaseConfirmed, 50 + i, 1));
    r.fsm.onEvent(ev(EventType::ReleaseCandidate, 50 + i));
  }
  int total = 0;
  for (uint32_t t = 100; t < 2900; t += SYNTHETIC_DT) {
    r.fsm.tick(t);
    total += r.drainRequests();
  }
  CHECK(total == 1);
  CHECK(r.fsm.requestsEmitted() == 1);
  CHECK(r.fsm.chuteRequested());
}

TEST_CASE(fsm_degraded_release_events_raise_flag_without_transition) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::Ascent);
  r.fsm.onEvent(ev(EventType::ReleaseSensorsOnly, 100));
  CHECK(r.fsm.state() == FlightState::Ascent);
  CHECK((r.fsm.faultMask() & kFaultReleaseDegraded) != 0);
}

TEST_CASE(fsm_chute_timeout_is_an_alarm_never_a_transition) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  r.fsm.tick(400);  // request
  CHECK(r.drainRequests() == 1);
  CHECK(r.fsm.chuteStatus() == ChuteStatus::RequestedAwaitingOpening);
  r.fsm.tick(3399);
  CHECK(r.out.count(EventType::ChuteOpenNotConfirmed) == 0);
  for (uint32_t t = 3400; t < 600000; t += 1000) r.fsm.tick(t);  // SYNTHETIC 3000 ms timeout and far beyond
  CHECK(r.fsm.state() == FlightState::ParachuteDeploy);  // never assumed open
  CHECK(r.fsm.chuteStatus() == ChuteStatus::OpeningNotSensedTimeout);
  CHECK(r.out.count(EventType::ChuteOpenNotConfirmed) == 1);
  CHECK((r.fsm.faultMask() & kFaultChuteOpenNotSensed) != 0);
  CHECK(r.out.count(EventType::StateChanged) == 4);  // no transition after reaching PARACHUTE_DEPLOY
  // A confirmed touchdown is still accepted from here (abnormal, flagged path).
  r.fsm.onEvent(ev(EventType::TouchdownDetected, 600001));
  CHECK(r.fsm.state() == FlightState::Landed);
  CHECK(r.fsm.chuteStatus() == ChuteStatus::OpeningNotSensedTimeout);
}

TEST_CASE(fsm_late_sensed_opening_after_alarm_still_advances) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  r.fsm.tick(400);
  r.fsm.tick(5000);  // alarm raised
  r.fsm.onEvent(ev(EventType::ChuteOpenDetected, 5100));
  CHECK(r.fsm.state() == FlightState::PanelDeploy);
  CHECK(r.fsm.chuteStatus() == ChuteStatus::OpeningSensed);
}

TEST_CASE(fsm_descent_confirmed_outside_panel_deploy_is_rejected) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  r.fsm.onEvent(ev(EventType::DescentConfirmed, 100));
  CHECK(r.fsm.state() == FlightState::ParachuteDeploy);
  CHECK(r.out.count(EventType::TransitionRejected) == 1);
}

TEST_CASE(fsm_incomplete_params_never_request) {
  FlightParams empty;  // nothing set: no defaults exist
  MockPersistentStore store;
  RecoveryManager rec(store);
  CollectSink out;
  FlightStateManager fsm(empty, rec, out);
  fsm.start(rec.restoreOnBoot(), 0);
  fsm.onEvent(ev(EventType::SelfCheckPass, 1));
  fsm.onEvent(ev(EventType::AscentDetected, 2));
  fsm.onEvent(ev(EventType::ReleaseConfirmed, 3, 1));
  for (uint32_t t = 0; t < 100000; t += 1000) fsm.tick(t);
  ActuatorRequest req;
  CHECK(!fsm.popRequest(req));
  CHECK(fsm.requestsEmitted() == 0);
}

// ======================= Persistence and reset recovery =======================
TEST_CASE(fsm_persists_every_transition_and_flag) {
  FsmRig r;
  r.start();
  const int before = r.store.writes;
  driveTo(r, FlightState::ParachuteDeploy);
  CHECK(r.store.record().last_state == static_cast<uint8_t>(FlightState::ParachuteDeploy));
  CHECK(r.store.record().one_shot_flags & kOneShotReleaseConfirmed);
  CHECK(r.store.writes - before >= 5);
  CHECK(r.store.record().crc == recoveryCrc(r.store.record()));
}

TEST_CASE(recovery_without_record_starts_self_check) {
  MockPersistentStore store;
  RecoveryManager rec(store);
  const RestoreResult rr = rec.restoreOnBoot();
  CHECK(!rr.had_record && !rr.corrupt && !rr.resumed);
  CHECK(rr.state == FlightState::PowerOnSelfCheck && rr.boot_count == 1);
  CHECK(store.has());
}

TEST_CASE(recovery_corrupt_record_restarts_safe_and_flags_fault) {
  FsmRig a;
  a.start();
  driveTo(a, FlightState::ParachuteDeploy);
  a.store.corrupt();
  RecoveryManager rec(a.store);
  CollectSink out;
  FlightStateManager fsm(a.params, rec, out);
  const RestoreResult rr = rec.restoreOnBoot();
  CHECK(rr.corrupt && !rr.resumed);
  fsm.start(rr, 0);
  CHECK(fsm.state() == FlightState::PowerOnSelfCheck);
  CHECK(fsm.faultMask() & kFaultRecoveryRecordCorrupt);
}

TEST_CASE(recovery_ground_states_restart_at_self_check) {
  FsmRig a;
  a.start();
  driveTo(a, FlightState::ReadyOnDrone);
  RecoveryManager rec(a.store);
  const RestoreResult rr = rec.restoreOnBoot();
  CHECK(!rr.resumed && rr.state == FlightState::PowerOnSelfCheck && rr.boot_count == 2);
}

TEST_CASE(recovery_after_request_resumes_without_second_request) {
  FsmRig a;
  a.start();
  driveTo(a, FlightState::ParachuteDeploy);
  a.fsm.tick(1000);
  CHECK(a.drainRequests() == 1);
  // --- simulated reset: RAM objects gone, store kept ---
  RecoveryManager rec(a.store);
  CollectSink out;
  FlightStateManager fsm(a.params, rec, out);
  const RestoreResult rr = rec.restoreOnBoot();
  CHECK(rr.resumed && rr.state == FlightState::ParachuteDeploy && rr.boot_count == 2);
  fsm.start(rr, 0);
  CHECK(out.count(EventType::ResetRecovered) == 1);
  CHECK(out.count(EventType::RequestSuppressed) == 1);
  for (uint32_t t = 0; t < 2000; t += SYNTHETIC_DT) fsm.tick(t);
  ActuatorRequest req;
  CHECK(!fsm.popRequest(req));
  CHECK(fsm.requestsEmitted() == 0);
}

TEST_CASE(recovery_before_request_requests_once_after_restarted_separation_timer) {
  FsmRig a;
  a.start();
  driveTo(a, FlightState::ParachuteDeploy);  // confirmed, request not yet due
  RecoveryManager rec(a.store);
  CollectSink out;
  FlightStateManager fsm(a.params, rec, out);
  fsm.start(rec.restoreOnBoot(), 0);
  fsm.tick(299);
  ActuatorRequest req;
  CHECK(!fsm.popRequest(req));
  fsm.tick(300);
  CHECK(fsm.popRequest(req));
  fsm.tick(400);
  CHECK(!fsm.popRequest(req));
}

TEST_CASE(persist_failure_raises_fault_and_still_requests_only_once) {
  FsmRig r;
  r.start();
  driveTo(r, FlightState::ParachuteDeploy);
  r.store.fail_writes = true;
  int total = 0;
  for (uint32_t t = 0; t < 2000; t += SYNTHETIC_DT) {
    r.fsm.tick(t);
    total += r.drainRequests();
  }
  CHECK(total == 1);
  CHECK(r.fsm.faultMask() & kFaultPersistWrite);
}

// ======================= Validator =======================
TEST_CASE(validator_accepts_good_frames_and_rejects_each_bad_kind) {
  const FlightParams fp = syntheticFlightParams(StuckSwitchPolicy::Vote2of3);
  SensorValidator v(fp);
  ValidatedFrame f = v.validate(goodFrame(0), 0);
  CHECK(f.baro_ok && f.imu_ok && f.power_ok && f.switches_ok && v.faultMask() == 0);

  SensorFrame s = goodFrame(50);
  s.baro.valid = false;
  s.imu.ax_g = std::nanf("");
  s.power.current_ma = 99999.0f;
  s.switches.valid = false;
  f = v.validate(s, 50);
  CHECK(f.baro_reject == kRejectInvalidFlag && f.imu_reject == kRejectNonFinite);
  CHECK(f.power_reject == kRejectRange && f.switches_reject == kRejectInvalidFlag);
  CHECK(v.newlyFaulted() == (kFaultBaroInvalid | kFaultImuInvalid | kFaultPowerInvalid | kFaultSwitchInvalid));

  s = goodFrame(100);
  s.imu.az_g = 0.0f;  // all six axes exactly zero
  s.baro.pressure_pa = 0.0f;
  s.baro.temp_c = 0.0f;
  f = v.validate(s, 100);
  CHECK(f.imu_reject == kRejectZeroRead && f.baro_reject == kRejectZeroRead);
  CHECK(v.newlyRecovered() == (kFaultPowerInvalid | kFaultSwitchInvalid));  // those were fine again at 100

  s = goodFrame(150);
  s.imu.az_g = 17.0f;  // beyond the ±16 g full scale: impossible
  s.baro.pressure_pa = 5000.0f;
  f = v.validate(s, 150);
  CHECK(f.imu_reject == kRejectRange && f.baro_reject == kRejectRange);

  f = v.validate(goodFrame(200), 200);
  CHECK(f.baro_ok && f.imu_ok && f.power_ok && f.switches_ok);
  CHECK(v.newlyRecovered() == (kFaultBaroInvalid | kFaultImuInvalid));
  CHECK(v.faultMask() == 0);
}

TEST_CASE(validator_detects_stale_by_repeat_and_by_age) {
  const FlightParams fp = syntheticFlightParams(StuckSwitchPolicy::Vote2of3);  // SYNTHETIC stale 200 ms
  SensorValidator v(fp);
  v.validate(goodFrame(100), 100);
  SensorFrame repeat = goodFrame(150);
  repeat.imu.t_ms = 100;  // timestamp did not advance
  ValidatedFrame f = v.validate(repeat, 150);
  CHECK(f.imu_reject == kRejectStaleRepeat && f.baro_ok);
  SensorFrame old = goodFrame(1000);
  old.baro.t_ms = 700;  // 300 ms old > 200 ms
  f = v.validate(old, 1000);
  CHECK(f.baro_reject == kRejectStaleAge);
}

TEST_CASE(validator_saturation_is_flagged_but_not_invalid) {
  const FlightParams fp = syntheticFlightParams(StuckSwitchPolicy::Vote2of3);
  SensorValidator v(fp);
  SensorFrame s = goodFrame(0);
  s.imu.az_g = 16.0f;
  s.imu.saturated = true;
  const ValidatedFrame f = v.validate(s, 0);
  CHECK(f.imu_ok);
  CHECK(v.faultMask() & kFaultImuSaturated);
}

// ======================= Event detector =======================
TEST_CASE(detector_with_incomplete_params_emits_only_selfcheck_fail) {
  FlightParams empty;
  CollectSink out;
  EventDetector d(empty, out);
  for (uint32_t t = 0; t < 2000; t += SYNTHETIC_DT) {
    d.update(vf(t, true, 0.0f, SYNTHETIC_P_PA - t), FlightState::Ascent, false);
  }
  CHECK(out.events.size() == 1);
  CHECK(out.events[0].type == EventType::SelfCheckFail && out.events[0].detail == kFaultParamsIncomplete);
}

TEST_CASE(detector_self_check_needs_consecutive_good_frames_with_mount_closed) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = 0;
  for (int i = 0; i < 20; ++i, t += SYNTHETIC_DT) d.update(vf(t, true, 1.0f, SYNTHETIC_P_PA), FlightState::PowerOnSelfCheck, false);
  CHECK(out.count(EventType::SelfCheckPass) == 0);  // mount open: not ready on drone
  for (int i = 0; i < 20; ++i, t += SYNTHETIC_DT) d.update(vf(t, false, 1.0f, SYNTHETIC_P_PA), FlightState::PowerOnSelfCheck, false);
  CHECK(out.count(EventType::SelfCheckPass) == 1);
  CHECK(d.hasGroundReference() && std::fabs(d.groundPressurePa() - SYNTHETIC_P_PA) < 0.01f);
}

TEST_CASE(detector_switch_debounce_and_not_armed_before_ascent) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC debounce 100 ms
  CollectSink out;
  EventDetector d(p, out);
  d.update(vf(0, false, 1.0f, SYNTHETIC_P_PA), FlightState::ReadyOnDrone, false);
  d.update(vf(100, false, 1.0f, SYNTHETIC_P_PA), FlightState::ReadyOnDrone, false);
  d.update(vf(150, true, 1.0f, SYNTHETIC_P_PA), FlightState::ReadyOnDrone, false);
  d.update(vf(300, true, 1.0f, SYNTHETIC_P_PA), FlightState::ReadyOnDrone, false);
  CHECK(d.mountOpen());
  CHECK(out.count(EventType::ReleaseCandidate) == 0);  // not armed in READY_ON_DRONE
  CollectSink out2;
  EventDetector d2(p, out2);
  d2.update(vf(0, false, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d2.update(vf(100, false, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d2.update(vf(150, true, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d2.update(vf(200, false, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);  // bounce
  d2.update(vf(250, true, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  CHECK(!d2.mountOpen());
  CHECK(out2.count(EventType::ReleaseCandidate) == 0);
  d2.update(vf(350, true, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  CHECK(d2.mountOpen());
  CHECK(out2.count(EventType::ReleaseCandidate) == 1);
}

TEST_CASE(detector_freefall_needs_duration_and_invalid_sample_resets_it) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC 0.3 g / 150 ms
  CollectSink out;
  EventDetector d(p, out);
  d.update(vf(0, false, 0.05f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d.update(vf(100, false, 0.05f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  CHECK(!d.freefall());
  d.update(vf(150, false, 0.05f, SYNTHETIC_P_PA, false), FlightState::Ascent, false);  // IMU invalid
  d.update(vf(200, false, 0.05f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d.update(vf(300, false, 0.05f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  CHECK(!d.freefall());
  d.update(vf(350, false, 0.05f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  CHECK(d.freefall());
}

TEST_CASE(detector_baro_descent_uses_window_and_valid_samples_only) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC 1 m over 500 ms
  CollectSink out;
  EventDetector d(p, out);
  d.update(vf(0, false, 1.0f, SYNTHETIC_P_PA), FlightState::Ascent, false);
  d.update(vf(400, false, 1.0f, SYNTHETIC_P_PA + SYNTHETIC_DROP_PA), FlightState::Ascent, false);
  CHECK(!d.baroDescent());  // window not yet covered
  d.update(vf(500, false, 1.0f, SYNTHETIC_P_PA + SYNTHETIC_DROP_PA), FlightState::Ascent, false);
  CHECK(d.baroDescent());
  d.update(vf(550, false, 1.0f, SYNTHETIC_P_PA + SYNTHETIC_DROP_PA, true, false), FlightState::Ascent, false);
  CHECK(!d.baroDescent());  // invalid sample: no evidence
}

// Stuck-switch evidence: switch reads mounted, free fall + baro descent present.
static void feedSensorsOnly(EventDetector& d, uint32_t from, uint32_t to, bool imu_glitch_at_start) {
  for (uint32_t t = from; t <= to; t += SYNTHETIC_DT) {
    const float p = SYNTHETIC_P_PA + SYNTHETIC_DROP_PA * static_cast<float>(t - from) / 500.0f;
    const bool imu_ok = !(imu_glitch_at_start && t == from + 3 * SYNTHETIC_DT);
    d.update(vf(t, false, 0.05f, p, imu_ok), FlightState::Ascent, false);
  }
}

TEST_CASE(detector_policy_A_strict_never_confirms_sensors_only) {
  CollectSink out;
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  EventDetector d(p, out);
  feedSensorsOnly(d, 0, 3000, false);
  CHECK(out.count(EventType::ReleaseConfirmed) == 0);
  CHECK(out.count(EventType::ReleaseSensorsOnly) == 1);
}

TEST_CASE(detector_policy_B_override_confirms_only_without_recent_rejects) {
  {
    CollectSink out;
    FlightParams p = syntheticFlightParams(StuckSwitchPolicy::SensorOverride);
    EventDetector d(p, out);
    feedSensorsOnly(d, 0, 3000, false);
    CHECK(out.count(EventType::ReleaseConfirmed) == 1);
    CHECK(out.events.back().detail == kBasisSensorsOnlyPolicy);
  }
  {
    CollectSink out;
    FlightParams p = syntheticFlightParams(StuckSwitchPolicy::SensorOverride);
    EventDetector d(p, out);
    feedSensorsOnly(d, 0, 800, true);  // IMU rejected at 150 ms; window SYNTHETIC 1000 ms
    CHECK(out.count(EventType::ReleaseConfirmed) == 0);
    CHECK(out.count(EventType::ReleaseSensorsOnly) == 1);
  }
}

TEST_CASE(detector_policy_C_vote_confirms_on_two_of_three) {
  CollectSink out;
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::Vote2of3);
  EventDetector d(p, out);
  feedSensorsOnly(d, 0, 3000, false);
  CHECK(out.count(EventType::ReleaseConfirmed) == 1);
  CHECK(out.count(EventType::ReleaseSensorsOnly) == 0);
}

TEST_CASE(detector_policy_G_fallback_confirms_after_delay) {
  CollectSink out;
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::DelayedFallback);  // SYNTHETIC 300 ms
  EventDetector d(p, out);
  feedSensorsOnly(d, 0, 3000, false);
  CHECK(out.count(EventType::ReleaseSensorsOnly) == 1);
  CHECK(out.count(EventType::ReleaseConfirmed) == 1);
  uint32_t t_so = 0, t_conf = 0;
  for (const Event& e : out.events) {
    if (e.type == EventType::ReleaseSensorsOnly) t_so = e.t_ms;
    if (e.type == EventType::ReleaseConfirmed) t_conf = e.t_ms;
  }
  CHECK(t_conf - t_so >= 300);
}

TEST_CASE(detector_release_latches_once) {
  CollectSink out;
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::Vote2of3);
  EventDetector d(p, out);
  feedSensorsOnly(d, 0, 6000, false);
  CHECK(out.count(EventType::ReleaseConfirmed) == 1);
  CHECK(d.releaseLatched());
}

// ======================= FlightSoftware composition =======================
TEST_CASE(flight_software_with_incomplete_params_stays_in_self_check) {
  FlightParams empty;
  MockPersistentStore store;
  FlightSoftware fs(empty, store);
  BootReport br;
  br.baro_ok = br.imu_ok = br.power_ok = true;
  fs.boot(br, 0);
  for (uint32_t t = 0; t < 5000; t += SYNTHETIC_DT) fs.tick(goodFrame(t), t);
  CHECK(fs.state() == FlightState::PowerOnSelfCheck);
  CHECK(fs.faultMask() & kFaultParamsIncomplete);
  CHECK(fs.requestsEmitted() == 0);
}

// ======================= Scenario x policy matrix =======================
TEST_CASE(every_scenario_every_policy_is_safe_structurally) {
  const std::vector<Scenario> all = allSyntheticScenarios();
  CHECK(all.size() == 13);
  for (const Scenario& sc : all) {
    for (StuckSwitchPolicy pol : candidatePolicies()) {
      MatrixRun run;
      runFsw(sc.name, pol, run);
      CHECK(run.stats.requests <= 1);                // never a duplicate request
      CHECK(run.stats.rejected_transitions == 0);    // detector never asks for a forbidden move
      for (size_t i = 1; i < run.stats.states_entered.size(); ++i) {  // strictly forward
        CHECK(static_cast<int>(run.stats.states_entered[i]) ==
              static_cast<int>(run.stats.states_entered[i - 1]) + 1);
      }
      bool labelled = false;
      for (const std::string& l : run.log.lines) {
        if (l.find("ACTUATOR LOGIC DISABLED") != std::string::npos) labelled = true;
        if (l.find("REQUEST:") != std::string::npos) CHECK(l.find("NOT_EXECUTED") != std::string::npos);
      }
      CHECK(labelled);
    }
  }
}

TEST_CASE(matrix_is_deterministic) {
  MatrixRun a, b;
  runFsw("reset_mid_flight", StuckSwitchPolicy::Vote2of3, a);
  runFsw("reset_mid_flight", StuckSwitchPolicy::Vote2of3, b);
  CHECK(a.log.lines == b.log.lines);
}

TEST_CASE(healthy_switch_scenarios_land_with_one_request_under_every_policy) {
  const char* names[] = {"nominal", "baro_dropout", "stale_imu", "invalid_values", "switch_bounce",
                         "reset_mid_flight"};
  for (const char* n : names) {
    for (StuckSwitchPolicy pol : candidatePolicies()) {
      MatrixRun run;
      runFsw(n, pol, run);
      CHECK(run.stats.final_state == FlightState::Landed);
      CHECK(run.stats.requests == 1);
      CHECK(run.stats.sensors_only_events == 0);
      CHECK(truthMountedAtRequest(run.log) == 0);  // requested only after true release
    }
  }
}

TEST_CASE(stale_imu_release_is_confirmed_by_baro_path) {
  MatrixRun run;
  runFsw("stale_imu", StuckSwitchPolicy::StrictSwitchVeto, run);
  CHECK(run.stats.last_release_basis == kBasisSwitchAndBaro);
}

TEST_CASE(noisy_scenario_finding_descent_and_landing_not_confirmed_with_synthetic_tolerances) {
  // SIMULATED finding, not a pass criterion: with SYNTHETIC tolerances, extra
  // noise prevents DESCENT confirmation and TOUCHDOWN. Nothing is assumed.
  MatrixRun run;
  runFsw("noisy", StuckSwitchPolicy::StrictSwitchVeto, run);
  CHECK(run.stats.requests == 1);
  CHECK(run.stats.final_state == FlightState::PanelDeploy);
  CHECK(run.stats.final_chute == ChuteStatus::OpeningSensed);
}

TEST_CASE(od060_S4_stuck_switch_really_released_per_policy) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    MatrixRun run;
    runFsw("stuck_switch_released", pol, run);
    if (pol == StuckSwitchPolicy::StrictSwitchVeto) {
      CHECK(run.stats.requests == 0);  // P-A: no parachute although really released
      CHECK(run.stats.final_state == FlightState::Ascent);
      CHECK(run.stats.sensors_only_events == 1);
      CHECK(run.stats.final_faults & kFaultReleaseDegraded);
    } else {
      CHECK(run.stats.requests == 1);  // P-B/P-C/P-G: requested on sensor evidence
      CHECK(run.stats.last_release_basis == kBasisSensorsOnlyPolicy);
      CHECK(truthMountedAtRequest(run.log) == 0);
    }
  }
}

TEST_CASE(od060_S4b_mounted_with_zeroed_imu_no_policy_requests) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    MatrixRun run;
    runFsw("mounted_imu_zero", pol, run);
    CHECK(run.stats.requests == 0);
    CHECK(run.stats.final_state == FlightState::Ascent);
    // Protection here comes from the validator rejecting all-zero IMU reads,
    // not from the policy itself.
    bool zero_rejected = false;
    for (const std::string& l : run.log.lines) {
      if (l.find("SensorFault:0x2") != std::string::npos) zero_rejected = true;
    }
    CHECK(zero_rejected);
  }
}

TEST_CASE(od060_S4c_mounted_drone_falling_hazard_under_sensor_policies) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    MatrixRun run;
    runFsw("mounted_drone_falling", pol, run);
    if (pol == StuckSwitchPolicy::StrictSwitchVeto) {
      CHECK(run.stats.requests == 0);  // P-A blocks: CanSat really is mounted
    } else {
      CHECK(run.stats.requests == 1);  // P-B/P-C/P-G request WHILE STILL MOUNTED (hazard, OD-060)
      CHECK(truthMountedAtRequest(run.log) == 1);
      // Correction (review item 1/4): no false LANDED, no assumed opening.
      CHECK(run.stats.final_state == FlightState::ParachuteDeploy);
      CHECK(run.stats.final_chute == ChuteStatus::OpeningNotSensedTimeout);
      CHECK(run.stats.chute_not_confirmed_alarms == 1);
    }
    CHECK(run.stats.final_state != FlightState::Landed);
  }
}

TEST_CASE(reset_mid_flight_recovers_twice_and_never_repeats_request) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    MatrixRun run;
    runFsw("reset_mid_flight", pol, run);
    CHECK(run.stats.resets_recovered == 2);
    CHECK(run.stats.suppressed_requests == 2);
    CHECK(run.stats.requests == 1);
    CHECK(run.stats.final_state == FlightState::Landed);
  }
}

TEST_CASE(imu_not_detected_blocks_self_check_and_requests) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    MatrixRun run;
    runFsw("imu_not_detected", pol, run);
    CHECK(run.stats.final_state == FlightState::PowerOnSelfCheck);
    CHECK(run.stats.requests == 0);
    CHECK(run.stats.final_faults & kFaultSelfCheck);
  }
}

int main() { return th::runAll(); }
