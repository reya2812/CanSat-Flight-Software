// Step 3 review tests (landing confirmation, timeouts, IMU health evidence,
// persistence-failure policies). [SIMULATED] software behaviour only.
// SYNTHETIC_* values are test-only. Actuator logic is disabled: "requests" are
// queued and counted, never executed.
#include <cmath>
#include <string>
#include <vector>

#include "EventDetector.h"
#include "FlightProfile.h"
#include "FlightSoftware.h"
#include "FlightStateManager.h"
#include "FswHook.h"
#include "MemoryLogSink.h"
#include "MockPersistentStore.h"
#include "MockSensors.h"
#include "RecoveryManager.h"
#include "SensorValidator.h"
#include "SimRunner.h"
#include "TestHarness.h"
#include "scenarios/SyntheticFlightParams.h"
#include "scenarios/SyntheticScenarios.h"

using namespace cansat;
using namespace cansat::mock;
using namespace cansat::sim;

static const float SYNTHETIC_P0 = 100000.0f;
static const float SYNTHETIC_HOVER_M = 64.0f;
static const float SYNTHETIC_NEAR_GROUND_M = 0.5f;
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
  const Event* first(EventType t) const {
    for (const Event& e : events) {
      if (e.type == t) return &e;
    }
    return nullptr;
  }
};

ValidatedFrame vf(uint32_t now, bool sw_open, float amag_g, float pressure_pa, bool imu_ok = true) {
  ValidatedFrame v;
  v.now_ms = now;
  v.baro_ok = true;
  v.imu_ok = imu_ok;
  v.power_ok = true;
  v.switches_ok = true;
  v.raw.baro.valid = true;
  v.raw.baro.pressure_pa = pressure_pa;
  v.raw.imu.valid = imu_ok;
  v.raw.imu.az_g = amag_g;
  v.raw.switches.valid = true;
  v.raw.switches.raw[0] = sw_open;  // SYNTHETIC wiring: open = HIGH
  v.raw.switches.raw[1] = sw_open;
  return v;
}

float pAt(float alt_m) { return pressureAtAltitude(SYNTHETIC_P0, alt_m); }

// Detector that has passed self-check with ground reference SYNTHETIC_P0.
uint32_t passSelfCheck(EventDetector& d) {
  uint32_t t = 0;
  for (int i = 0; i < 20; ++i, t += SYNTHETIC_DT) {
    d.update(vf(t, false, 1.0f, SYNTHETIC_P0), FlightState::PowerOnSelfCheck, false);
  }
  return t;
}

// Raw sensor frame with health fields set and a tiny SYNTHETIC jitter so that
// the stuck-output check sees realistic (non-identical) data.
SensorFrame jitterFrame(uint32_t now, bool sw_closed_level = false) {
  SensorFrame f;
  const float j = static_cast<float>(now % 7) * 0.001f;
  f.baro.valid = f.baro.comm_ok = f.baro.data_ready = true;
  f.baro.t_ms = now;
  f.baro.pressure_pa = SYNTHETIC_P0 + j;
  f.baro.temp_c = 20.0f;
  f.imu.valid = f.imu.comm_ok = f.imu.data_ready = true;
  f.imu.t_ms = now;
  f.imu.az_g = 1.0f + j;
  f.power.valid = f.power.comm_ok = f.power.data_ready = true;
  f.power.t_ms = now;
  f.power.bus_v = 3.8f;
  f.power.current_ma = 100.0f;
  f.switches.valid = true;
  f.switches.t_ms = now;
  f.switches.raw[0] = f.switches.raw[1] = sw_closed_level;
  return f;
}

void runFsw(const std::string& scenario, StuckSwitchPolicy pol, FswStats& stats, MemoryLogSink& log) {
  Scenario sc;
  CHECK(findSyntheticScenario(scenario, sc));
  FlightSoftwareHook hook(syntheticFlightParams(pol));
  SimRunner r;
  r.run(sc, log, &hook);
  stats = hook.stats();
}

FlightParams paramsWithPersistPolicy(PersistFailurePolicy pf) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  p.interlock.persist_failure_policy.set(pf);
  return p;
}

void toParachuteDeploy(FlightStateManager& fsm) {
  Event e;
  const EventType seq[] = {EventType::SelfCheckPass, EventType::AscentDetected,
                           EventType::ReleaseCandidate, EventType::ReleaseConfirmed};
  uint32_t t = 0;
  for (EventType s : seq) {
    e.type = s;
    e.t_ms = t += 10;
    e.detail = 1;
    fsm.onEvent(e);
  }
}

int drain(FlightStateManager& fsm) {
  int n = 0;
  ActuatorRequest r;
  while (fsm.popRequest(r)) ++n;
  return n;
}

}  // namespace

// ================= Item 1: landing confirmation =================
TEST_CASE(touchdown_never_confirmed_without_ground_reference) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  CollectSink out;
  EventDetector d(p, out);  // no self-check, no restored reference
  for (uint32_t t = 0; t < 60000; t += SYNTHETIC_DT) {
    d.update(vf(t, true, 1.0f, SYNTHETIC_P0), FlightState::Descent, true);
  }
  CHECK(out.count(EventType::TouchdownDetected) == 0);
  CHECK(out.count(EventType::SensorFault) == 1);
  CHECK(d.faultMask() & kFaultLandingUnconfirmable);
}

TEST_CASE(stable_hover_at_altitude_is_never_touchdown) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = passSelfCheck(d);
  for (const FlightState st : {FlightState::ParachuteDeploy, FlightState::PanelDeploy, FlightState::Descent}) {
    for (int i = 0; i < 1200; ++i, t += SYNTHETIC_DT) {  // 60 s each, perfectly stable, 1 g
      d.update(vf(t, true, 1.0f, pAt(SYNTHETIC_HOVER_M)), st, true);
    }
  }
  CHECK(out.count(EventType::TouchdownDetected) == 0);
}

TEST_CASE(touchdown_near_ground_only_after_full_window) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC 3000 ms, 5 m
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = passSelfCheck(d);
  const uint32_t start = t;
  for (; t < start + 2950; t += SYNTHETIC_DT) d.update(vf(t, true, 1.0f, pAt(SYNTHETIC_NEAR_GROUND_M)), FlightState::Descent, true);
  CHECK(out.count(EventType::TouchdownDetected) == 0);
  for (; t <= start + 3100; t += SYNTHETIC_DT) d.update(vf(t, true, 1.0f, pAt(SYNTHETIC_NEAR_GROUND_M)), FlightState::Descent, true);
  CHECK(out.count(EventType::TouchdownDetected) == 1);
  CHECK(out.first(EventType::TouchdownDetected)->detail == 0);
}

TEST_CASE(touchdown_window_restarts_on_invalid_imu) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = passSelfCheck(d);
  const uint32_t start = t;
  for (; t < start + 2000; t += SYNTHETIC_DT) d.update(vf(t, true, 1.0f, pAt(0.0f)), FlightState::Descent, true);
  d.update(vf(t, true, 1.0f, pAt(0.0f), false), FlightState::Descent, true);  // invalid IMU
  t += SYNTHETIC_DT;
  const uint32_t restart = t;
  for (; t < restart + 2950; t += SYNTHETIC_DT) d.update(vf(t, true, 1.0f, pAt(0.0f)), FlightState::Descent, true);
  CHECK(out.count(EventType::TouchdownDetected) == 0);
}

TEST_CASE(touchdown_with_mount_reading_closed_is_flagged) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = passSelfCheck(d);
  for (int i = 0; i < 100; ++i, t += SYNTHETIC_DT) d.update(vf(t, false, 1.0f, pAt(0.0f)), FlightState::Descent, true);
  const Event* e = out.first(EventType::TouchdownDetected);
  CHECK(e != nullptr && (e->detail & kTouchdownMountReadsClosed));
  CHECK(d.faultMask() & kFaultLandedMountClosed);
}

TEST_CASE(descent_confirmation_needs_sustained_baro_descent) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC 1 m/500 ms for 1000 ms
  CollectSink out;
  EventDetector d(p, out);
  uint32_t t = passSelfCheck(d);
  float alt = 80.0f;
  for (int i = 0; i < 1200; ++i, t += SYNTHETIC_DT) {  // stable at 80 m: no descent
    d.update(vf(t, true, 1.0f, pAt(alt)), FlightState::PanelDeploy, true);
  }
  CHECK(out.count(EventType::DescentConfirmed) == 0);
  const uint32_t start = t;
  for (; t < start + 3000; t += SYNTHETIC_DT) {  // 3 m/s descent
    alt -= 0.15f;
    d.update(vf(t, true, 1.0f, pAt(alt)), FlightState::PanelDeploy, true);
  }
  CHECK(out.count(EventType::DescentConfirmed) == 1);
}

TEST_CASE(scenario_mounted_drone_falling_never_lands_under_any_policy) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    FswStats st;
    MemoryLogSink log;
    runFsw("mounted_drone_falling", pol, st, log);
    CHECK(st.final_state != FlightState::Landed);
    for (const std::string& l : log.lines) CHECK(l.find("TouchdownDetected") == std::string::npos);
  }
}

TEST_CASE(scenario_nominal_lands_only_near_ground_and_after_descent) {
  FswStats st;
  MemoryLogSink log;
  runFsw("nominal", StuckSwitchPolicy::StrictSwitchVeto, st, log);
  CHECK(st.final_state == FlightState::Landed);
  bool seen = false;
  for (const std::string& l : log.lines) {
    if (l.find("TouchdownDetected") == std::string::npos) continue;
    seen = true;
    const size_t c1 = l.find(',');
    const size_t c2 = l.find(',', c1 + 1);
    const size_t c3 = l.find(',', c2 + 1);
    const size_t c4 = l.find(',', c3 + 1);
    const float truth_alt = std::stof(l.substr(c4 + 1));
    CHECK(truth_alt < 1.0f);
  }
  CHECK(seen);
}

// ================= Item 4: states, timeouts, abnormal paths =================
TEST_CASE(abnormal_landing_paths_are_explicit_and_keep_status) {
  CHECK(FlightStateManager::isPermitted(FlightState::ParachuteDeploy, FlightState::Landed));
  CHECK(FlightStateManager::isPermitted(FlightState::PanelDeploy, FlightState::Landed));
  CHECK(!FlightStateManager::isPermitted(FlightState::Ascent, FlightState::Landed));
  CHECK(!FlightStateManager::isPermitted(FlightState::ReleaseDetected, FlightState::Landed));
  CHECK(!FlightStateManager::isPermitted(FlightState::ParachuteDeploy, FlightState::Descent));
}

TEST_CASE(no_state_is_left_by_time_alone) {
  for (uint8_t code = 1; code <= kFlightStateCount; ++code) {
    MockPersistentStore store;
    RecoveryRecord rec;
    rec.magic = kRecoveryMagic;
    rec.version = kRecoveryVersion;
    rec.boot_count = 1;
    rec.last_state = code;
    rec.one_shot_flags = code >= 5 ? (kOneShotReleaseConfirmed | kOneShotChuteRequested) : 0;
    rec.ground_pressure_pa = SYNTHETIC_P0;
    rec.crc = recoveryCrc(rec);
    store.save(rec);
    const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
    RecoveryManager rm(store);
    CollectSink out;
    FlightStateManager fsm(p, rm, out);
    const RestoreResult rr = rm.restoreOnBoot();
    fsm.start(rr, 0);
    const FlightState before = fsm.state();
    for (uint32_t t = 0; t < 3600000; t += 1000) fsm.tick(t);  // one simulated hour, no events
    CHECK(fsm.state() == before);
    CHECK(out.count(EventType::StateChanged) == 0);
  }
}

// ================= Item 3: IMU health evidence =================
TEST_CASE(validator_rejects_comm_failure_and_not_ready) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  SensorValidator v(p);
  SensorFrame f = jitterFrame(0);
  f.imu.comm_ok = false;
  f.imu.valid = false;
  ValidatedFrame r = v.validate(f, 0);
  CHECK(!r.imu_ok && (r.imu_reject & kRejectComm) && (r.imu_reject & kRejectInvalidFlag));
  f = jitterFrame(50);
  f.imu.data_ready = false;
  r = v.validate(f, 50);
  CHECK(!r.imu_ok && r.imu_reject == kRejectNotFresh);
  f = jitterFrame(100);
  f.baro.data_ready = false;
  f.power.comm_ok = false;
  r = v.validate(f, 100);
  CHECK(r.imu_ok && r.baro_reject == kRejectNotFresh && (r.power_reject & kRejectComm));
}

TEST_CASE(validator_detects_stuck_imu_output_after_n_identical_samples) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);  // SYNTHETIC N = 5
  SensorValidator v(p);
  SensorFrame f = jitterFrame(0);
  for (uint32_t i = 0; i < 4; ++i) {
    f.imu.t_ms = f.baro.t_ms = f.power.t_ms = f.switches.t_ms = i * SYNTHETIC_DT;
    CHECK(v.validate(f, i * SYNTHETIC_DT).imu_ok);  // 1..4 identical: cannot tell yet
  }
  f.imu.t_ms = f.baro.t_ms = f.power.t_ms = f.switches.t_ms = 200;
  ValidatedFrame r = v.validate(f, 200);
  CHECK(!r.imu_ok && r.imu_reject == kRejectStuck);
  SensorFrame g = jitterFrame(250);
  g.imu.az_g += 0.01f;
  CHECK(v.validate(g, 250).imu_ok);  // output moves again: recovered
}

TEST_CASE(validator_stuck_check_disabled_without_param) {
  FlightParams p;  // nothing set
  SensorValidator v(p);
  SensorFrame f = jitterFrame(0);
  for (uint32_t i = 0; i < 50; ++i) {
    f.imu.t_ms = f.baro.t_ms = f.power.t_ms = f.switches.t_ms = i * SYNTHETIC_DT;
    CHECK((v.validate(f, i * SYNTHETIC_DT).imu_reject & kRejectStuck) == 0);
  }
}

TEST_CASE(mock_imu_new_fault_kinds) {
  VirtualClock c;
  class Truth : public ITruthSource {
   public:
    float az = 1.0f;
    TruthState truthAt(uint32_t t) const override {
      TruthState s;
      s.truth_ms = t;
      s.accel_g[2] = az;
      s.gyro_dps[0] = 0.3f;
      return s;
    }
  } truth;
  FaultInjector fi;
  fi.add({FaultTarget::Imu, FaultKind::CommFailure, 100, 200, 0});
  fi.add({FaultTarget::Imu, FaultKind::NotReady, 200, 300, 0});
  fi.add({FaultTarget::Imu, FaultKind::StuckOutput, 300, 400, 0});
  MockImu imu(c, truth, fi, SensorNoise(), 1);
  imu.begin();
  ImuSample s = imu.read();
  CHECK(s.valid && s.comm_ok && s.data_ready);
  truth.az = 0.05f;
  c.advanceTo(150);
  s = imu.read();
  CHECK(!s.valid && !s.comm_ok);
  c.advanceTo(250);
  s = imu.read();
  CHECK(s.valid && s.comm_ok && !s.data_ready && s.t_ms == 250 && s.az_g == 1.0f);
  c.advanceTo(350);
  s = imu.read();
  CHECK(s.valid && s.data_ready && s.t_ms == 350 && s.az_g == 1.0f);  // frozen output
  c.advanceTo(400);
  s = imu.read();
  CHECK(s.az_g == 0.05f);
}

TEST_CASE(self_test_failed_blocks_self_check_and_not_run_is_flagged) {
  const FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  {
    MockPersistentStore store;
    FlightSoftware fs(p, store);
    BootReport br;
    br.baro_ok = br.imu_ok = br.power_ok = true;
    br.imu_self_test = SelfTestResult::Failed;
    fs.boot(br, 0);
    for (uint32_t t = 0; t < 5000; t += SYNTHETIC_DT) fs.tick(jitterFrame(t), t);
    CHECK(fs.state() == FlightState::PowerOnSelfCheck);
    CHECK(fs.faultMask() & kFaultImuSelfTestFailed);
  }
  {
    MockPersistentStore store;
    FlightSoftware fs(p, store);
    BootReport br;
    br.baro_ok = br.imu_ok = br.power_ok = true;  // self-test NotRun (default)
    fs.boot(br, 0);
    for (uint32_t t = 0; t < 5000; t += SYNTHETIC_DT) fs.tick(jitterFrame(t), t);
    CHECK(fs.state() == FlightState::ReadyOnDrone);  // provisional: NotRun does not block
    CHECK(fs.faultMask() & kFaultImuSelfTestNotRun);
  }
  {
    MockPersistentStore store;
    FlightSoftware fs(p, store);
    BootReport br;
    br.baro_ok = br.imu_ok = br.power_ok = true;
    br.imu_self_test = SelfTestResult::Passed;
    fs.boot(br, 0);
    CHECK((fs.faultMask() & (kFaultImuSelfTestNotRun | kFaultImuSelfTestFailed)) == 0);
  }
}

TEST_CASE(scenario_imu_stuck_in_release_is_caught_and_baro_confirms) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    FswStats st;
    MemoryLogSink log;
    runFsw("imu_stuck_in_release", pol, st, log);
    CHECK(st.final_state == FlightState::Landed);
    CHECK(st.requests == 1);
    CHECK(st.last_release_basis == kBasisSwitchAndBaro);  // frozen IMU never counted as free fall
  }
}

TEST_CASE(scenario_imu_comm_failure_in_descent_still_lands) {
  FswStats st;
  MemoryLogSink log;
  runFsw("imu_comm_failure_descent", StuckSwitchPolicy::StrictSwitchVeto, st, log);
  CHECK(st.final_state == FlightState::Landed);
  bool comm_rows = false;
  for (const std::string& l : log.lines) comm_rows = comm_rows || l.find("imu.comm_failure") != std::string::npos;
  CHECK(comm_rows);
}

// ================= Item 5: persistence failure =================
TEST_CASE(persist_failure_request_anyway_can_duplicate_after_reset) {
  // Demonstrates the documented consequence of RequestAnyway (OD-067).
  const FlightParams p = paramsWithPersistPolicy(PersistFailurePolicy::RequestAnyway);
  MockPersistentStore store;
  int total = 0;
  {
    RecoveryManager rm(store);
    CollectSink out;
    FlightStateManager fsm(p, rm, out);
    fsm.start(rm.restoreOnBoot(), 0);
    toParachuteDeploy(fsm);  // persisted while the store still works
    store.fail_writes = true;
    for (uint32_t t = 0; t < 1000; t += SYNTHETIC_DT) {
      fsm.tick(t);
      total += drain(fsm);
    }
    CHECK(total == 1);
    CHECK(fsm.faultMask() & kFaultPersistWrite);
  }
  // --- reset: the record still says "release confirmed, chute NOT requested" ---
  {
    RecoveryManager rm(store);
    CollectSink out;
    FlightStateManager fsm(p, rm, out);
    fsm.start(rm.restoreOnBoot(), 0);
    CHECK(out.count(EventType::RequestSuppressed) == 0);
    for (uint32_t t = 0; t < 1000; t += SYNTHETIC_DT) {
      fsm.tick(t);
      total += drain(fsm);
    }
  }
  CHECK(total == 2);  // SECOND request after the reset: the hazard RequestAnyway accepts
}

TEST_CASE(persist_failure_withhold_never_requests_while_storage_fails) {
  const FlightParams p = paramsWithPersistPolicy(PersistFailurePolicy::WithholdUntilPersisted);
  MockPersistentStore store;
  RecoveryManager rm(store);
  CollectSink out;
  FlightStateManager fsm(p, rm, out);
  fsm.start(rm.restoreOnBoot(), 0);
  toParachuteDeploy(fsm);
  store.fail_writes = true;
  int total = 0;
  for (uint32_t t = 0; t < 30000; t += SYNTHETIC_DT) {
    fsm.tick(t);
    total += drain(fsm);
  }
  CHECK(total == 0);  // the hazard WithholdUntilPersisted accepts: no parachute request at all
  CHECK(out.count(EventType::RequestWithheld) == 1);
  CHECK(fsm.faultMask() & kFaultRequestWithheld);
  CHECK(fsm.chuteStatus() == ChuteStatus::NotRequested);
  store.fail_writes = false;  // storage recovers
  for (uint32_t t = 30000; t < 31000; t += SYNTHETIC_DT) {
    fsm.tick(t);
    total += drain(fsm);
  }
  CHECK(total == 1);
  CHECK(store.record().one_shot_flags & kOneShotChuteRequested);
  // Reset afterwards: flag was persisted, so no second request.
  RecoveryManager rm2(store);
  CollectSink out2;
  FlightStateManager fsm2(p, rm2, out2);
  fsm2.start(rm2.restoreOnBoot(), 0);
  for (uint32_t t = 0; t < 2000; t += SYNTHETIC_DT) {
    fsm2.tick(t);
    total += drain(fsm2);
  }
  CHECK(total == 1);
}

TEST_CASE(persist_failure_policy_unset_means_params_incomplete_and_no_request) {
  FlightParams p = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  p.interlock.persist_failure_policy.clear();
  CHECK(!p.isComplete());
  MockPersistentStore store;
  RecoveryManager rm(store);
  CollectSink out;
  FlightStateManager fsm(p, rm, out);
  fsm.start(rm.restoreOnBoot(), 0);
  toParachuteDeploy(fsm);
  for (uint32_t t = 0; t < 5000; t += SYNTHETIC_DT) fsm.tick(t);
  CHECK(drain(fsm) == 0);
}

int main() { return th::runAll(); }
