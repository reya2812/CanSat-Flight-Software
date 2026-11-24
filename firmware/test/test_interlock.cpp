// test_interlock.cpp — DeploymentInterlock + ActuatorManager (OD-070), mocks only.
//
// [SIMULATED] No hardware. The only actuator driver is MockActuatorDriver
// (isPhysical() == false) or, in one test, a test-local fake that CLAIMS to be
// physical so the refusal path can be checked; that fake never touches hardware.
// The connection assessment is scripted: these tests do not implement or
// assume any release architecture (A1–A5) or any switch behaviour.
//
// SYNTHETIC values below exist only for these tests.
#include <vector>

#include "ActuatorManager.h"
#include "DeploymentInterlock.h"
#include "FlightStateManager.h"
#include "MockActuators.h"
#include "MockPersistentStore.h"
#include "RecoveryManager.h"
#include "TestHarness.h"
#include "scenarios/SyntheticFlightParams.h"

using namespace cansat;
using namespace cansat::sim;
using cansat::mock::MockActuatorDriver;
using cansat::mock::MockArmingSource;
using cansat::mock::MockPersistentStore;
using cansat::mock::ScriptedConnectionSource;

namespace {

const uint32_t SYNTHETIC_CONNECTION_MAX_AGE_MS = 100;
const uint32_t SYNTHETIC_RELEASE_AT_MS = 1000;
const uint32_t SYNTHETIC_AFTER_SEPARATION_MS = 2000;  // > release + SYNTHETIC min separation (300)
const uint16_t SYNTHETIC_BOOT = 1;

struct Sink : IEventSink {
  std::vector<Event> events;
  void onEvent(const Event& e) override { events.push_back(e); }
};

// Claims to be physical. Used only to prove the manager refuses it.
struct FakePhysicalDriver : IActuatorDriver {
  int calls = 0;
  void apply(ActuatorRequest) override { ++calls; }
  bool isPhysical() const override { return true; }
};

FlightParams flightParams() { return syntheticFlightParams(StuckSwitchPolicy::StrictSwitchVeto); }

DeploymentInterlockParams ilParams() {
  DeploymentInterlockParams p;
  p.connection_max_age_ms.set(SYNTHETIC_CONNECTION_MAX_AGE_MS);
  return p;
}

FlightStatusView readyStatus() {
  FlightStatusView fs;
  fs.state = FlightState::ParachuteDeploy;
  fs.one_shot_flags = kOneShotReleaseConfirmed | kOneShotChuteRequested;
  fs.release_timer_start_ms = SYNTHETIC_RELEASE_AT_MS;
  return fs;
}

ConnectionAssessmentSample conn(ConnectionAssessment v, uint32_t t = 0) {
  ConnectionAssessmentSample s;
  s.value = v;
  s.t_ms = t;
  return s;
}

ArmingSample arm(ArmState s) {
  ArmingSample a;
  a.state = s;
  return a;
}

// A fully permissive rig: every gate passes unless a test changes something.
struct Rig {
  FlightParams fp = flightParams();
  DeploymentInterlockParams ip = ilParams();
  ScriptedConnectionSource connection;
  MockArmingSource arming;
  MockActuatorDriver driver;
  Sink sink;
  ActuatorManager mgr;
  explicit Rig(uint16_t boot = SYNTHETIC_BOOT)
      : mgr(fp, ip, connection, arming, driver, sink, boot) {
    connection.current = conn(ConnectionAssessment::Separated);
    arming.current = arm(ArmState::Armed);
  }
};

InterlockInputs permissiveInputs() {
  InterlockInputs in;
  in.request = ActuatorRequest::ReleaseParachute;
  in.now_ms = SYNTHETIC_AFTER_SEPARATION_MS;
  const FlightStatusView fs = readyStatus();
  in.state = fs.state;
  in.one_shot_flags = fs.one_shot_flags;
  in.release_timer_start_ms = fs.release_timer_start_ms;
  in.arming = arm(ArmState::Armed);
  in.connection = conn(ConnectionAssessment::Separated, SYNTHETIC_AFTER_SEPARATION_MS);
  return in;
}

ActuatorDecision decisionOf(const Event& e) { return static_cast<ActuatorDecision>((e.detail >> 16) & 0xFFu); }
int phaseOf(const Event& e) { return (e.detail >> 31) ? 1 : 0; }

}  // namespace

// ======================= Configuration / defaults =======================

TEST_CASE(unset_interlock_params_block_everything) {
  DeploymentInterlockParams unset;
  DeploymentInterlock il(flightParams(), unset);
  CHECK(!il.configured());
  const InterlockResult r = il.evaluate(permissiveInputs());
  CHECK(!r.permitted);
  CHECK(r.decision == ActuatorDecision::BlockedParamsIncomplete);
  CHECK(r.reasons & kIlParamsIncomplete);
}

TEST_CASE(unset_flight_params_block_everything) {
  FlightParams unset;
  DeploymentInterlock il(unset, ilParams());
  CHECK(!il.configured());
  CHECK(!il.evaluate(permissiveInputs()).permitted);
}

TEST_CASE(default_sources_and_default_inputs_block) {
  DeploymentInterlock il(flightParams(), ilParams());
  InterlockInputs in = permissiveInputs();
  in.arming = ArmingSample();                   // Unknown
  in.connection = ConnectionAssessmentSample();  // Unavailable
  const InterlockResult r = il.evaluate(in);
  CHECK(!r.permitted);
  CHECK(r.reasons & kIlArmUnknown);
  CHECK(r.reasons & kIlConnUnavailable);
  CHECK(!il.evaluate(InterlockInputs()).permitted);  // all-default snapshot
}

TEST_CASE(all_gates_pass_is_authorized_and_executes_only_the_mock) {
  Rig rig;
  const ActuatorDecision d = rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(),
                                            SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(d == ActuatorDecision::ExecutedSimulated);
  CHECK(rig.driver.applied.size() == 1);
  CHECK(!rig.driver.isPhysical());
  CHECK(rig.mgr.executedCount() == 1);
  // The connection and arming sources are read fresh in BOTH phases.
  CHECK(rig.connection.calls == 2);
  CHECK(rig.arming.calls == 2);
}

// ======================= Individual gates =======================

TEST_CASE(every_connection_value_except_separated_blocks) {
  const ConnectionAssessment vals[] = {ConnectionAssessment::Unavailable, ConnectionAssessment::Invalid,
                                       ConnectionAssessment::Indeterminate, ConnectionAssessment::Connected};
  const uint32_t bits[] = {kIlConnUnavailable, kIlConnInvalid, kIlConnIndeterminate, kIlConnConnected};
  const ActuatorDecision ds[] = {ActuatorDecision::BlockedConnectionUnavailable,
                                 ActuatorDecision::BlockedConnectionInvalid,
                                 ActuatorDecision::BlockedConnectionIndeterminate,
                                 ActuatorDecision::BlockedInterlockMounted};
  for (int i = 0; i < 4; ++i) {
    Rig rig;
    rig.connection.current = conn(vals[i]);
    const ActuatorDecision d = rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(),
                                              SYNTHETIC_AFTER_SEPARATION_MS);
    CHECK(d == ds[i]);
    CHECK(rig.mgr.lastResult().reasons & bits[i]);
    CHECK(rig.driver.applied.empty());
  }
}

TEST_CASE(stale_and_future_dated_assessments_block) {
  DeploymentInterlock il(flightParams(), ilParams());
  InterlockInputs in = permissiveInputs();
  in.connection.t_ms = in.now_ms - SYNTHETIC_CONNECTION_MAX_AGE_MS;  // exactly at the limit: accepted
  CHECK(il.evaluate(in).permitted);
  in.connection.t_ms = in.now_ms - SYNTHETIC_CONNECTION_MAX_AGE_MS - 1;  // one ms too old
  InterlockResult r = il.evaluate(in);
  CHECK(!r.permitted && (r.reasons & kIlConnStale));
  CHECK(r.decision == ActuatorDecision::BlockedConnectionStale);
  in.connection.t_ms = in.now_ms + 1;  // claims to come from the future
  r = il.evaluate(in);
  CHECK(!r.permitted && (r.reasons & kIlConnFutureTimestamp));
}

TEST_CASE(stale_connected_assessment_reports_both_reasons) {
  DeploymentInterlock il(flightParams(), ilParams());
  InterlockInputs in = permissiveInputs();
  in.connection = conn(ConnectionAssessment::Connected, 0);
  const InterlockResult r = il.evaluate(in);
  CHECK((r.reasons & kIlConnConnected) && (r.reasons & kIlConnStale));
}

TEST_CASE(disarmed_or_unknown_arming_blocks) {
  for (ArmState s : {ArmState::Disarmed, ArmState::Unknown}) {
    Rig rig;
    rig.arming.current = arm(s);
    CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
          ActuatorDecision::BlockedNotArmed);
    CHECK(rig.mgr.lastResult().reasons & (s == ArmState::Disarmed ? kIlNotArmed : kIlArmUnknown));
    CHECK(rig.driver.applied.empty());
  }
}

TEST_CASE(any_state_other_than_parachute_deploy_blocks) {
  for (uint8_t code = 1; code <= 8; ++code) {
    const FlightState st = static_cast<FlightState>(code);
    if (st == FlightState::ParachuteDeploy) continue;
    Rig rig;
    FlightStatusView fs = readyStatus();
    fs.state = st;
    CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS) ==
          ActuatorDecision::BlockedWrongState);
    CHECK(rig.driver.applied.empty());
  }
}

TEST_CASE(release_not_confirmed_blocks_even_in_parachute_deploy) {
  Rig rig;
  FlightStatusView fs = readyStatus();
  fs.one_shot_flags = kOneShotChuteRequested;  // inconsistent flags: no confirmed release
  CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::BlockedReleaseNotConfirmed);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(separation_delay_is_rechecked_independently) {
  Rig rig;
  uint32_t sep = 0;
  rig.fp.interlock.min_separation_ms.get(sep);
  const uint32_t early = SYNTHETIC_RELEASE_AT_MS + sep - 1;
  CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(), early) ==
        ActuatorDecision::BlockedSeparationDelay);
  // Clock earlier than the recorded start (time inconsistency) also blocks.
  CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(), SYNTHETIC_RELEASE_AT_MS - 1) ==
        ActuatorDecision::BlockedSeparationDelay);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(requests_without_an_interlock_rule_are_refused) {
  for (ActuatorRequest r : {ActuatorRequest::DeployPanels, ActuatorRequest::BuzzerOn, ActuatorRequest::BuzzerOff}) {
    Rig rig;
    CHECK(rig.mgr.handle(r, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
          ActuatorDecision::BlockedUnsupportedRequest);
    CHECK(rig.driver.applied.empty());
  }
}

TEST_CASE(multiple_failing_gates_are_all_reported) {
  DeploymentInterlock il(flightParams(), ilParams());
  InterlockInputs in = permissiveInputs();
  in.state = FlightState::Ascent;
  in.one_shot_flags = 0;
  in.arming = arm(ArmState::Disarmed);
  in.connection = conn(ConnectionAssessment::Connected, in.now_ms);
  const InterlockResult r = il.evaluate(in);
  CHECK(!r.permitted);
  CHECK(r.decision == ActuatorDecision::BlockedWrongState);  // first gate in the fixed order
  const uint32_t expected = kIlWrongState | kIlReleaseNotConfirmed | kIlNotArmed | kIlConnConnected;
  CHECK((r.reasons & expected) == expected);
}

TEST_CASE(a_driver_claiming_to_be_physical_is_refused_and_never_called) {
  FlightParams fp = flightParams();
  DeploymentInterlockParams ip = ilParams();
  ScriptedConnectionSource c;
  c.current = conn(ConnectionAssessment::Separated);
  MockArmingSource a;
  a.current = arm(ArmState::Armed);
  FakePhysicalDriver phys;
  Sink sink;
  ActuatorManager mgr(fp, ip, c, a, phys, sink, SYNTHETIC_BOOT);
  CHECK(mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::BlockedBuildDisabled);
  CHECK(mgr.lastResult().reasons & kIlPhysicalDriverRefused);
  CHECK(phys.calls == 0);
  CHECK(mgr.executedCount() == 0);
}

TEST_CASE(decisions_are_reported_as_events_for_both_phases) {
  Rig rig;
  rig.mgr.handle(ActuatorRequest::ReleaseParachute, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(rig.sink.events.size() == 2);
  CHECK(rig.sink.events[0].type == EventType::ActuatorDecided);
  CHECK(phaseOf(rig.sink.events[0]) == 0);
  CHECK(decisionOf(rig.sink.events[0]) == ActuatorDecision::AuthorizedPendingExecution);
  CHECK(phaseOf(rig.sink.events[1]) == 1);
  CHECK(decisionOf(rig.sink.events[1]) == ActuatorDecision::ExecutedSimulated);
  CHECK(((rig.sink.events[1].detail >> 24) & 0x7Fu) == static_cast<uint32_t>(ActuatorRequest::ReleaseParachute));
}

// ============ Evidence changing between authorization and execution ============

TEST_CASE(evidence_changing_after_authorization_blocks_execution) {
  const ConnectionAssessment later[] = {ConnectionAssessment::Connected, ConnectionAssessment::Invalid,
                                        ConnectionAssessment::Unavailable, ConnectionAssessment::Indeterminate};
  for (ConnectionAssessment v : later) {
    Rig rig;
    rig.connection.next = {conn(ConnectionAssessment::Separated), conn(v)};
    const FlightStatusView fs = readyStatus();
    const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
    CHECK(a.valid);
    const ActuatorDecision d = rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS + 1);
    CHECK(d != ActuatorDecision::ExecutedSimulated);
    CHECK(rig.driver.applied.empty());
    // The token is spent even though execution was blocked.
    CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS + 2) == ActuatorDecision::BlockedNotAuthorized);
  }
}

TEST_CASE(evidence_going_stale_between_phases_blocks_execution) {
  Rig rig;
  rig.connection.fixed_time = true;  // the source stops refreshing its assessment
  rig.connection.current = conn(ConnectionAssessment::Separated, SYNTHETIC_AFTER_SEPARATION_MS);
  const FlightStatusView fs = readyStatus();
  const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(a.valid);
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS + SYNTHETIC_CONNECTION_MAX_AGE_MS + 1) ==
        ActuatorDecision::BlockedConnectionStale);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(disarming_between_phases_blocks_execution) {
  Rig rig;
  rig.arming.next = {arm(ArmState::Armed), arm(ArmState::Disarmed)};
  const FlightStatusView fs = readyStatus();
  const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(a.valid);
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedNotArmed);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(flight_state_changing_between_phases_blocks_execution) {
  Rig rig;
  FlightStatusView fs = readyStatus();
  const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(a.valid);
  fs.state = FlightState::PanelDeploy;
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedWrongState);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(evidence_improving_after_a_blocked_authorization_does_not_execute) {
  Rig rig;
  rig.connection.next = {conn(ConnectionAssessment::Connected), conn(ConnectionAssessment::Separated)};
  const FlightStatusView fs = readyStatus();
  const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(!a.valid);
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedNotAuthorized);
  CHECK(rig.driver.applied.empty());
}

// ================= Duplicates around the authorization/execution boundary =================

TEST_CASE(duplicate_execute_of_one_token_actuates_once) {
  Rig rig;
  const FlightStatusView fs = readyStatus();
  const Authorization a = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::ExecutedSimulated);
  CHECK(rig.mgr.execute(a, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedAlreadyDone);
  CHECK(rig.driver.applied.size() == 1);
}

TEST_CASE(second_request_after_execution_is_refused_at_authorization) {
  Rig rig;
  const FlightStatusView fs = readyStatus();
  CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::ExecutedSimulated);
  CHECK(rig.mgr.handle(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS + 1) ==
        ActuatorDecision::BlockedAlreadyDone);
  CHECK(rig.driver.applied.size() == 1);
}

TEST_CASE(older_token_is_superseded_by_a_newer_authorization) {
  Rig rig;
  const FlightStatusView fs = readyStatus();
  const Authorization a1 = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  const Authorization a2 = rig.mgr.authorize(ActuatorRequest::ReleaseParachute, fs, SYNTHETIC_AFTER_SEPARATION_MS);
  CHECK(a1.valid && a2.valid && a1.serial != a2.serial);
  CHECK(rig.mgr.execute(a1, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedNotAuthorized);
  CHECK(rig.mgr.execute(a2, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::ExecutedSimulated);
  CHECK(rig.mgr.execute(a1, fs, SYNTHETIC_AFTER_SEPARATION_MS) == ActuatorDecision::BlockedAlreadyDone);
  CHECK(rig.driver.applied.size() == 1);
}

TEST_CASE(a_default_or_forged_token_is_refused) {
  Rig rig;
  Authorization forged;
  CHECK(rig.mgr.execute(forged, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::BlockedNotAuthorized);
  forged.valid = true;
  forged.boot_count = SYNTHETIC_BOOT;
  forged.serial = 77;
  CHECK(rig.mgr.execute(forged, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::BlockedNotAuthorized);
  CHECK(rig.driver.applied.empty());
}

TEST_CASE(token_from_before_a_reset_is_refused_after_the_reset) {
  Authorization a;
  {
    Rig boot1(1);
    a = boot1.mgr.authorize(ActuatorRequest::ReleaseParachute, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS);
    CHECK(a.valid);
  }  // RAM lost
  Rig boot2(2);
  CHECK(boot2.mgr.execute(a, readyStatus(), SYNTHETIC_AFTER_SEPARATION_MS) ==
        ActuatorDecision::BlockedStaleAuthorization);
  CHECK(boot2.driver.applied.empty());
}

// ============ Integration with the (unchanged) state machine and recovery ============

namespace {
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

FlightStatusView viewOf(const FlightStateManager& fsm) {
  FlightStatusView v;
  v.state = fsm.state();
  v.one_shot_flags = fsm.oneShotFlags();
  v.release_timer_start_ms = fsm.releaseTimerStartMs();
  return v;
}
}  // namespace

TEST_CASE(entering_parachute_deploy_never_actuates_by_itself) {
  FlightParams fp = flightParams();
  MockPersistentStore store;
  RecoveryManager rec(store);
  Sink fsm_sink;
  FlightStateManager fsm(fp, rec, fsm_sink);
  fsm.start(rec.restoreOnBoot(), 0);
  Rig rig;
  toParachuteDeploy(fsm);
  for (uint32_t t = 100; t < 5000; t += 50) fsm.tick(t);
  CHECK(fsm.state() == FlightState::ParachuteDeploy);
  CHECK(fsm.requestsEmitted() == 1);   // a REQUEST exists ...
  CHECK(rig.driver.applied.empty());   // ... but nothing reached any driver
  CHECK(rig.connection.calls == 0);    // the interlock was not even consulted
}

TEST_CASE(state_machine_request_passes_through_the_interlock_once) {
  FlightParams fp = flightParams();
  MockPersistentStore store;
  RecoveryManager rec(store);
  Sink fsm_sink;
  FlightStateManager fsm(fp, rec, fsm_sink);
  fsm.start(rec.restoreOnBoot(), 0);
  Rig rig;
  toParachuteDeploy(fsm);
  int executed = 0;
  for (uint32_t t = 100; t < 5000; t += 50) {
    fsm.tick(t);
    ActuatorRequest req;
    while (fsm.popRequest(req)) {
      if (rig.mgr.handle(req, viewOf(fsm), t) == ActuatorDecision::ExecutedSimulated) ++executed;
    }
  }
  CHECK(executed == 1);
  CHECK(rig.driver.applied.size() == 1);
}

TEST_CASE(reset_after_execution_never_actuates_again) {
  FlightParams fp = flightParams();
  MockPersistentStore store;
  int total_applied = 0;
  for (uint16_t boot = 1; boot <= 3; ++boot) {
    RecoveryManager rec(store);
    Sink fsm_sink;
    FlightStateManager fsm(fp, rec, fsm_sink);
    const RestoreResult rr = rec.restoreOnBoot();
    fsm.start(rr, 0);
    if (boot == 1) toParachuteDeploy(fsm);
    Rig rig(rr.boot_count);
    for (uint32_t t = 100; t < 5000; t += 50) {
      fsm.tick(t);
      ActuatorRequest req;
      while (fsm.popRequest(req)) rig.mgr.handle(req, viewOf(fsm), t);
    }
    total_applied += static_cast<int>(rig.driver.applied.size());
  }
  CHECK(total_applied == 1);
}

// HAZARD (documents CURRENT behaviour; OD-070). The state machine persists its
// "requested" flag BEFORE queueing, and the manager's "executed" record is
// RAM-only. A reset after the request was persisted but before it executed
// therefore loses the actuation for good: after the reset the request is
// suppressed as "already requested". This test must be updated deliberately
// when the team decides how execution should be recorded (needs an approved
// change to the recovery implementation).
TEST_CASE(HAZARD_reset_between_authorization_and_execution_loses_the_actuation) {
  FlightParams fp = flightParams();
  MockPersistentStore store;
  Authorization pending;
  {
    RecoveryManager rec(store);
    Sink fsm_sink;
    FlightStateManager fsm(fp, rec, fsm_sink);
    const RestoreResult rr = rec.restoreOnBoot();
    fsm.start(rr, 0);
    toParachuteDeploy(fsm);
    Rig rig(rr.boot_count);
    for (uint32_t t = 100; t < 5000 && !pending.valid; t += 50) {
      fsm.tick(t);
      ActuatorRequest req;
      if (fsm.popRequest(req)) pending = rig.mgr.authorize(req, viewOf(fsm), t);
    }
    CHECK(pending.valid);
    CHECK(rig.driver.applied.empty());
  }  // reset before execute()
  RecoveryManager rec(store);
  Sink fsm_sink;
  FlightStateManager fsm(fp, rec, fsm_sink);
  const RestoreResult rr = rec.restoreOnBoot();
  fsm.start(rr, 0);
  Rig rig(rr.boot_count);
  CHECK(rig.mgr.execute(pending, viewOf(fsm), 100) == ActuatorDecision::BlockedStaleAuthorization);
  int requests = 0;
  for (uint32_t t = 100; t < 10000; t += 50) {
    fsm.tick(t);
    ActuatorRequest req;
    while (fsm.popRequest(req)) {
      ++requests;
      rig.mgr.handle(req, viewOf(fsm), t);
    }
  }
  CHECK(fsm.state() == FlightState::ParachuteDeploy);
  CHECK(requests == 0);               // suppressed: "already requested"
  CHECK(rig.driver.applied.empty());  // => never executed in any boot
}

int main() { return th::runAll(); }
