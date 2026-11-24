// test_recovery_faults.cpp — persisted-record faults (OD-069). [SIMULATED]
//
// Two kinds of test, kept apart on purpose:
//
//   INVARIANT_*  Safety properties that must hold whichever recovery approach
//                (R-A … R-F) the team eventually selects. A failure here is a bug.
//
//   HAZARD_*     Characterisation of CURRENT behaviour (R-A: restart at
//                POWER_ON_SELF_CHECK). They pin known hazards so that any
//                change is visible. They are NOT approved behaviour; when the
//                team selects an OD-069 approach, update them deliberately.
//
// No recovery approach is selected or implemented here. The recovery manager,
// state machine and release detector are unchanged.
#include <string>
#include <vector>

#include "FlightStateManager.h"
#include "FswHook.h"
#include "MemoryLogSink.h"
#include "MockPersistentStore.h"
#include "RecoveryManager.h"
#include "SimRunner.h"
#include "TestHarness.h"
#include "scenarios/SyntheticFlightParams.h"
#include "scenarios/SyntheticScenarios.h"

using namespace cansat;
using namespace cansat::sim;
using cansat::mock::MemoryLogSink;
using cansat::mock::MockPersistentStore;

namespace {

struct Sink : IEventSink {
  std::vector<Event> events;
  void onEvent(const Event& e) override { events.push_back(e); }
};

struct Run {
  FswStats stats;
  MemoryLogSink log;
};

void runFsw(const std::string& name, StuckSwitchPolicy pol, Run& out) {
  Scenario sc;
  CHECK(findSyntheticScenario(name, sc));
  FlightSoftwareHook hook(syntheticFlightParams(pol));
  hook.setStoreFaults(sc.store_faults);
  SimRunner r;
  r.run(sc, out.log, &hook);
  out.stats = hook.stats();
}

std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> o(1);
  for (char ch : s) {
    if (ch == sep) o.emplace_back();
    else o.back() += ch;
  }
  return o;
}

// Truth "mounted" column (index 6) of every row that logged a request.
std::vector<int> truthMountedAtRequests(const MemoryLogSink& log) {
  std::vector<int> v;
  for (const std::string& l : log.lines) {
    if (l.empty() || l[0] == '#' || l.find("REQUEST:") == std::string::npos) continue;
    const std::vector<std::string> c = split(l, ',');
    if (c.size() > 6) v.push_back(c[6] == "1" ? 1 : 0);
  }
  return v;
}

bool contains(const std::vector<FlightState>& v, FlightState s, int times) {
  int n = 0;
  for (FlightState x : v) n += (x == s);
  return n >= times;
}

void toParachuteDeploy(FlightStateManager& fsm) {
  Event e;
  const EventType seq[] = {EventType::SelfCheckPass, EventType::AscentDetected, EventType::ReleaseCandidate,
                           EventType::ReleaseConfirmed};
  uint32_t t = 0;
  for (EventType s : seq) {
    e.type = s;
    e.t_ms = t += 10;
    e.detail = kBasisSwitchAndFreefall;
    fsm.onEvent(e);
  }
}

}  // namespace

// ============================ INVARIANTS ============================

TEST_CASE(INVARIANT_scenario_sets_are_separate_and_named) {
  CHECK(allSyntheticScenarios().size() == 13);  // Step 2/3 set unchanged
  const std::vector<Scenario> rf = recoveryFaultScenarios();
  CHECK(rf.size() == 4);
  for (const Scenario& sc : rf) {
    CHECK(!sc.store_faults.empty());
    CHECK(sc.description.find("HAZARD") != std::string::npos);
  }
  CHECK(everySyntheticScenario().size() == 17);
}

TEST_CASE(INVARIANT_corrupt_record_never_resumes_or_restores_one_shots) {
  for (uint8_t code = 1; code <= 8; ++code) {
    MockPersistentStore store;
    {
      RecoveryManager rec(store);
      rec.restoreOnBoot();
      rec.setGroundPressure(100000.0f);
      rec.persist(static_cast<FlightState>(code), kOneShotReleaseConfirmed | kOneShotChuteRequested);
    }
    store.corrupt();
    RecoveryManager rec(store);
    const RestoreResult rr = rec.restoreOnBoot();
    CHECK(rr.corrupt);
    CHECK(!rr.resumed);
    CHECK(rr.state == FlightState::PowerOnSelfCheck);
    CHECK(rr.one_shot_flags == 0);
    CHECK(!rr.has_ground);
  }
}

TEST_CASE(INVARIANT_structurally_invalid_records_are_treated_as_corrupt) {
  // Valid CRC but impossible content must not be trusted.
  RecoveryRecord bad[3];
  for (RecoveryRecord& r : bad) {
    r.magic = kRecoveryMagic;
    r.version = kRecoveryVersion;
    r.boot_count = 1;
    r.last_state = static_cast<uint8_t>(FlightState::ParachuteDeploy);
  }
  bad[0].magic ^= 1u;
  bad[1].version = static_cast<uint16_t>(kRecoveryVersion + 1);
  bad[2].last_state = 99;
  for (RecoveryRecord& r : bad) {
    r.crc = recoveryCrc(r);
    MockPersistentStore store;
    store.save(r);
    RecoveryManager rec(store);
    const RestoreResult rr = rec.restoreOnBoot();
    CHECK(rr.corrupt && !rr.resumed && rr.one_shot_flags == 0);
  }
}

TEST_CASE(INVARIANT_corrupt_or_absent_record_alone_never_causes_a_request) {
  for (int kind = 0; kind < 2; ++kind) {
    const FlightParams fp = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
    MockPersistentStore store;
    {
      RecoveryManager rec(store);
      Sink s;
      FlightStateManager fsm(fp, rec, s);
      fsm.start(rec.restoreOnBoot(), 0);
      toParachuteDeploy(fsm);  // release confirmed and persisted, request not yet emitted
    }
    if (kind == 0) store.corrupt();
    else store.erase();
    RecoveryManager rec(store);
    Sink s;
    FlightStateManager fsm(fp, rec, s);
    const RestoreResult rr = rec.restoreOnBoot();
    fsm.start(rr, 0);
    for (uint32_t t = 0; t < 60000; t += 50) fsm.tick(t);
    CHECK(fsm.requestsEmitted() == 0);
    CHECK(fsm.oneShotFlags() == 0);
    CHECK(((fsm.faultMask() & kFaultRecoveryRecordCorrupt) != 0) == (kind == 0));
  }
}

TEST_CASE(INVARIANT_recovery_fault_scenarios_never_request_twice_or_while_mounted) {
  for (const Scenario& sc : recoveryFaultScenarios()) {
    for (StuckSwitchPolicy pol : candidatePolicies()) {
      Run run;
      runFsw(sc.name, pol, run);
      CHECK(run.stats.requests <= 1);
      CHECK(run.stats.store_faults_applied == sc.store_faults.size());
      for (int mounted : truthMountedAtRequests(run.log)) CHECK(mounted == 0);
      for (const std::string& l : run.log.lines) {
        if (l.find("REQUEST:") != std::string::npos) CHECK(l.find("NOT_EXECUTED") != std::string::npos);
      }
    }
  }
}

TEST_CASE(INVARIANT_corrupt_record_fault_is_visible_for_the_rest_of_the_boot) {
  const char* names[] = {"corrupt_record_after_release", "corrupt_record_after_request",
                         "corrupt_record_mounted_ascent"};
  for (const char* n : names) {
    for (StuckSwitchPolicy pol : candidatePolicies()) {
      Run run;
      runFsw(n, pol, run);
      CHECK(run.stats.corrupt_restarts == 1);
      CHECK(run.stats.final_faults & kFaultRecoveryRecordCorrupt);
    }
  }
}

TEST_CASE(INVARIANT_recovery_fault_runs_are_deterministic) {
  Run a, b;
  runFsw("corrupt_record_after_release", StuckSwitchPolicy::Vote2of3, a);
  runFsw("corrupt_record_after_release", StuckSwitchPolicy::Vote2of3, b);
  CHECK(a.log.lines == b.log.lines);
}

// ===================== HAZARDS (current behaviour, R-A) =====================

// Reset after real separation, after ReleaseConfirmed, before the request,
// with a corrupt record: restart at self-check, which requires the mount to
// read closed. After separation it reads open, so self-check never passes and
// the parachute is never requested.
TEST_CASE(HAZARD_corrupt_record_after_release_means_no_parachute_request) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    Run run;
    runFsw("corrupt_record_after_release", pol, run);
    CHECK(run.stats.release_confirmed == 1);  // before the reset
    CHECK(run.stats.requests == 0);
    CHECK(run.stats.final_state == FlightState::PowerOnSelfCheck);
    CHECK(run.stats.final_chute == ChuteStatus::NotRequested);
  }
}

// Same, but nothing marks the stuck self-check: no SelfCheck fault is raised
// for "mount reads open at self-check". Only the corrupt-record bit is visible.
TEST_CASE(HAZARD_stuck_self_check_after_corrupt_restart_raises_no_specific_fault) {
  Run run;
  runFsw("corrupt_record_after_release", StuckSwitchPolicy::StrictSwitchVeto, run);
  CHECK((run.stats.final_faults & kFaultSelfCheck) == 0);
  CHECK(run.stats.final_faults & kFaultRecoveryRecordCorrupt);
}

// An ERASED (absent) record mid-flight is indistinguishable from a first boot:
// same no-parachute outcome, and not even the corrupt-record fault is raised.
TEST_CASE(HAZARD_erased_record_after_release_looks_like_first_boot) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    Run run;
    runFsw("record_erased_after_release", pol, run);
    CHECK(run.stats.requests == 0);
    CHECK(run.stats.final_state == FlightState::PowerOnSelfCheck);
    CHECK(run.stats.corrupt_restarts == 0);
    CHECK((run.stats.final_faults & kFaultRecoveryRecordCorrupt) == 0);
  }
}

// Corrupt record AFTER the request: the request happened before the reset,
// but the new boot has lost all one-shot knowledge (chute status reads
// NOT_REQUESTED). Any future approach that resumes flight from sensor data
// must handle "was it already requested?" explicitly.
TEST_CASE(HAZARD_corrupt_record_after_request_forgets_the_request) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    Run run;
    runFsw("corrupt_record_after_request", pol, run);
    CHECK(run.stats.requests == 1);  // emitted in boot 1
    CHECK(run.stats.final_state == FlightState::PowerOnSelfCheck);
    CHECK(run.stats.final_chute == ChuteStatus::NotRequested);
  }
}

// Corrupt record while still mounted in ascent: self-check passes AGAIN at
// altitude and captures that altitude as "ground". With the SYNTHETIC profile
// the flight then proceeds, but touchdown can never be confirmed because the
// real ground is far below the captured reference.
TEST_CASE(HAZARD_corrupt_record_while_mounted_recaptures_ground_at_altitude) {
  for (StuckSwitchPolicy pol : candidatePolicies()) {
    Run run;
    runFsw("corrupt_record_mounted_ascent", pol, run);
    CHECK(contains(run.stats.states_entered, FlightState::PowerOnSelfCheck, 2));
    CHECK(contains(run.stats.states_entered, FlightState::ReadyOnDrone, 2));
    CHECK(run.stats.final_state != FlightState::Landed);
  }
}

// A failed write followed by a reset resumes the LAST SUCCESSFULLY written
// state, not the true one: here ASCENT, with the release one-shot lost.
TEST_CASE(HAZARD_write_failure_then_reset_resumes_an_older_state) {
  const FlightParams fp = syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto);
  MockPersistentStore store;
  {
    RecoveryManager rec(store);
    Sink s;
    FlightStateManager fsm(fp, rec, s);
    fsm.start(rec.restoreOnBoot(), 0);
    Event e;
    e.type = EventType::SelfCheckPass;
    e.t_ms = 10;
    fsm.onEvent(e);
    e.type = EventType::AscentDetected;
    e.t_ms = 20;
    fsm.onEvent(e);
    CHECK(fsm.state() == FlightState::Ascent);
    store.fail_writes = true;
    e.type = EventType::ReleaseCandidate;
    e.t_ms = 30;
    fsm.onEvent(e);
    e.type = EventType::ReleaseConfirmed;
    e.t_ms = 40;
    e.detail = kBasisSwitchAndFreefall;
    fsm.onEvent(e);
    CHECK(fsm.state() == FlightState::ParachuteDeploy);
    CHECK(fsm.faultMask() & kFaultPersistWrite);
  }
  store.fail_writes = false;
  RecoveryManager rec(store);
  const RestoreResult rr = rec.restoreOnBoot();
  CHECK(rr.resumed);
  CHECK(rr.state == FlightState::Ascent);
  CHECK((rr.one_shot_flags & kOneShotReleaseConfirmed) == 0);
}

int main() { return th::runAll(); }
