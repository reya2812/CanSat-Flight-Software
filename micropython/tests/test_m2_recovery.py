# Module 2: recovery record, corrupt / missing records and resets during flight.
# INVARIANT_ tests: must hold whichever recovery approach (R-A..R-F, OD-069) is chosen.
# HAZARD_ tests: pin CURRENT behaviour (R-A) that is a known hazard; update them
# deliberately when OD-069 is decided. NVS brownout survival is [UNVERIFIED].
# SIMULATED, not hardware validation. All values SYNTHETIC.
import unittest

from cansat.core import types as T
from cansat.core.flight_software import BootReport
from cansat.core.num import f32
from cansat.core.recovery_manager import (RecoveryManager, record_from_bytes, record_to_bytes,
                                          RECOVERY_MAGIC, RECOVERY_VERSION, recovery_crc)
from cansat.mock.persistent_store import MockPersistentStore
from cansat.config import flight_params as FP
from tests.helpers_m2 import SYNTHETIC_GROUND_PA, boot, run, seeded_store

IN_FLIGHT = (T.STATE_ASCENT, T.STATE_RELEASE_DETECTED, T.STATE_PARACHUTE_DEPLOY, T.STATE_PANEL_DEPLOY,
             T.STATE_DESCENT, T.STATE_LANDED)
SYNTHETIC_ALTITUDE_PA = 100100.0  # roughly 100 m above SYNTHETIC_GROUND_PA


def types(events):
    return [e.type for e in events]


class RecoveryManagerUnit(unittest.TestCase):
    def test_no_record_is_a_first_boot(self):
        st = MockPersistentStore()
        r = RecoveryManager(st).restore_on_boot()
        self.assertFalse(r.had_record or r.corrupt or r.resumed)
        self.assertEqual((r.state, r.boot_count), (T.STATE_POWER_ON_SELF_CHECK, 1))
        ok, rec = st.load()
        self.assertTrue(ok)
        self.assertEqual(rec.crc, recovery_crc(rec))

    def test_every_kind_of_bad_record_is_corrupt(self):
        def bad(mut):
            st = seeded_store(T.STATE_DESCENT, T.ONESHOT_RELEASE_CONFIRMED)
            mut(st.record())
            return RecoveryManager(st).restore_on_boot()

        def recrc(f):
            def g(r):
                f(r)
                r.crc = recovery_crc(r)  # structurally invalid but CRC valid
            return g
        cases = {
            "crc": lambda r: setattr(r, "crc", r.crc ^ 1),
            "magic": recrc(lambda r: setattr(r, "magic", RECOVERY_MAGIC ^ 1)),
            "version": recrc(lambda r: setattr(r, "version", RECOVERY_VERSION + 1)),
            "state0": recrc(lambda r: setattr(r, "last_state", 0)),
            "state9": recrc(lambda r: setattr(r, "last_state", 9)),
        }
        for name, mut in cases.items():
            with self.subTest(case=name):
                r = bad(mut)
                self.assertTrue(r.had_record and r.corrupt)
                self.assertFalse(r.resumed or r.has_ground)
                self.assertEqual((r.state, r.one_shot_flags, r.boot_count), (T.STATE_POWER_ON_SELF_CHECK, 0, 1))

    def test_ground_states_restart_self_check_without_restoring(self):
        for s in (T.STATE_POWER_ON_SELF_CHECK, T.STATE_READY_ON_DRONE):
            with self.subTest(state=s):
                r = RecoveryManager(seeded_store(s, flags=T.ONESHOT_RELEASE_CONFIRMED, boot_count=4)).restore_on_boot()
                self.assertFalse(r.resumed or r.corrupt or r.has_ground)
                self.assertEqual((r.state, r.one_shot_flags, r.boot_count), (T.STATE_POWER_ON_SELF_CHECK, 0, 5))

    def test_in_flight_states_resume_with_flags_and_ground(self):
        for s in IN_FLIGHT:
            with self.subTest(state=s):
                r = RecoveryManager(seeded_store(s, flags=3, boot_count=2)).restore_on_boot()
                self.assertTrue(r.resumed and r.has_ground)
                self.assertEqual((r.state, r.one_shot_flags, r.boot_count), (s, 3, 3))
                self.assertEqual(r.ground_pressure_pa, f32(SYNTHETIC_GROUND_PA))

    def test_zero_ground_is_not_a_ground_reference(self):
        r = RecoveryManager(seeded_store(T.STATE_ASCENT, ground=0.0)).restore_on_boot()
        self.assertTrue(r.resumed)
        self.assertFalse(r.has_ground)

    def test_boot_count_wraps_like_uint16(self):
        r = RecoveryManager(seeded_store(T.STATE_ASCENT, boot_count=0xFFFF)).restore_on_boot()
        self.assertEqual(r.boot_count, 0)

    def test_write_failure_reported_and_store_unchanged(self):
        st = seeded_store(T.STATE_ASCENT)
        rm = RecoveryManager(st)
        rm.restore_on_boot()
        st.fail_writes = True
        self.assertFalse(rm.persist(T.STATE_RELEASE_DETECTED, 0))
        self.assertEqual(st.record().last_state, T.STATE_ASCENT)

    def test_store_keeps_copies(self):
        st = MockPersistentStore()
        rm = RecoveryManager(st)
        rm.restore_on_boot()
        rm.record().last_state = T.STATE_LANDED  # RAM change without persist
        self.assertEqual(st.load()[1].last_state, T.STATE_POWER_ON_SELF_CHECK)

    def test_mock_store_copies_on_save_and_load(self):
        st = MockPersistentStore()
        r = seeded_store(T.STATE_ASCENT).record()
        st.save(r)
        r.last_state = T.STATE_LANDED
        self.assertEqual(st.load()[1].last_state, T.STATE_ASCENT)
        st.load()[1].last_state = T.STATE_LANDED
        self.assertEqual(st.load()[1].last_state, T.STATE_ASCENT)

    def test_record_bytes_round_trip(self):
        st = seeded_store(T.STATE_DESCENT, flags=5, boot_count=7)
        r = st.record()
        b = record_to_bytes(r)
        self.assertEqual(len(b), 22)  # <IHHBBIfI, no padding
        back = record_from_bytes(b)
        self.assertEqual(record_to_bytes(back), b)
        self.assertIsNone(record_from_bytes(b[:-1]))
        self.assertIsNone(record_from_bytes(None))


class InvariantsAcrossResets(unittest.TestCase):
    def test_INVARIANT_corrupt_record_never_resumes_or_restores(self):
        for s in IN_FLIGHT:
            with self.subTest(state=s):
                st = seeded_store(s, flags=T.ONESHOT_RELEASE_CONFIRMED | T.ONESHOT_CHUTE_REQUESTED)
                st.corrupt()
                fs = boot(st)
                self.assertTrue(fs.restore().corrupt)
                self.assertEqual(fs.state(), T.STATE_POWER_ON_SELF_CHECK)
                self.assertEqual(fs.fsm().one_shot_flags(), 0)
                self.assertFalse(fs.detector().has_ground_reference())
                self.assertTrue(fs.fault_mask() & T.FAULT_RECOVERY_RECORD_CORRUPT)
                self.assertNotIn(T.EV_RESET_RECOVERED, types(fs.events()))

    def test_INVARIANT_missing_record_is_a_clean_first_boot(self):
        fs = boot(MockPersistentStore())
        self.assertFalse(fs.restore().had_record)
        self.assertEqual(fs.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertFalse(fs.fault_mask() & T.FAULT_RECOVERY_RECORD_CORRUPT)

    def test_INVARIANT_corrupt_or_missing_record_alone_never_requests(self):
        for corrupt in (True, False):
            for sw_open in (True, False):
                with self.subTest(corrupt=corrupt, mount_open=sw_open):
                    st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
                    st.corrupt() if corrupt else st.erase()
                    fs = boot(st)
                    _, reqs = run(fs, 0, 10000, sw_open=sw_open)
                    self.assertEqual(reqs, [])

    def test_INVARIANT_reset_in_flight_resumes_same_state_and_never_rerequests(self):
        for s in IN_FLIGHT:
            with self.subTest(state=s):
                flags = T.ONESHOT_RELEASE_CONFIRMED | T.ONESHOT_CHUTE_REQUESTED if s >= T.STATE_PARACHUTE_DEPLOY else 0
                fs = boot(seeded_store(s, flags))
                ev = fs.events()
                self.assertEqual(fs.state(), s)
                rec = [e for e in ev if e.type == T.EV_RESET_RECOVERED]
                self.assertEqual([e.detail for e in rec], [s])
                if flags & T.ONESHOT_CHUTE_REQUESTED:
                    self.assertIn(T.EV_REQUEST_SUPPRESSED, types(ev))
                events, reqs = run(fs, 50, 8000, pressure=SYNTHETIC_GROUND_PA, sw_open=True)
                if flags & T.ONESHOT_CHUTE_REQUESTED:
                    self.assertEqual(reqs, [])
                    self.assertNotIn(T.EV_REQUEST_EMITTED, types(events))

    def test_INVARIANT_repeated_resets_never_request_twice(self):
        st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
        total = []
        for k in range(5):
            fs = boot(st)
            _, reqs = run(fs, 50, 1000, sw_open=True)
            total.extend(reqs)
        self.assertEqual(len(total), 1)

    def test_separation_timer_restarts_after_reset(self):
        # Release confirmed, chute not yet requested, reset: the request waits a full
        # min_separation_ms from the NEW boot (conservative; OD-070 notes).
        fs = boot(seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED), now=0)
        _, reqs = run(fs, 50, 1000, sw_open=True)
        self.assertEqual(reqs, [(300, T.REQ_RELEASE_PARACHUTE)])  # SYNTHETIC_MIN_SEPARATION_MS = 300


class Hazards(unittest.TestCase):
    def test_HAZARD_corrupt_record_after_release_never_requests(self):
        # OD-069: self-check needs the mount closed, which cannot happen after
        # separation, so the CanSat never leaves POWER_ON_SELF_CHECK.
        st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
        st.corrupt()
        fs = boot(st)
        events, reqs = run(fs, 50, 20000, pressure=SYNTHETIC_ALTITUDE_PA, acc=(0.0, 0.0, 0.05), sw_open=True)
        self.assertEqual(reqs, [])
        self.assertEqual(fs.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertNotIn(T.EV_SELF_CHECK_PASS, types(events))
        self.assertFalse(fs.fault_mask() & T.FAULT_SELF_CHECK)  # stuck self-check raises no specific fault

    def test_HAZARD_erased_record_after_release_looks_like_first_boot(self):
        st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
        st.erase()
        fs = boot(st)
        self.assertFalse(fs.fault_mask() & T.FAULT_RECOVERY_RECORD_CORRUPT)
        _, reqs = run(fs, 50, 5000, sw_open=True)
        self.assertEqual(reqs, [])

    def test_HAZARD_corrupt_record_while_mounted_recaptures_ground_at_altitude(self):
        st = seeded_store(T.STATE_ASCENT)
        st.corrupt()
        fs = boot(st)
        run(fs, 50, 1000, pressure=SYNTHETIC_ALTITUDE_PA, sw_open=False)
        self.assertEqual(fs.state(), T.STATE_READY_ON_DRONE)
        self.assertEqual(fs.detector().ground_pressure_pa(), f32(SYNTHETIC_ALTITUDE_PA))

    def test_HAZARD_request_anyway_duplicates_after_reset(self):
        # OD-067 RequestAnyway: the flag could not be saved, so a reset re-requests.
        st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
        fs = boot(st, policy=FP.POLICY_STRICT_SWITCH_VETO)
        st.fail_writes = True
        _, first = run(fs, 50, 1000, sw_open=True)
        st.fail_writes = False
        fs = boot(st)
        _, second = run(fs, 50, 1000, sw_open=True)
        self.assertEqual((len(first), len(second)), (1, 1))
        self.assertTrue(st.record().one_shot_flags & T.ONESHOT_CHUTE_REQUESTED)

    def test_HAZARD_withhold_never_requests_while_storage_fails(self):
        st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
        p_policy = FP.PERSIST_WITHHOLD_UNTIL_PERSISTED
        from tests.helpers_m2 import params
        from cansat.core.flight_software import FlightSoftware
        prm = params()
        prm.interlock.persist_failure_policy.set(p_policy)
        fs = FlightSoftware(prm, st)
        fs.boot(BootReport(True, True, True), 0)
        st.fail_writes = True
        falling = dict(sw_open=True, pressure=SYNTHETIC_ALTITUDE_PA, acc=(0.0, 0.0, 0.05))  # never "landed"
        events, reqs = run(fs, 50, 3000, **falling)
        self.assertEqual(reqs, [])
        self.assertEqual(types(events).count(T.EV_REQUEST_WITHHELD), 1)
        self.assertTrue(fs.fault_mask() & T.FAULT_REQUEST_WITHHELD)
        st.fail_writes = False
        _, reqs = run(fs, 3050, 3100, **falling)
        self.assertEqual(reqs, [(3050, T.REQ_RELEASE_PARACHUTE)])


if __name__ == "__main__":
    unittest.main()
