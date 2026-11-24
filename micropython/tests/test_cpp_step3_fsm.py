# One-to-one port of firmware/test/test_step3_fsm.cpp (42 cases): validator,
# event detector, recovery, state machine, and every SYNTHETIC scenario x every
# OD-060 candidate policy. [SIMULATED] Actuator logic disabled throughout.
import math
import unittest

from cansat.config import flight_params as FP
from cansat.core import types as T
from cansat.core.event_detector import EventDetector
from cansat.core.flight_software import BootReport, FlightSoftware
from cansat.core.flight_state_manager import FlightStateManager, is_permitted
from cansat.core.num import f32
from cansat.core.recovery_manager import RecoveryManager, recovery_crc
from cansat.core.sensor_validator import (REJECT_INVALID_FLAG, REJECT_NON_FINITE, REJECT_RANGE,
                                          REJECT_STALE_AGE, REJECT_STALE_REPEAT, REJECT_ZERO_READ,
                                          SensorValidator, ValidatedFrame)
from cansat.mock.memory_log import MemoryLogSink
from cansat.mock.persistent_store import MockPersistentStore
from cansat.sim.fsw_hook import FlightSoftwareHook
from cansat.sim.runner import run
from cansat.sim.scenarios import all_synthetic_scenarios, find_synthetic_scenario
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params

SYNTHETIC_P_PA = f32(100000.0)
SYNTHETIC_DROP_PA = f32(400.0)
SYNTHETIC_DT = 50
A, B, C, G = (FP.POLICY_STRICT_SWITCH_VETO, FP.POLICY_SENSOR_OVERRIDE, FP.POLICY_VOTE_2_OF_3,
              FP.POLICY_DELAYED_FALLBACK)


class CollectSink:
    def __init__(self):
        self.events = []

    def on_event(self, e):
        self.events.append(e)

    def count(self, t):
        return sum(1 for e in self.events if e.type == t)

    def clear(self):
        self.events = []


def ev(t, now, detail=0):
    return T.Event(t, now, detail)


class FsmRig:
    def __init__(self, test):
        self.test = test
        self.params = synthetic_flight_params(A)
        self.store = MockPersistentStore()
        self.rec = RecoveryManager(self.store)
        self.out = CollectSink()
        self.fsm = FlightStateManager(self.params, self.rec, self.out)

    def start(self, now=0):
        self.fsm.start(self.rec.restore_on_boot(), now)

    def drain_requests(self):
        n = 0
        r = self.fsm.pop_request()
        while r is not None:
            self.test.assertEqual(r, T.REQ_RELEASE_PARACHUTE)
            n += 1
            r = self.fsm.pop_request()
        return n


def drive_to(r, target):
    t = 0
    if target >= T.STATE_READY_ON_DRONE:
        t += 10
        r.fsm.on_event(ev(T.EV_SELF_CHECK_PASS, t))
    if target >= T.STATE_ASCENT:
        t += 10
        r.fsm.on_event(ev(T.EV_ASCENT_DETECTED, t))
    if target >= T.STATE_RELEASE_DETECTED:
        t += 10
        r.fsm.on_event(ev(T.EV_RELEASE_CANDIDATE, t))
    if target >= T.STATE_PARACHUTE_DEPLOY:
        t += 10
        r.fsm.on_event(ev(T.EV_RELEASE_CONFIRMED, t, 1))


def vf(now, sw_open, amag_g, pressure_pa, imu_ok=True, baro_ok=True):
    f = T.SensorFrame()
    f.baro.valid, f.baro.t_ms, f.baro.pressure_pa = baro_ok, now, f32(pressure_pa)
    f.imu.valid, f.imu.t_ms, f.imu.az_g = imu_ok, now, f32(amag_g)
    f.switches.valid = True
    f.switches.raw = [sw_open, sw_open]  # SYNTHETIC wiring: open = HIGH
    v = ValidatedFrame(now, f)
    v.baro_ok, v.imu_ok, v.power_ok, v.switches_ok = baro_ok, imu_ok, True, True
    return v


def good_frame(now):
    f = T.SensorFrame()
    f.baro.valid, f.baro.t_ms, f.baro.pressure_pa, f.baro.temp_c = True, now, SYNTHETIC_P_PA, f32(20.0)
    f.baro.comm_ok = f.baro.data_ready = True
    f.imu.valid, f.imu.t_ms, f.imu.az_g = True, now, 1.0
    f.imu.comm_ok = f.imu.data_ready = True
    f.power.valid, f.power.t_ms, f.power.bus_v, f.power.current_ma = True, now, f32(3.8), f32(100.0)
    f.power.comm_ok = f.power.data_ready = True
    f.switches.valid, f.switches.t_ms = True, now
    return f


def run_fsw(name, pol):
    sc = find_synthetic_scenario(name)
    hook = FlightSoftwareHook(synthetic_flight_params(pol))  # as C++: no store faults in this suite
    log = MemoryLogSink()
    run(sc, log, hook)
    return hook.stats, log


def truth_mounted_at_request(log):
    for l in log.lines:
        if l and l[0] != "#" and "REQUEST:" in l:
            return 1 if l.split(",")[6] == "1" else 0
    return -1


class StateMachine(unittest.TestCase):
    def test_fsm_permitted_transitions_are_the_slide19_chain_plus_two_flagged_landings(self):
        permitted = 0
        for f in range(1, 9):
            for t in range(1, 9):
                ok = is_permitted(f, t)
                self.assertEqual(ok, t == f + 1 or (t == 8 and f in (5, 6)), (f, t))
                permitted += ok
        self.assertEqual(permitted, 9)
        self.assertFalse(is_permitted(T.STATE_LANDED, T.STATE_POWER_ON_SELF_CHECK))
        self.assertFalse(is_permitted(0, T.STATE_POWER_ON_SELF_CHECK))

    def test_fsm_nominal_event_sequence_reaches_landed_with_one_request(self):
        r = FsmRig(self)
        r.start()
        self.assertEqual(r.fsm.state(), T.STATE_POWER_ON_SELF_CHECK)
        r.fsm.on_event(ev(T.EV_SELF_CHECK_PASS, 100))
        r.fsm.on_event(ev(T.EV_ASCENT_DETECTED, 200))
        r.fsm.on_event(ev(T.EV_RELEASE_CANDIDATE, 300))
        self.assertEqual(r.fsm.state(), T.STATE_RELEASE_DETECTED)
        r.fsm.on_event(ev(T.EV_RELEASE_CONFIRMED, 350, T.BASIS_SWITCH_AND_FREEFALL))
        self.assertEqual(r.fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        r.fsm.tick(600)
        self.assertEqual(r.drain_requests(), 0)
        r.fsm.tick(650)
        self.assertEqual(r.drain_requests(), 1)
        r.fsm.on_event(ev(T.EV_CHUTE_OPEN_DETECTED, 900))
        self.assertEqual(r.fsm.state(), T.STATE_PANEL_DEPLOY)
        self.assertEqual(r.fsm.chute_status(), T.CHUTE_OPENING_SENSED)
        for t in range(900, 60000, 1000):
            r.fsm.tick(t)
        self.assertEqual(r.fsm.state(), T.STATE_PANEL_DEPLOY)
        self.assertEqual(r.fsm.panel_status(), T.PANEL_UNKNOWN_NO_SENSOR)
        r.fsm.on_event(ev(T.EV_DESCENT_CONFIRMED, 60000))
        self.assertEqual(r.fsm.state(), T.STATE_DESCENT)
        r.fsm.on_event(ev(T.EV_TOUCHDOWN_DETECTED, 65000))
        self.assertEqual(r.fsm.state(), T.STATE_LANDED)
        self.assertEqual(r.out.count(T.EV_TRANSITION_REJECTED), 0)
        self.assertEqual(r.out.count(T.EV_STATE_CHANGED), 7)
        self.assertEqual(r.fsm.requests_emitted(), 1)

    def test_fsm_confirm_from_ascent_takes_two_legal_steps(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_ASCENT)
        r.fsm.on_event(ev(T.EV_RELEASE_CONFIRMED, 500, T.BASIS_SENSORS_ONLY_POLICY))
        self.assertEqual(r.fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(r.out.count(T.EV_STATE_CHANGED), 4)

    def test_fsm_rejects_events_in_wrong_state_and_does_not_move(self):
        r = FsmRig(self)
        r.start()
        for t, e in ((10, T.EV_ASCENT_DETECTED), (20, T.EV_TOUCHDOWN_DETECTED), (30, T.EV_RELEASE_CANDIDATE),
                     (40, T.EV_RELEASE_CONFIRMED)):
            r.fsm.on_event(ev(e, t))
        self.assertEqual(r.fsm.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertEqual(r.out.count(T.EV_TRANSITION_REJECTED), 4)
        self.assertEqual(r.fsm.requests_emitted(), 0)
        l = FsmRig(self)
        l.start()
        drive_to(l, T.STATE_PARACHUTE_DEPLOY)
        l.fsm.tick(10000)
        l.fsm.on_event(ev(T.EV_CHUTE_OPEN_DETECTED, 10001))
        l.fsm.tick(20000)
        l.fsm.on_event(ev(T.EV_TOUCHDOWN_DETECTED, 20001))
        self.assertEqual(l.fsm.state(), T.STATE_LANDED)
        l.out.clear()
        l.fsm.on_event(ev(T.EV_SELF_CHECK_PASS, 20002))
        l.fsm.on_event(ev(T.EV_TOUCHDOWN_DETECTED, 20003))
        self.assertEqual(l.fsm.state(), T.STATE_LANDED)
        self.assertEqual(l.out.count(T.EV_TRANSITION_REJECTED), 2)

    def test_fsm_chute_open_before_request_is_rejected(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        r.fsm.on_event(ev(T.EV_CHUTE_OPEN_DETECTED, 45))
        self.assertEqual(r.fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(r.out.count(T.EV_TRANSITION_REJECTED), 1)

    def test_fsm_duplicate_release_events_and_ticks_give_exactly_one_request(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        for i in range(5):
            r.fsm.on_event(ev(T.EV_RELEASE_CONFIRMED, 50 + i, 1))
            r.fsm.on_event(ev(T.EV_RELEASE_CANDIDATE, 50 + i))
        total = 0
        for t in range(100, 2900, SYNTHETIC_DT):
            r.fsm.tick(t)
            total += r.drain_requests()
        self.assertEqual(total, 1)
        self.assertEqual(r.fsm.requests_emitted(), 1)
        self.assertTrue(r.fsm.chute_requested())

    def test_fsm_degraded_release_events_raise_flag_without_transition(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_ASCENT)
        r.fsm.on_event(ev(T.EV_RELEASE_SENSORS_ONLY, 100))
        self.assertEqual(r.fsm.state(), T.STATE_ASCENT)
        self.assertTrue(r.fsm.fault_mask() & T.FAULT_RELEASE_DEGRADED)

    def test_fsm_chute_timeout_is_an_alarm_never_a_transition(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        r.fsm.tick(400)
        self.assertEqual(r.drain_requests(), 1)
        self.assertEqual(r.fsm.chute_status(), T.CHUTE_REQUESTED_AWAITING_OPENING)
        r.fsm.tick(3399)
        self.assertEqual(r.out.count(T.EV_CHUTE_OPEN_NOT_CONFIRMED), 0)
        for t in range(3400, 600000, 1000):
            r.fsm.tick(t)
        self.assertEqual(r.fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(r.fsm.chute_status(), T.CHUTE_OPENING_NOT_SENSED_TIMEOUT)
        self.assertEqual(r.out.count(T.EV_CHUTE_OPEN_NOT_CONFIRMED), 1)
        self.assertTrue(r.fsm.fault_mask() & T.FAULT_CHUTE_OPEN_NOT_SENSED)
        self.assertEqual(r.out.count(T.EV_STATE_CHANGED), 4)
        r.fsm.on_event(ev(T.EV_TOUCHDOWN_DETECTED, 600001))
        self.assertEqual(r.fsm.state(), T.STATE_LANDED)
        self.assertEqual(r.fsm.chute_status(), T.CHUTE_OPENING_NOT_SENSED_TIMEOUT)

    def test_fsm_late_sensed_opening_after_alarm_still_advances(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        r.fsm.tick(400)
        r.fsm.tick(5000)
        r.fsm.on_event(ev(T.EV_CHUTE_OPEN_DETECTED, 5100))
        self.assertEqual(r.fsm.state(), T.STATE_PANEL_DEPLOY)
        self.assertEqual(r.fsm.chute_status(), T.CHUTE_OPENING_SENSED)

    def test_fsm_descent_confirmed_outside_panel_deploy_is_rejected(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        r.fsm.on_event(ev(T.EV_DESCENT_CONFIRMED, 100))
        self.assertEqual(r.fsm.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(r.out.count(T.EV_TRANSITION_REJECTED), 1)

    def test_fsm_incomplete_params_never_request(self):
        store = MockPersistentStore()
        rec = RecoveryManager(store)
        fsm = FlightStateManager(FP.FlightParams(), rec, CollectSink())
        fsm.start(rec.restore_on_boot(), 0)
        fsm.on_event(ev(T.EV_SELF_CHECK_PASS, 1))
        fsm.on_event(ev(T.EV_ASCENT_DETECTED, 2))
        fsm.on_event(ev(T.EV_RELEASE_CONFIRMED, 3, 1))
        for t in range(0, 100000, 1000):
            fsm.tick(t)
        self.assertIsNone(fsm.pop_request())
        self.assertEqual(fsm.requests_emitted(), 0)


class Persistence(unittest.TestCase):
    def test_fsm_persists_every_transition_and_flag(self):
        r = FsmRig(self)
        r.start()
        before = r.store.writes
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        rec = r.store.record()
        self.assertEqual(rec.last_state, T.STATE_PARACHUTE_DEPLOY)
        self.assertTrue(rec.one_shot_flags & T.ONESHOT_RELEASE_CONFIRMED)
        self.assertGreaterEqual(r.store.writes - before, 5)
        self.assertEqual(rec.crc, recovery_crc(rec))

    def test_recovery_without_record_starts_self_check(self):
        store = MockPersistentStore()
        rr = RecoveryManager(store).restore_on_boot()
        self.assertFalse(rr.had_record or rr.corrupt or rr.resumed)
        self.assertEqual((rr.state, rr.boot_count), (T.STATE_POWER_ON_SELF_CHECK, 1))
        self.assertTrue(store.has())

    def test_recovery_corrupt_record_restarts_safe_and_flags_fault(self):
        a = FsmRig(self)
        a.start()
        drive_to(a, T.STATE_PARACHUTE_DEPLOY)
        a.store.corrupt()
        rec = RecoveryManager(a.store)
        fsm = FlightStateManager(a.params, rec, CollectSink())
        rr = rec.restore_on_boot()
        self.assertTrue(rr.corrupt and not rr.resumed)
        fsm.start(rr, 0)
        self.assertEqual(fsm.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertTrue(fsm.fault_mask() & T.FAULT_RECOVERY_RECORD_CORRUPT)

    def test_recovery_ground_states_restart_at_self_check(self):
        a = FsmRig(self)
        a.start()
        drive_to(a, T.STATE_READY_ON_DRONE)
        rr = RecoveryManager(a.store).restore_on_boot()
        self.assertTrue(not rr.resumed and rr.state == T.STATE_POWER_ON_SELF_CHECK and rr.boot_count == 2)

    def test_recovery_after_request_resumes_without_second_request(self):
        a = FsmRig(self)
        a.start()
        drive_to(a, T.STATE_PARACHUTE_DEPLOY)
        a.fsm.tick(1000)
        self.assertEqual(a.drain_requests(), 1)
        rec = RecoveryManager(a.store)
        out = CollectSink()
        fsm = FlightStateManager(a.params, rec, out)
        rr = rec.restore_on_boot()
        self.assertTrue(rr.resumed and rr.state == T.STATE_PARACHUTE_DEPLOY and rr.boot_count == 2)
        fsm.start(rr, 0)
        self.assertEqual(out.count(T.EV_RESET_RECOVERED), 1)
        self.assertEqual(out.count(T.EV_REQUEST_SUPPRESSED), 1)
        for t in range(0, 2000, SYNTHETIC_DT):
            fsm.tick(t)
        self.assertIsNone(fsm.pop_request())
        self.assertEqual(fsm.requests_emitted(), 0)

    def test_recovery_before_request_requests_once_after_restarted_separation_timer(self):
        a = FsmRig(self)
        a.start()
        drive_to(a, T.STATE_PARACHUTE_DEPLOY)
        rec = RecoveryManager(a.store)
        fsm = FlightStateManager(a.params, rec, CollectSink())
        fsm.start(rec.restore_on_boot(), 0)
        fsm.tick(299)
        self.assertIsNone(fsm.pop_request())
        fsm.tick(300)
        self.assertIsNotNone(fsm.pop_request())
        fsm.tick(400)
        self.assertIsNone(fsm.pop_request())

    def test_persist_failure_raises_fault_and_still_requests_only_once(self):
        r = FsmRig(self)
        r.start()
        drive_to(r, T.STATE_PARACHUTE_DEPLOY)
        r.store.fail_writes = True
        total = 0
        for t in range(0, 2000, SYNTHETIC_DT):
            r.fsm.tick(t)
            total += r.drain_requests()
        self.assertEqual(total, 1)
        self.assertTrue(r.fsm.fault_mask() & T.FAULT_PERSIST_WRITE)


class Validator(unittest.TestCase):
    def test_validator_accepts_good_frames_and_rejects_each_bad_kind(self):
        v = SensorValidator(synthetic_flight_params(C))
        f = v.validate(good_frame(0), 0)
        self.assertTrue(f.baro_ok and f.imu_ok and f.power_ok and f.switches_ok and v.fault_mask() == 0)
        s = good_frame(50)
        s.baro.valid = False
        s.imu.ax_g = float("nan")
        s.power.current_ma = f32(99999.0)
        s.switches.valid = False
        f = v.validate(s, 50)
        self.assertEqual((f.baro_reject, f.imu_reject), (REJECT_INVALID_FLAG, REJECT_NON_FINITE))
        self.assertEqual((f.power_reject, f.switches_reject), (REJECT_RANGE, REJECT_INVALID_FLAG))
        self.assertEqual(v.newly_faulted(), T.FAULT_BARO_INVALID | T.FAULT_IMU_INVALID | T.FAULT_POWER_INVALID |
                         T.FAULT_SWITCH_INVALID)
        s = good_frame(100)
        s.imu.az_g = 0.0
        s.baro.pressure_pa = s.baro.temp_c = 0.0
        f = v.validate(s, 100)
        self.assertEqual((f.imu_reject, f.baro_reject), (REJECT_ZERO_READ, REJECT_ZERO_READ))
        self.assertEqual(v.newly_recovered(), T.FAULT_POWER_INVALID | T.FAULT_SWITCH_INVALID)
        s = good_frame(150)
        s.imu.az_g = f32(17.0)
        s.baro.pressure_pa = f32(5000.0)
        f = v.validate(s, 150)
        self.assertEqual((f.imu_reject, f.baro_reject), (REJECT_RANGE, REJECT_RANGE))
        f = v.validate(good_frame(200), 200)
        self.assertTrue(f.baro_ok and f.imu_ok and f.power_ok and f.switches_ok)
        self.assertEqual(v.newly_recovered(), T.FAULT_BARO_INVALID | T.FAULT_IMU_INVALID)
        self.assertEqual(v.fault_mask(), 0)

    def test_validator_detects_stale_by_repeat_and_by_age(self):
        v = SensorValidator(synthetic_flight_params(C))
        v.validate(good_frame(100), 100)
        rep = good_frame(150)
        rep.imu.t_ms = 100
        f = v.validate(rep, 150)
        self.assertTrue(f.imu_reject == REJECT_STALE_REPEAT and f.baro_ok)
        old = good_frame(1000)
        old.baro.t_ms = 700
        self.assertEqual(v.validate(old, 1000).baro_reject, REJECT_STALE_AGE)

    def test_validator_saturation_is_flagged_but_not_invalid(self):
        v = SensorValidator(synthetic_flight_params(C))
        s = good_frame(0)
        s.imu.az_g = 16.0
        s.imu.saturated = True
        self.assertTrue(v.validate(s, 0).imu_ok)
        self.assertTrue(v.fault_mask() & T.FAULT_IMU_SATURATED)


def feed_sensors_only(d, frm, to, imu_glitch_at_start):
    t = frm
    while t <= to:
        p = f32(SYNTHETIC_P_PA + f32(f32(SYNTHETIC_DROP_PA * f32(t - frm)) / 500.0))
        imu_ok = not (imu_glitch_at_start and t == frm + 3 * SYNTHETIC_DT)
        d.update(vf(t, False, 0.05, p, imu_ok), T.STATE_ASCENT, False)
        t += SYNTHETIC_DT


class Detector(unittest.TestCase):
    def test_detector_with_incomplete_params_emits_only_selfcheck_fail(self):
        out = CollectSink()
        d = EventDetector(FP.FlightParams(), out)
        for t in range(0, 2000, SYNTHETIC_DT):
            d.update(vf(t, True, 0.0, SYNTHETIC_P_PA - t), T.STATE_ASCENT, False)
        self.assertEqual(len(out.events), 1)
        self.assertEqual((out.events[0].type, out.events[0].detail), (T.EV_SELF_CHECK_FAIL, T.FAULT_PARAMS_INCOMPLETE))

    def test_detector_self_check_needs_consecutive_good_frames_with_mount_closed(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(A), out)
        t = 0
        for _ in range(20):
            d.update(vf(t, True, 1.0, SYNTHETIC_P_PA), T.STATE_POWER_ON_SELF_CHECK, False)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_SELF_CHECK_PASS), 0)
        for _ in range(20):
            d.update(vf(t, False, 1.0, SYNTHETIC_P_PA), T.STATE_POWER_ON_SELF_CHECK, False)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_SELF_CHECK_PASS), 1)
        self.assertTrue(d.has_ground_reference() and abs(d.ground_pressure_pa() - SYNTHETIC_P_PA) < 0.01)

    def test_detector_switch_debounce_and_not_armed_before_ascent(self):
        p = synthetic_flight_params(A)
        out = CollectSink()
        d = EventDetector(p, out)
        for t, o in ((0, False), (100, False), (150, True), (300, True)):
            d.update(vf(t, o, 1.0, SYNTHETIC_P_PA), T.STATE_READY_ON_DRONE, False)
        self.assertTrue(d.mount_open())
        self.assertEqual(out.count(T.EV_RELEASE_CANDIDATE), 0)
        out2 = CollectSink()
        d2 = EventDetector(p, out2)
        for t, o in ((0, False), (100, False), (150, True), (200, False), (250, True)):
            d2.update(vf(t, o, 1.0, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        self.assertFalse(d2.mount_open())
        self.assertEqual(out2.count(T.EV_RELEASE_CANDIDATE), 0)
        d2.update(vf(350, True, 1.0, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        self.assertTrue(d2.mount_open())
        self.assertEqual(out2.count(T.EV_RELEASE_CANDIDATE), 1)

    def test_detector_freefall_needs_duration_and_invalid_sample_resets_it(self):
        d = EventDetector(synthetic_flight_params(A), CollectSink())
        d.update(vf(0, False, 0.05, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        d.update(vf(100, False, 0.05, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        self.assertFalse(d.freefall())
        d.update(vf(150, False, 0.05, SYNTHETIC_P_PA, False), T.STATE_ASCENT, False)
        d.update(vf(200, False, 0.05, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        d.update(vf(300, False, 0.05, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        self.assertFalse(d.freefall())
        d.update(vf(350, False, 0.05, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        self.assertTrue(d.freefall())

    def test_detector_baro_descent_uses_window_and_valid_samples_only(self):
        d = EventDetector(synthetic_flight_params(A), CollectSink())
        hi = f32(SYNTHETIC_P_PA + SYNTHETIC_DROP_PA)
        d.update(vf(0, False, 1.0, SYNTHETIC_P_PA), T.STATE_ASCENT, False)
        d.update(vf(400, False, 1.0, hi), T.STATE_ASCENT, False)
        self.assertFalse(d.baro_descent())
        d.update(vf(500, False, 1.0, hi), T.STATE_ASCENT, False)
        self.assertTrue(d.baro_descent())
        d.update(vf(550, False, 1.0, hi, True, False), T.STATE_ASCENT, False)
        self.assertFalse(d.baro_descent())

    def test_detector_policy_A_strict_never_confirms_sensors_only(self):
        out = CollectSink()
        feed_sensors_only(EventDetector(synthetic_flight_params(A), out), 0, 3000, False)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 0)
        self.assertEqual(out.count(T.EV_RELEASE_SENSORS_ONLY), 1)

    def test_detector_policy_B_override_confirms_only_without_recent_rejects(self):
        out = CollectSink()
        feed_sensors_only(EventDetector(synthetic_flight_params(B), out), 0, 3000, False)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 1)
        self.assertEqual(out.events[-1].detail, T.BASIS_SENSORS_ONLY_POLICY)
        out = CollectSink()
        feed_sensors_only(EventDetector(synthetic_flight_params(B), out), 0, 800, True)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 0)
        self.assertEqual(out.count(T.EV_RELEASE_SENSORS_ONLY), 1)

    def test_detector_policy_C_vote_confirms_on_two_of_three(self):
        out = CollectSink()
        feed_sensors_only(EventDetector(synthetic_flight_params(C), out), 0, 3000, False)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 1)
        self.assertEqual(out.count(T.EV_RELEASE_SENSORS_ONLY), 0)

    def test_detector_policy_G_fallback_confirms_after_delay(self):
        out = CollectSink()
        feed_sensors_only(EventDetector(synthetic_flight_params(G), out), 0, 3000, False)
        self.assertEqual(out.count(T.EV_RELEASE_SENSORS_ONLY), 1)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 1)
        t_so = [e.t_ms for e in out.events if e.type == T.EV_RELEASE_SENSORS_ONLY][-1]
        t_conf = [e.t_ms for e in out.events if e.type == T.EV_RELEASE_CONFIRMED][-1]
        self.assertGreaterEqual(t_conf - t_so, 300)

    def test_detector_release_latches_once(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(C), out)
        feed_sensors_only(d, 0, 6000, False)
        self.assertEqual(out.count(T.EV_RELEASE_CONFIRMED), 1)
        self.assertTrue(d.release_latched())


class Composition(unittest.TestCase):
    def test_flight_software_with_incomplete_params_stays_in_self_check(self):
        fs = FlightSoftware(FP.FlightParams(), MockPersistentStore())
        fs.boot(BootReport(True, True, True), 0)
        for t in range(0, 5000, SYNTHETIC_DT):
            fs.tick(good_frame(t), t)
        self.assertEqual(fs.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertTrue(fs.fault_mask() & T.FAULT_PARAMS_INCOMPLETE)
        self.assertEqual(fs.requests_emitted(), 0)


class Matrix(unittest.TestCase):
    def test_every_scenario_every_policy_is_safe_structurally(self):
        scs = all_synthetic_scenarios()
        self.assertEqual(len(scs), 13)
        for sc in scs:
            for pol in CANDIDATE_POLICIES:
                with self.subTest(scenario=sc.name, policy=pol):
                    st, log = run_fsw(sc.name, pol)
                    self.assertLessEqual(st.requests, 1)
                    self.assertEqual(st.rejected_transitions, 0)
                    for i in range(1, len(st.states_entered)):
                        self.assertEqual(st.states_entered[i], st.states_entered[i - 1] + 1)
                    self.assertTrue(any("ACTUATOR LOGIC DISABLED" in l for l in log.lines))
                    for l in log.lines:
                        if "REQUEST:" in l:
                            self.assertIn("NOT_EXECUTED", l)

    def test_matrix_is_deterministic(self):
        self.assertEqual(run_fsw("reset_mid_flight", C)[1].lines, run_fsw("reset_mid_flight", C)[1].lines)

    def test_healthy_switch_scenarios_land_with_one_request_under_every_policy(self):
        for n in ("nominal", "baro_dropout", "stale_imu", "invalid_values", "switch_bounce", "reset_mid_flight"):
            for pol in CANDIDATE_POLICIES:
                with self.subTest(scenario=n, policy=pol):
                    st, log = run_fsw(n, pol)
                    self.assertEqual((st.final_state, st.requests, st.sensors_only_events), (T.STATE_LANDED, 1, 0))
                    self.assertEqual(truth_mounted_at_request(log), 0)

    def test_stale_imu_release_is_confirmed_by_baro_path(self):
        self.assertEqual(run_fsw("stale_imu", A)[0].last_release_basis, T.BASIS_SWITCH_AND_BARO)

    def test_noisy_scenario_finding_descent_and_landing_not_confirmed_with_synthetic_tolerances(self):
        st, _ = run_fsw("noisy", A)  # SIMULATED finding, not a pass criterion
        self.assertEqual((st.requests, st.final_state, st.final_chute), (1, T.STATE_PANEL_DEPLOY, T.CHUTE_OPENING_SENSED))

    def test_od060_S4_stuck_switch_really_released_per_policy(self):
        for pol in CANDIDATE_POLICIES:
            st, log = run_fsw("stuck_switch_released", pol)
            if pol == A:
                self.assertEqual((st.requests, st.final_state, st.sensors_only_events), (0, T.STATE_ASCENT, 1))
                self.assertTrue(st.final_faults & T.FAULT_RELEASE_DEGRADED)
            else:
                self.assertEqual((st.requests, st.last_release_basis), (1, T.BASIS_SENSORS_ONLY_POLICY))
                self.assertEqual(truth_mounted_at_request(log), 0)

    def test_od060_S4b_mounted_with_zeroed_imu_no_policy_requests(self):
        for pol in CANDIDATE_POLICIES:
            st, log = run_fsw("mounted_imu_zero", pol)
            self.assertEqual((st.requests, st.final_state), (0, T.STATE_ASCENT))
            self.assertTrue(any("SensorFault:0x2" in l for l in log.lines))

    def test_od060_S4c_mounted_drone_falling_hazard_under_sensor_policies(self):
        for pol in CANDIDATE_POLICIES:
            st, log = run_fsw("mounted_drone_falling", pol)
            if pol == A:
                self.assertEqual(st.requests, 0)
            else:
                self.assertEqual(st.requests, 1)  # requested WHILE STILL MOUNTED (hazard, OD-060)
                self.assertEqual(truth_mounted_at_request(log), 1)
                self.assertEqual((st.final_state, st.final_chute), (T.STATE_PARACHUTE_DEPLOY,
                                                                    T.CHUTE_OPENING_NOT_SENSED_TIMEOUT))
                self.assertEqual(st.chute_not_confirmed_alarms, 1)
            self.assertNotEqual(st.final_state, T.STATE_LANDED)

    def test_reset_mid_flight_recovers_twice_and_never_repeats_request(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("reset_mid_flight", pol)
            self.assertEqual((st.resets_recovered, st.suppressed_requests, st.requests, st.final_state),
                             (2, 2, 1, T.STATE_LANDED))

    def test_imu_not_detected_blocks_self_check_and_requests(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("imu_not_detected", pol)
            self.assertEqual((st.final_state, st.requests), (T.STATE_POWER_ON_SELF_CHECK, 0))
            self.assertTrue(st.final_faults & T.FAULT_SELF_CHECK)


if __name__ == "__main__":
    unittest.main()
