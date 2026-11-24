# Module 3: persisted-record faults at scenario level (OD-069). [SIMULATED]
# One-to-one port of firmware/test/test_recovery_faults.cpp (13 cases).
#   INVARIANT_*  must hold whichever recovery approach (R-A..R-F) is chosen.
#   HAZARD_*     pin CURRENT behaviour (R-A); not approved behaviour.
import unittest

from cansat.core import types as T
from cansat.core.flight_state_manager import FlightStateManager
from cansat.core.recovery_manager import RECOVERY_MAGIC, RECOVERY_VERSION, RecoveryManager, recovery_crc
from cansat.config import flight_params as FP
from cansat.mock.memory_log import MemoryLogSink
from cansat.mock.persistent_store import MockPersistentStore
from cansat.sim.fsw_hook import FlightSoftwareHook
from cansat.sim.runner import run
from cansat.sim.scenarios import (all_synthetic_scenarios, every_synthetic_scenario, find_synthetic_scenario,
                                  recovery_fault_scenarios)
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params


class Sink:
    def __init__(self):
        self.events = []

    def on_event(self, e):
        self.events.append(e)


def run_fsw(name, pol):
    sc = find_synthetic_scenario(name)
    hook = FlightSoftwareHook(synthetic_flight_params(pol))
    hook.set_store_faults(sc.store_faults)
    log = MemoryLogSink()
    run(sc, log, hook)
    return hook.stats, log


def truth_mounted_at_requests(log):
    return [1 if l.split(",")[6] == "1" else 0 for l in log.lines
            if l and l[0] != "#" and "REQUEST:" in l]


def to_parachute_deploy(fsm):
    t = 0
    for s in (T.EV_SELF_CHECK_PASS, T.EV_ASCENT_DETECTED, T.EV_RELEASE_CANDIDATE, T.EV_RELEASE_CONFIRMED):
        t += 10
        fsm.on_event(T.Event(s, t, T.BASIS_SWITCH_AND_FREEFALL))


VETO = FP.POLICY_STRICT_SWITCH_VETO


class Invariants(unittest.TestCase):
    def test_INVARIANT_scenario_sets_are_separate_and_named(self):
        self.assertEqual(len(all_synthetic_scenarios()), 13)
        rf = recovery_fault_scenarios()
        self.assertEqual(len(rf), 4)
        for sc in rf:
            self.assertTrue(sc.store_faults)
            self.assertIn("HAZARD", sc.description)
        self.assertEqual(len(every_synthetic_scenario()), 17)

    def test_INVARIANT_corrupt_record_never_resumes_or_restores_one_shots(self):
        for code in range(1, 9):
            store = MockPersistentStore()
            rec = RecoveryManager(store)
            rec.restore_on_boot()
            rec.set_ground_pressure(100000.0)
            rec.persist(code, T.ONESHOT_RELEASE_CONFIRMED | T.ONESHOT_CHUTE_REQUESTED)
            store.corrupt()
            rr = RecoveryManager(store).restore_on_boot()
            self.assertTrue(rr.corrupt)
            self.assertFalse(rr.resumed or rr.has_ground)
            self.assertEqual((rr.state, rr.one_shot_flags), (T.STATE_POWER_ON_SELF_CHECK, 0))

    def test_INVARIANT_structurally_invalid_records_are_treated_as_corrupt(self):
        for field, value in (("magic", RECOVERY_MAGIC ^ 1), ("version", RECOVERY_VERSION + 1), ("last_state", 99)):
            r = T.RecoveryRecord()
            r.magic, r.version, r.boot_count, r.last_state = RECOVERY_MAGIC, RECOVERY_VERSION, 1, T.STATE_PARACHUTE_DEPLOY
            setattr(r, field, value)
            r.crc = recovery_crc(r)
            store = MockPersistentStore()
            store.save(r)
            rr = RecoveryManager(store).restore_on_boot()
            self.assertTrue(rr.corrupt and not rr.resumed and rr.one_shot_flags == 0, field)

    def test_INVARIANT_corrupt_or_absent_record_alone_never_causes_a_request(self):
        for kind in (0, 1):
            fp = synthetic_flight_params(VETO)
            store = MockPersistentStore()
            rec = RecoveryManager(store)
            fsm = FlightStateManager(fp, rec, Sink())
            fsm.start(rec.restore_on_boot(), 0)
            to_parachute_deploy(fsm)
            store.corrupt() if kind == 0 else store.erase()
            rec = RecoveryManager(store)
            fsm = FlightStateManager(fp, rec, Sink())
            fsm.start(rec.restore_on_boot(), 0)
            for t in range(0, 60000, 50):
                fsm.tick(t)
            self.assertEqual(fsm.requests_emitted(), 0)
            self.assertEqual(fsm.one_shot_flags(), 0)
            self.assertEqual(bool(fsm.fault_mask() & T.FAULT_RECOVERY_RECORD_CORRUPT), kind == 0)

    def test_INVARIANT_recovery_fault_scenarios_never_request_twice_or_while_mounted(self):
        for sc in recovery_fault_scenarios():
            for pol in CANDIDATE_POLICIES:
                with self.subTest(scenario=sc.name, policy=pol):
                    st, log = run_fsw(sc.name, pol)
                    self.assertLessEqual(st.requests, 1)
                    self.assertEqual(st.store_faults_applied, len(sc.store_faults))
                    self.assertTrue(all(m == 0 for m in truth_mounted_at_requests(log)))
                    for l in log.lines:
                        if "REQUEST:" in l:
                            self.assertIn("NOT_EXECUTED", l)

    def test_INVARIANT_corrupt_record_fault_is_visible_for_the_rest_of_the_boot(self):
        for n in ("corrupt_record_after_release", "corrupt_record_after_request", "corrupt_record_mounted_ascent"):
            for pol in CANDIDATE_POLICIES:
                st, _ = run_fsw(n, pol)
                self.assertEqual(st.corrupt_restarts, 1)
                self.assertTrue(st.final_faults & T.FAULT_RECOVERY_RECORD_CORRUPT)

    def test_INVARIANT_recovery_fault_runs_are_deterministic(self):
        a = run_fsw("corrupt_record_after_release", FP.POLICY_VOTE_2_OF_3)[1]
        b = run_fsw("corrupt_record_after_release", FP.POLICY_VOTE_2_OF_3)[1]
        self.assertEqual(a.lines, b.lines)


class Hazards(unittest.TestCase):
    def test_HAZARD_corrupt_record_after_release_means_no_parachute_request(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("corrupt_record_after_release", pol)
            self.assertEqual((st.release_confirmed, st.requests), (1, 0))
            self.assertEqual((st.final_state, st.final_chute), (T.STATE_POWER_ON_SELF_CHECK, T.CHUTE_NOT_REQUESTED))

    def test_HAZARD_stuck_self_check_after_corrupt_restart_raises_no_specific_fault(self):
        st, _ = run_fsw("corrupt_record_after_release", VETO)
        self.assertEqual(st.final_faults & T.FAULT_SELF_CHECK, 0)
        self.assertTrue(st.final_faults & T.FAULT_RECOVERY_RECORD_CORRUPT)

    def test_HAZARD_erased_record_after_release_looks_like_first_boot(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("record_erased_after_release", pol)
            self.assertEqual((st.requests, st.final_state, st.corrupt_restarts), (0, T.STATE_POWER_ON_SELF_CHECK, 0))
            self.assertEqual(st.final_faults & T.FAULT_RECOVERY_RECORD_CORRUPT, 0)

    def test_HAZARD_corrupt_record_after_request_forgets_the_request(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("corrupt_record_after_request", pol)
            self.assertEqual(st.requests, 1)
            self.assertEqual((st.final_state, st.final_chute), (T.STATE_POWER_ON_SELF_CHECK, T.CHUTE_NOT_REQUESTED))

    def test_HAZARD_corrupt_record_while_mounted_recaptures_ground_at_altitude(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("corrupt_record_mounted_ascent", pol)
            self.assertGreaterEqual(st.states_entered.count(T.STATE_POWER_ON_SELF_CHECK), 2)
            self.assertGreaterEqual(st.states_entered.count(T.STATE_READY_ON_DRONE), 2)
            self.assertNotEqual(st.final_state, T.STATE_LANDED)

    def test_HAZARD_write_failure_then_reset_resumes_an_older_state(self):
        fp = synthetic_flight_params(VETO)
        store = MockPersistentStore()
        rec = RecoveryManager(store)
        fsm = FlightStateManager(fp, rec, Sink())
        fsm.start(rec.restore_on_boot(), 0)
        fsm.on_event(T.Event(T.EV_SELF_CHECK_PASS, 10))
        fsm.on_event(T.Event(T.EV_ASCENT_DETECTED, 20))
        self.assertEqual(fsm.state(), T.STATE_ASCENT)
        store.fail_writes = True
        fsm.on_event(T.Event(T.EV_RELEASE_CANDIDATE, 30))
        fsm.on_event(T.Event(T.EV_RELEASE_CONFIRMED, 40, T.BASIS_SWITCH_AND_FREEFALL))
        self.assertEqual(fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertTrue(fsm.fault_mask() & T.FAULT_PERSIST_WRITE)
        store.fail_writes = False
        rr = RecoveryManager(store).restore_on_boot()
        self.assertTrue(rr.resumed)
        self.assertEqual(rr.state, T.STATE_ASCENT)
        self.assertEqual(rr.one_shot_flags & T.ONESHOT_RELEASE_CONFIRMED, 0)


if __name__ == "__main__":
    unittest.main()
