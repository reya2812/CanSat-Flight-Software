# Module 3: DeploymentInterlock + ActuatorManager (OD-070), mocks only.
# One-to-one port of firmware/test/test_interlock.cpp (29 cases).
# [SIMULATED] No hardware. The only "physical" driver is a test-local fake that
# CLAIMS to be physical so the refusal path can be checked; it touches nothing.
# The connection assessment is scripted: no release architecture (A1-A5) or
# switch behaviour is implemented or assumed. SYNTHETIC values for these tests only.
import unittest

from cansat.config import flight_params as FP
from cansat.core import types as T
from cansat.core.actuator_manager import ActuatorManager, Authorization, FlightStatusView
from cansat.core.deployment_interlock import DeploymentInterlock, InterlockInputs
from cansat.core.flight_state_manager import FlightStateManager
from cansat.core.recovery_manager import RecoveryManager
from cansat.hal.interfaces import ActuatorDriver
from cansat.mock.actuators import MockActuatorDriver, MockArmingSource, ScriptedConnectionSource
from cansat.mock.persistent_store import MockPersistentStore
from cansat.sim.synthetic_flight_params import synthetic_flight_params

SYNTHETIC_CONNECTION_MAX_AGE_MS = 100
SYNTHETIC_RELEASE_AT_MS = 1000
SYNTHETIC_AFTER_SEPARATION_MS = 2000  # > release + SYNTHETIC min separation (300)
SYNTHETIC_BOOT = 1
REL = T.REQ_RELEASE_PARACHUTE
NOW = SYNTHETIC_AFTER_SEPARATION_MS


class Sink:
    def __init__(self):
        self.events = []

    def on_event(self, e):
        self.events.append(e)


class FakePhysicalDriver(ActuatorDriver):
    """Claims to be physical. Used only to prove the manager refuses it."""

    def __init__(self):
        self.calls = 0

    def apply(self, request):
        self.calls += 1

    def is_physical(self):
        return True


def flight_params():
    return synthetic_flight_params(FP.POLICY_STRICT_SWITCH_VETO)


def il_params():
    p = FP.DeploymentInterlockParams()
    p.connection_max_age_ms.set(SYNTHETIC_CONNECTION_MAX_AGE_MS)
    return p


def ready_status():
    return FlightStatusView(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED | T.ONESHOT_CHUTE_REQUESTED,
                            SYNTHETIC_RELEASE_AT_MS)


def conn(v, t=0):
    return T.ConnectionAssessmentSample(v, t)


def arm(s):
    return T.ArmingSample(s)


class Rig:
    """A fully permissive rig: every gate passes unless a test changes something."""

    def __init__(self, boot=SYNTHETIC_BOOT):
        self.fp, self.ip = flight_params(), il_params()
        self.connection = ScriptedConnectionSource()
        self.arming = MockArmingSource()
        self.driver = MockActuatorDriver()
        self.sink = Sink()
        self.mgr = ActuatorManager(self.fp, self.ip, self.connection, self.arming, self.driver, self.sink, boot)
        self.connection.current = conn(T.CONN_SEPARATED)
        self.arming.current = arm(T.ARM_ARMED)


def permissive_inputs():
    i = InterlockInputs()
    i.request = REL
    i.now_ms = NOW
    fs = ready_status()
    i.state, i.one_shot_flags, i.release_timer_start_ms = fs.state, fs.one_shot_flags, fs.release_timer_start_ms
    i.arming = arm(T.ARM_ARMED)
    i.connection = conn(T.CONN_SEPARATED, NOW)
    return i


def decision_of(e):
    return (e.detail >> 16) & 0xFF


def phase_of(e):
    return 1 if e.detail >> 31 else 0


class Configuration(unittest.TestCase):
    def test_unset_interlock_params_block_everything(self):
        il = DeploymentInterlock(flight_params(), FP.DeploymentInterlockParams())
        self.assertFalse(il.configured())
        r = il.evaluate(permissive_inputs())
        self.assertFalse(r.permitted)
        self.assertEqual(r.decision, T.DEC_BLOCKED_PARAMS_INCOMPLETE)
        self.assertTrue(r.reasons & T.IL_PARAMS_INCOMPLETE)

    def test_unset_flight_params_block_everything(self):
        il = DeploymentInterlock(FP.FlightParams(), il_params())
        self.assertFalse(il.configured())
        self.assertFalse(il.evaluate(permissive_inputs()).permitted)

    def test_default_sources_and_default_inputs_block(self):
        il = DeploymentInterlock(flight_params(), il_params())
        i = permissive_inputs()
        i.arming = T.ArmingSample()
        i.connection = T.ConnectionAssessmentSample()
        r = il.evaluate(i)
        self.assertFalse(r.permitted)
        self.assertTrue(r.reasons & T.IL_ARM_UNKNOWN)
        self.assertTrue(r.reasons & T.IL_CONN_UNAVAILABLE)
        self.assertFalse(il.evaluate(InterlockInputs()).permitted)

    def test_all_gates_pass_is_authorized_and_executes_only_the_mock(self):
        rig = Rig()
        self.assertEqual(rig.mgr.handle(REL, ready_status(), NOW), T.DEC_EXECUTED_SIMULATED)
        self.assertEqual(len(rig.driver.applied), 1)
        self.assertIs(rig.driver.is_physical(), False)
        self.assertEqual(rig.mgr.executed_count(), 1)
        self.assertEqual((rig.connection.calls, rig.arming.calls), (2, 2))  # fresh reads in BOTH phases


class Gates(unittest.TestCase):
    def test_every_connection_value_except_separated_blocks(self):
        cases = [(T.CONN_UNAVAILABLE, T.IL_CONN_UNAVAILABLE, T.DEC_BLOCKED_CONNECTION_UNAVAILABLE),
                 (T.CONN_INVALID, T.IL_CONN_INVALID, T.DEC_BLOCKED_CONNECTION_INVALID),
                 (T.CONN_INDETERMINATE, T.IL_CONN_INDETERMINATE, T.DEC_BLOCKED_CONNECTION_INDETERMINATE),
                 (T.CONN_CONNECTED, T.IL_CONN_CONNECTED, T.DEC_BLOCKED_INTERLOCK_MOUNTED)]
        for v, bit, d in cases:
            with self.subTest(value=v):
                rig = Rig()
                rig.connection.current = conn(v)
                self.assertEqual(rig.mgr.handle(REL, ready_status(), NOW), d)
                self.assertTrue(rig.mgr.last_result().reasons & bit)
                self.assertEqual(rig.driver.applied, [])

    def test_stale_and_future_dated_assessments_block(self):
        il = DeploymentInterlock(flight_params(), il_params())
        i = permissive_inputs()
        i.connection.t_ms = i.now_ms - SYNTHETIC_CONNECTION_MAX_AGE_MS  # exactly at the limit: accepted
        self.assertTrue(il.evaluate(i).permitted)
        i.connection.t_ms = i.now_ms - SYNTHETIC_CONNECTION_MAX_AGE_MS - 1
        r = il.evaluate(i)
        self.assertTrue(not r.permitted and r.reasons & T.IL_CONN_STALE)
        self.assertEqual(r.decision, T.DEC_BLOCKED_CONNECTION_STALE)
        i.connection.t_ms = i.now_ms + 1
        r = il.evaluate(i)
        self.assertTrue(not r.permitted and r.reasons & T.IL_CONN_FUTURE_TIMESTAMP)

    def test_stale_connected_assessment_reports_both_reasons(self):
        il = DeploymentInterlock(flight_params(), il_params())
        i = permissive_inputs()
        i.connection = conn(T.CONN_CONNECTED, 0)
        r = il.evaluate(i)
        self.assertTrue(r.reasons & T.IL_CONN_CONNECTED and r.reasons & T.IL_CONN_STALE)

    def test_disarmed_or_unknown_arming_blocks(self):
        for s, bit in ((T.ARM_DISARMED, T.IL_NOT_ARMED), (T.ARM_UNKNOWN, T.IL_ARM_UNKNOWN)):
            with self.subTest(state=s):
                rig = Rig()
                rig.arming.current = arm(s)
                self.assertEqual(rig.mgr.handle(REL, ready_status(), NOW), T.DEC_BLOCKED_NOT_ARMED)
                self.assertTrue(rig.mgr.last_result().reasons & bit)
                self.assertEqual(rig.driver.applied, [])

    def test_any_state_other_than_parachute_deploy_blocks(self):
        for code in range(1, 9):
            if code == T.STATE_PARACHUTE_DEPLOY:
                continue
            with self.subTest(state=code):
                rig = Rig()
                fs = ready_status()
                fs.state = code
                self.assertEqual(rig.mgr.handle(REL, fs, NOW), T.DEC_BLOCKED_WRONG_STATE)
                self.assertEqual(rig.driver.applied, [])

    def test_release_not_confirmed_blocks_even_in_parachute_deploy(self):
        rig = Rig()
        fs = ready_status()
        fs.one_shot_flags = T.ONESHOT_CHUTE_REQUESTED
        self.assertEqual(rig.mgr.handle(REL, fs, NOW), T.DEC_BLOCKED_RELEASE_NOT_CONFIRMED)
        self.assertEqual(rig.driver.applied, [])

    def test_separation_delay_is_rechecked_independently(self):
        rig = Rig()
        sep = rig.fp.interlock.min_separation_ms.require()
        self.assertEqual(rig.mgr.handle(REL, ready_status(), SYNTHETIC_RELEASE_AT_MS + sep - 1),
                         T.DEC_BLOCKED_SEPARATION_DELAY)
        self.assertEqual(rig.mgr.handle(REL, ready_status(), SYNTHETIC_RELEASE_AT_MS - 1),
                         T.DEC_BLOCKED_SEPARATION_DELAY)
        self.assertEqual(rig.driver.applied, [])

    def test_requests_without_an_interlock_rule_are_refused(self):
        for r in (T.REQ_DEPLOY_PANELS, T.REQ_BUZZER_ON, T.REQ_BUZZER_OFF):
            with self.subTest(request=r):
                rig = Rig()
                self.assertEqual(rig.mgr.handle(r, ready_status(), NOW), T.DEC_BLOCKED_UNSUPPORTED_REQUEST)
                self.assertEqual(rig.driver.applied, [])

    def test_multiple_failing_gates_are_all_reported(self):
        il = DeploymentInterlock(flight_params(), il_params())
        i = permissive_inputs()
        i.state = T.STATE_ASCENT
        i.one_shot_flags = 0
        i.arming = arm(T.ARM_DISARMED)
        i.connection = conn(T.CONN_CONNECTED, i.now_ms)
        r = il.evaluate(i)
        self.assertFalse(r.permitted)
        self.assertEqual(r.decision, T.DEC_BLOCKED_WRONG_STATE)
        expected = T.IL_WRONG_STATE | T.IL_RELEASE_NOT_CONFIRMED | T.IL_NOT_ARMED | T.IL_CONN_CONNECTED
        self.assertEqual(r.reasons & expected, expected)

    def test_a_driver_claiming_to_be_physical_is_refused_and_never_called(self):
        c = ScriptedConnectionSource()
        c.current = conn(T.CONN_SEPARATED)
        a = MockArmingSource()
        a.current = arm(T.ARM_ARMED)
        phys = FakePhysicalDriver()
        mgr = ActuatorManager(flight_params(), il_params(), c, a, phys, Sink(), SYNTHETIC_BOOT)
        self.assertEqual(mgr.handle(REL, ready_status(), NOW), T.DEC_BLOCKED_BUILD_DISABLED)
        self.assertTrue(mgr.last_result().reasons & T.IL_PHYSICAL_DRIVER_REFUSED)
        self.assertEqual((phys.calls, mgr.executed_count()), (0, 0))

    def test_decisions_are_reported_as_events_for_both_phases(self):
        rig = Rig()
        rig.mgr.handle(REL, ready_status(), NOW)
        ev = rig.sink.events
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0].type, T.EV_ACTUATOR_DECIDED)
        self.assertEqual((phase_of(ev[0]), decision_of(ev[0])), (0, T.DEC_AUTHORIZED_PENDING_EXECUTION))
        self.assertEqual((phase_of(ev[1]), decision_of(ev[1])), (1, T.DEC_EXECUTED_SIMULATED))
        self.assertEqual((ev[1].detail >> 24) & 0x7F, REL)


class EvidenceChangesBetweenPhases(unittest.TestCase):
    def test_evidence_changing_after_authorization_blocks_execution(self):
        for v in (T.CONN_CONNECTED, T.CONN_INVALID, T.CONN_UNAVAILABLE, T.CONN_INDETERMINATE):
            with self.subTest(value=v):
                rig = Rig()
                rig.connection.next = [conn(T.CONN_SEPARATED), conn(v)]
                fs = ready_status()
                a = rig.mgr.authorize(REL, fs, NOW)
                self.assertTrue(a.valid)
                self.assertNotEqual(rig.mgr.execute(a, fs, NOW + 1), T.DEC_EXECUTED_SIMULATED)
                self.assertEqual(rig.driver.applied, [])
                self.assertEqual(rig.mgr.execute(a, fs, NOW + 2), T.DEC_BLOCKED_NOT_AUTHORIZED)  # token spent

    def test_evidence_going_stale_between_phases_blocks_execution(self):
        rig = Rig()
        rig.connection.fixed_time = True
        rig.connection.current = conn(T.CONN_SEPARATED, NOW)
        fs = ready_status()
        a = rig.mgr.authorize(REL, fs, NOW)
        self.assertTrue(a.valid)
        self.assertEqual(rig.mgr.execute(a, fs, NOW + SYNTHETIC_CONNECTION_MAX_AGE_MS + 1),
                         T.DEC_BLOCKED_CONNECTION_STALE)
        self.assertEqual(rig.driver.applied, [])

    def test_disarming_between_phases_blocks_execution(self):
        rig = Rig()
        rig.arming.next = [arm(T.ARM_ARMED), arm(T.ARM_DISARMED)]
        fs = ready_status()
        a = rig.mgr.authorize(REL, fs, NOW)
        self.assertTrue(a.valid)
        self.assertEqual(rig.mgr.execute(a, fs, NOW), T.DEC_BLOCKED_NOT_ARMED)
        self.assertEqual(rig.driver.applied, [])

    def test_flight_state_changing_between_phases_blocks_execution(self):
        rig = Rig()
        fs = ready_status()
        a = rig.mgr.authorize(REL, fs, NOW)
        self.assertTrue(a.valid)
        fs.state = T.STATE_PANEL_DEPLOY
        self.assertEqual(rig.mgr.execute(a, fs, NOW), T.DEC_BLOCKED_WRONG_STATE)
        self.assertEqual(rig.driver.applied, [])

    def test_evidence_improving_after_a_blocked_authorization_does_not_execute(self):
        rig = Rig()
        rig.connection.next = [conn(T.CONN_CONNECTED), conn(T.CONN_SEPARATED)]
        fs = ready_status()
        a = rig.mgr.authorize(REL, fs, NOW)
        self.assertFalse(a.valid)
        self.assertEqual(rig.mgr.execute(a, fs, NOW), T.DEC_BLOCKED_NOT_AUTHORIZED)
        self.assertEqual(rig.driver.applied, [])


class Duplicates(unittest.TestCase):
    def test_duplicate_execute_of_one_token_actuates_once(self):
        rig = Rig()
        fs = ready_status()
        a = rig.mgr.authorize(REL, fs, NOW)
        self.assertEqual(rig.mgr.execute(a, fs, NOW), T.DEC_EXECUTED_SIMULATED)
        self.assertEqual(rig.mgr.execute(a, fs, NOW), T.DEC_BLOCKED_ALREADY_DONE)
        self.assertEqual(len(rig.driver.applied), 1)

    def test_second_request_after_execution_is_refused_at_authorization(self):
        rig = Rig()
        fs = ready_status()
        self.assertEqual(rig.mgr.handle(REL, fs, NOW), T.DEC_EXECUTED_SIMULATED)
        self.assertEqual(rig.mgr.handle(REL, fs, NOW + 1), T.DEC_BLOCKED_ALREADY_DONE)
        self.assertEqual(len(rig.driver.applied), 1)

    def test_older_token_is_superseded_by_a_newer_authorization(self):
        rig = Rig()
        fs = ready_status()
        a1 = rig.mgr.authorize(REL, fs, NOW)
        a2 = rig.mgr.authorize(REL, fs, NOW)
        self.assertTrue(a1.valid and a2.valid and a1.serial != a2.serial)
        self.assertEqual(rig.mgr.execute(a1, fs, NOW), T.DEC_BLOCKED_NOT_AUTHORIZED)
        self.assertEqual(rig.mgr.execute(a2, fs, NOW), T.DEC_EXECUTED_SIMULATED)
        self.assertEqual(rig.mgr.execute(a1, fs, NOW), T.DEC_BLOCKED_ALREADY_DONE)
        self.assertEqual(len(rig.driver.applied), 1)

    def test_a_default_or_forged_token_is_refused(self):
        rig = Rig()
        forged = Authorization()
        self.assertEqual(rig.mgr.execute(forged, ready_status(), NOW), T.DEC_BLOCKED_NOT_AUTHORIZED)
        forged.valid, forged.boot_count, forged.serial = True, SYNTHETIC_BOOT, 77
        self.assertEqual(rig.mgr.execute(forged, ready_status(), NOW), T.DEC_BLOCKED_NOT_AUTHORIZED)
        self.assertEqual(rig.driver.applied, [])

    def test_token_from_before_a_reset_is_refused_after_the_reset(self):
        a = Rig(1).mgr.authorize(REL, ready_status(), NOW)
        self.assertTrue(a.valid)
        boot2 = Rig(2)  # RAM lost
        self.assertEqual(boot2.mgr.execute(a, ready_status(), NOW), T.DEC_BLOCKED_STALE_AUTHORIZATION)
        self.assertEqual(boot2.driver.applied, [])


def to_parachute_deploy(fsm):
    t = 0
    for s in (T.EV_SELF_CHECK_PASS, T.EV_ASCENT_DETECTED, T.EV_RELEASE_CANDIDATE, T.EV_RELEASE_CONFIRMED):
        t += 10
        fsm.on_event(T.Event(s, t, T.BASIS_SWITCH_AND_FREEFALL))


def view_of(fsm):
    return FlightStatusView(fsm.state(), fsm.one_shot_flags(), fsm.release_timer_start_ms())


def new_fsm(store):
    rec = RecoveryManager(store)
    fsm = FlightStateManager(flight_params(), rec, Sink())
    rr = rec.restore_on_boot()
    fsm.start(rr, 0)
    return fsm, rr


class StateMachineIntegration(unittest.TestCase):
    def test_entering_parachute_deploy_never_actuates_by_itself(self):
        fsm, _ = new_fsm(MockPersistentStore())
        rig = Rig()
        to_parachute_deploy(fsm)
        for t in range(100, 5000, 50):
            fsm.tick(t)
        self.assertEqual(fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(fsm.requests_emitted(), 1)   # a REQUEST exists ...
        self.assertEqual(rig.driver.applied, [])      # ... but nothing reached any driver
        self.assertEqual(rig.connection.calls, 0)     # the interlock was not even consulted

    def test_state_machine_request_passes_through_the_interlock_once(self):
        fsm, _ = new_fsm(MockPersistentStore())
        rig = Rig()
        to_parachute_deploy(fsm)
        executed = 0
        for t in range(100, 5000, 50):
            fsm.tick(t)
            req = fsm.pop_request()
            while req is not None:
                executed += rig.mgr.handle(req, view_of(fsm), t) == T.DEC_EXECUTED_SIMULATED
                req = fsm.pop_request()
        self.assertEqual(executed, 1)
        self.assertEqual(len(rig.driver.applied), 1)

    def test_reset_after_execution_never_actuates_again(self):
        store = MockPersistentStore()
        total = 0
        for boot in (1, 2, 3):
            fsm, rr = new_fsm(store)
            if boot == 1:
                to_parachute_deploy(fsm)
            rig = Rig(rr.boot_count)
            for t in range(100, 5000, 50):
                fsm.tick(t)
                req = fsm.pop_request()
                while req is not None:
                    rig.mgr.handle(req, view_of(fsm), t)
                    req = fsm.pop_request()
            total += len(rig.driver.applied)
        self.assertEqual(total, 1)

    def test_HAZARD_reset_between_authorization_and_execution_loses_the_actuation(self):
        # Documents CURRENT behaviour (OD-070): see the C++ test of the same name.
        store = MockPersistentStore()
        fsm, rr = new_fsm(store)
        to_parachute_deploy(fsm)
        rig = Rig(rr.boot_count)
        pending = Authorization()
        for t in range(100, 5000, 50):
            fsm.tick(t)
            req = fsm.pop_request()
            if req is not None:
                pending = rig.mgr.authorize(req, view_of(fsm), t)
            if pending.valid:
                break
        self.assertTrue(pending.valid)
        self.assertEqual(rig.driver.applied, [])
        fsm, rr = new_fsm(store)  # reset before execute()
        rig = Rig(rr.boot_count)
        self.assertEqual(rig.mgr.execute(pending, view_of(fsm), 100), T.DEC_BLOCKED_STALE_AUTHORIZATION)
        requests = 0
        for t in range(100, 10000, 50):
            fsm.tick(t)
            req = fsm.pop_request()
            while req is not None:
                requests += 1
                rig.mgr.handle(req, view_of(fsm), t)
                req = fsm.pop_request()
        self.assertEqual(fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(requests, 0)          # suppressed: "already requested"
        self.assertEqual(rig.driver.applied, [])  # => never executed in any boot


if __name__ == "__main__":
    unittest.main()
