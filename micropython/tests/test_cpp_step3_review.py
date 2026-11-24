# One-to-one port of firmware/test/test_step3_review.cpp (20 cases): landing
# confirmation, timeouts, IMU health evidence, persistence-failure policies.
# [SIMULATED] SYNTHETIC_* values are test-only. Requests are counted, never executed.
import unittest

from cansat.config import flight_params as FP
from cansat.core import types as T
from cansat.core.event_detector import EventDetector
from cansat.core.flight_software import BootReport, FlightSoftware
from cansat.core.flight_state_manager import FlightStateManager, is_permitted
from cansat.core.num import f32
from cansat.core.recovery_manager import RECOVERY_MAGIC, RECOVERY_VERSION, RecoveryManager, recovery_crc
from cansat.core.sensor_validator import (REJECT_COMM, REJECT_INVALID_FLAG, REJECT_NOT_FRESH, REJECT_STUCK,
                                          SensorValidator, ValidatedFrame)
from cansat.mock import fault_injector as FI
from cansat.mock.memory_log import MemoryLogSink
from cansat.mock.persistent_store import MockPersistentStore
from cansat.mock.sensors import MockImu, SensorNoise
from cansat.mock.truth import TruthSource, TruthState
from cansat.mock.virtual_clock import VirtualClock
from cansat.sim.flight_profile import pressure_at_altitude
from cansat.sim.fsw_hook import FlightSoftwareHook
from cansat.sim.runner import run
from cansat.sim.scenarios import find_synthetic_scenario
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params

SYNTHETIC_P0 = f32(100000.0)
SYNTHETIC_HOVER_M = f32(64.0)
SYNTHETIC_NEAR_GROUND_M = f32(0.5)
SYNTHETIC_DT = 50
VETO = FP.POLICY_STRICT_SWITCH_VETO


class CollectSink:
    def __init__(self):
        self.events = []

    def on_event(self, e):
        self.events.append(e)

    def count(self, t):
        return sum(1 for e in self.events if e.type == t)

    def first(self, t):
        for e in self.events:
            if e.type == t:
                return e
        return None


def vf(now, sw_open, amag_g, pressure_pa, imu_ok=True):
    f = T.SensorFrame()
    f.baro.valid, f.baro.pressure_pa = True, f32(pressure_pa)
    f.imu.valid, f.imu.az_g = imu_ok, f32(amag_g)
    f.switches.valid = True
    f.switches.raw = [sw_open, sw_open]  # SYNTHETIC wiring: open = HIGH
    v = ValidatedFrame(now, f)
    v.baro_ok, v.imu_ok, v.power_ok, v.switches_ok = True, imu_ok, True, True
    return v


def p_at(alt_m):
    return pressure_at_altitude(SYNTHETIC_P0, alt_m)


def pass_self_check(d):
    t = 0
    for _ in range(20):
        d.update(vf(t, False, 1.0, SYNTHETIC_P0), T.STATE_POWER_ON_SELF_CHECK, False)
        t += SYNTHETIC_DT
    return t


def jitter_frame(now, sw_closed_level=False):
    f = T.SensorFrame()
    j = f32(f32(now % 7) * f32(0.001))
    f.baro.valid = f.baro.comm_ok = f.baro.data_ready = True
    f.baro.t_ms, f.baro.pressure_pa, f.baro.temp_c = now, f32(SYNTHETIC_P0 + j), f32(20.0)
    f.imu.valid = f.imu.comm_ok = f.imu.data_ready = True
    f.imu.t_ms, f.imu.az_g = now, f32(1.0 + j)
    f.power.valid = f.power.comm_ok = f.power.data_ready = True
    f.power.t_ms, f.power.bus_v, f.power.current_ma = now, f32(3.8), f32(100.0)
    f.switches.valid, f.switches.t_ms = True, now
    f.switches.raw = [sw_closed_level, sw_closed_level]
    return f


def set_t(f, t):
    f.imu.t_ms = f.baro.t_ms = f.power.t_ms = f.switches.t_ms = t


def run_fsw(name, pol):
    hook = FlightSoftwareHook(synthetic_flight_params(pol))
    log = MemoryLogSink()
    run(find_synthetic_scenario(name), log, hook)
    return hook.stats, log


def params_with_persist_policy(pf):
    p = synthetic_flight_params(VETO)
    p.interlock.persist_failure_policy.set(pf)
    return p


def to_parachute_deploy(fsm):
    t = 0
    for s in (T.EV_SELF_CHECK_PASS, T.EV_ASCENT_DETECTED, T.EV_RELEASE_CANDIDATE, T.EV_RELEASE_CONFIRMED):
        t += 10
        fsm.on_event(T.Event(s, t, 1))


def drain(fsm):
    n = 0
    while fsm.pop_request() is not None:
        n += 1
    return n


def new_fsm(p, store):
    rm = RecoveryManager(store)
    out = CollectSink()
    fsm = FlightStateManager(p, rm, out)
    fsm.start(rm.restore_on_boot(), 0)
    return fsm, out


class Landing(unittest.TestCase):
    def test_touchdown_never_confirmed_without_ground_reference(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        for t in range(0, 60000, SYNTHETIC_DT):
            d.update(vf(t, True, 1.0, SYNTHETIC_P0), T.STATE_DESCENT, True)
        self.assertEqual(out.count(T.EV_TOUCHDOWN_DETECTED), 0)
        self.assertEqual(out.count(T.EV_SENSOR_FAULT), 1)
        self.assertTrue(d.fault_mask() & T.FAULT_LANDING_UNCONFIRMABLE)

    def test_stable_hover_at_altitude_is_never_touchdown(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        t = pass_self_check(d)
        for st in (T.STATE_PARACHUTE_DEPLOY, T.STATE_PANEL_DEPLOY, T.STATE_DESCENT):
            for _ in range(1200):
                d.update(vf(t, True, 1.0, p_at(SYNTHETIC_HOVER_M)), st, True)
                t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_TOUCHDOWN_DETECTED), 0)

    def test_touchdown_near_ground_only_after_full_window(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        t = pass_self_check(d)
        start = t
        while t < start + 2950:
            d.update(vf(t, True, 1.0, p_at(SYNTHETIC_NEAR_GROUND_M)), T.STATE_DESCENT, True)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_TOUCHDOWN_DETECTED), 0)
        while t <= start + 3100:
            d.update(vf(t, True, 1.0, p_at(SYNTHETIC_NEAR_GROUND_M)), T.STATE_DESCENT, True)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_TOUCHDOWN_DETECTED), 1)
        self.assertEqual(out.first(T.EV_TOUCHDOWN_DETECTED).detail, 0)

    def test_touchdown_window_restarts_on_invalid_imu(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        t = pass_self_check(d)
        start = t
        while t < start + 2000:
            d.update(vf(t, True, 1.0, p_at(0.0)), T.STATE_DESCENT, True)
            t += SYNTHETIC_DT
        d.update(vf(t, True, 1.0, p_at(0.0), False), T.STATE_DESCENT, True)
        t += SYNTHETIC_DT
        restart = t
        while t < restart + 2950:
            d.update(vf(t, True, 1.0, p_at(0.0)), T.STATE_DESCENT, True)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_TOUCHDOWN_DETECTED), 0)

    def test_touchdown_with_mount_reading_closed_is_flagged(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        t = pass_self_check(d)
        for _ in range(100):
            d.update(vf(t, False, 1.0, p_at(0.0)), T.STATE_DESCENT, True)
            t += SYNTHETIC_DT
        e = out.first(T.EV_TOUCHDOWN_DETECTED)
        self.assertTrue(e is not None and e.detail & T.TOUCHDOWN_MOUNT_READS_CLOSED)
        self.assertTrue(d.fault_mask() & T.FAULT_LANDED_MOUNT_CLOSED)

    def test_descent_confirmation_needs_sustained_baro_descent(self):
        out = CollectSink()
        d = EventDetector(synthetic_flight_params(VETO), out)
        t = pass_self_check(d)
        alt = f32(80.0)
        for _ in range(1200):
            d.update(vf(t, True, 1.0, p_at(alt)), T.STATE_PANEL_DEPLOY, True)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_DESCENT_CONFIRMED), 0)
        start = t
        while t < start + 3000:
            alt = f32(alt - f32(0.15))
            d.update(vf(t, True, 1.0, p_at(alt)), T.STATE_PANEL_DEPLOY, True)
            t += SYNTHETIC_DT
        self.assertEqual(out.count(T.EV_DESCENT_CONFIRMED), 1)

    def test_scenario_mounted_drone_falling_never_lands_under_any_policy(self):
        for pol in CANDIDATE_POLICIES:
            st, log = run_fsw("mounted_drone_falling", pol)
            self.assertNotEqual(st.final_state, T.STATE_LANDED)
            self.assertFalse(any("TouchdownDetected" in l for l in log.lines))

    def test_scenario_nominal_lands_only_near_ground_and_after_descent(self):
        st, log = run_fsw("nominal", VETO)
        self.assertEqual(st.final_state, T.STATE_LANDED)
        seen = False
        for l in log.lines:
            if "TouchdownDetected" in l:
                seen = True
                self.assertLess(float(l.split(",")[4]), 1.0)
        self.assertTrue(seen)


class StatesAndTimeouts(unittest.TestCase):
    def test_abnormal_landing_paths_are_explicit_and_keep_status(self):
        self.assertTrue(is_permitted(T.STATE_PARACHUTE_DEPLOY, T.STATE_LANDED))
        self.assertTrue(is_permitted(T.STATE_PANEL_DEPLOY, T.STATE_LANDED))
        self.assertFalse(is_permitted(T.STATE_ASCENT, T.STATE_LANDED))
        self.assertFalse(is_permitted(T.STATE_RELEASE_DETECTED, T.STATE_LANDED))
        self.assertFalse(is_permitted(T.STATE_PARACHUTE_DEPLOY, T.STATE_DESCENT))

    def test_no_state_is_left_by_time_alone(self):
        for code in range(1, 9):
            store = MockPersistentStore()
            rec = T.RecoveryRecord()
            rec.magic, rec.version, rec.boot_count, rec.last_state = RECOVERY_MAGIC, RECOVERY_VERSION, 1, code
            rec.one_shot_flags = (T.ONESHOT_RELEASE_CONFIRMED | T.ONESHOT_CHUTE_REQUESTED) if code >= 5 else 0
            rec.ground_pressure_pa = SYNTHETIC_P0
            rec.crc = recovery_crc(rec)
            store.save(rec)
            fsm, out = new_fsm(synthetic_flight_params(VETO), store)
            before = fsm.state()
            for t in range(0, 3600000, 1000):  # one simulated hour, no events
                fsm.tick(t)
            self.assertEqual(fsm.state(), before, code)
            self.assertEqual(out.count(T.EV_STATE_CHANGED), 0)


class ImuHealth(unittest.TestCase):
    def test_validator_rejects_comm_failure_and_not_ready(self):
        v = SensorValidator(synthetic_flight_params(VETO))
        f = jitter_frame(0)
        f.imu.comm_ok = f.imu.valid = False
        r = v.validate(f, 0)
        self.assertTrue(not r.imu_ok and r.imu_reject & REJECT_COMM and r.imu_reject & REJECT_INVALID_FLAG)
        f = jitter_frame(50)
        f.imu.data_ready = False
        r = v.validate(f, 50)
        self.assertTrue(not r.imu_ok and r.imu_reject == REJECT_NOT_FRESH)
        f = jitter_frame(100)
        f.baro.data_ready = False
        f.power.comm_ok = False
        r = v.validate(f, 100)
        self.assertTrue(r.imu_ok and r.baro_reject == REJECT_NOT_FRESH and r.power_reject & REJECT_COMM)

    def test_validator_detects_stuck_imu_output_after_n_identical_samples(self):
        v = SensorValidator(synthetic_flight_params(VETO))
        f = jitter_frame(0)
        for i in range(4):
            set_t(f, i * SYNTHETIC_DT)
            self.assertTrue(v.validate(f, i * SYNTHETIC_DT).imu_ok)
        set_t(f, 200)
        r = v.validate(f, 200)
        self.assertTrue(not r.imu_ok and r.imu_reject == REJECT_STUCK)
        g = jitter_frame(250)
        g.imu.az_g = f32(g.imu.az_g + f32(0.01))
        self.assertTrue(v.validate(g, 250).imu_ok)

    def test_validator_stuck_check_disabled_without_param(self):
        v = SensorValidator(FP.FlightParams())
        f = jitter_frame(0)
        for i in range(50):
            set_t(f, i * SYNTHETIC_DT)
            self.assertEqual(v.validate(f, i * SYNTHETIC_DT).imu_reject & REJECT_STUCK, 0)

    def test_mock_imu_new_fault_kinds(self):
        class Truth(TruthSource):
            az = 1.0

            def truth_at(self, t):
                s = TruthState()
                s.truth_ms = t
                s.accel_g[2] = f32(self.az)
                s.gyro_dps[0] = f32(0.3)
                return s

        c, truth, fi = VirtualClock(), Truth(), FI.FaultInjector()
        fi.add(FI.FaultWindow(FI.TARGET_IMU, FI.COMM_FAILURE, 100, 200))
        fi.add(FI.FaultWindow(FI.TARGET_IMU, FI.NOT_READY, 200, 300))
        fi.add(FI.FaultWindow(FI.TARGET_IMU, FI.STUCK_OUTPUT, 300, 400))
        imu = MockImu(c, truth, fi, SensorNoise(), 1)
        imu.begin()
        s = imu.read()
        self.assertTrue(s.valid and s.comm_ok and s.data_ready)
        truth.az = 0.05
        c.advance_to(150)
        s = imu.read()
        self.assertTrue(not s.valid and not s.comm_ok)
        c.advance_to(250)
        s = imu.read()
        self.assertTrue(s.valid and s.comm_ok and not s.data_ready and s.t_ms == 250 and s.az_g == 1.0)
        c.advance_to(350)
        s = imu.read()
        self.assertTrue(s.valid and s.data_ready and s.t_ms == 350 and s.az_g == 1.0)
        c.advance_to(400)
        self.assertEqual(imu.read().az_g, f32(0.05))

    def test_self_test_failed_blocks_self_check_and_not_run_is_flagged(self):
        p = synthetic_flight_params(VETO)
        fs = FlightSoftware(p, MockPersistentStore())
        fs.boot(BootReport(True, True, True, T.SELF_TEST_FAILED), 0)
        for t in range(0, 5000, SYNTHETIC_DT):
            fs.tick(jitter_frame(t), t)
        self.assertEqual(fs.state(), T.STATE_POWER_ON_SELF_CHECK)
        self.assertTrue(fs.fault_mask() & T.FAULT_IMU_SELF_TEST_FAILED)
        fs = FlightSoftware(p, MockPersistentStore())
        fs.boot(BootReport(True, True, True), 0)  # NotRun (default)
        for t in range(0, 5000, SYNTHETIC_DT):
            fs.tick(jitter_frame(t), t)
        self.assertEqual(fs.state(), T.STATE_READY_ON_DRONE)  # provisional: NotRun does not block
        self.assertTrue(fs.fault_mask() & T.FAULT_IMU_SELF_TEST_NOT_RUN)
        fs = FlightSoftware(p, MockPersistentStore())
        fs.boot(BootReport(True, True, True, T.SELF_TEST_PASSED), 0)
        self.assertEqual(fs.fault_mask() & (T.FAULT_IMU_SELF_TEST_NOT_RUN | T.FAULT_IMU_SELF_TEST_FAILED), 0)

    def test_scenario_imu_stuck_in_release_is_caught_and_baro_confirms(self):
        for pol in CANDIDATE_POLICIES:
            st, _ = run_fsw("imu_stuck_in_release", pol)
            self.assertEqual((st.final_state, st.requests, st.last_release_basis),
                             (T.STATE_LANDED, 1, T.BASIS_SWITCH_AND_BARO))

    def test_scenario_imu_comm_failure_in_descent_still_lands(self):
        st, log = run_fsw("imu_comm_failure_descent", VETO)
        self.assertEqual(st.final_state, T.STATE_LANDED)
        self.assertTrue(any("imu.comm_failure" in l for l in log.lines))


class PersistenceFailure(unittest.TestCase):
    def test_persist_failure_request_anyway_can_duplicate_after_reset(self):
        p = params_with_persist_policy(FP.PERSIST_REQUEST_ANYWAY)
        store = MockPersistentStore()
        fsm, _ = new_fsm(p, store)
        to_parachute_deploy(fsm)
        store.fail_writes = True
        total = 0
        for t in range(0, 1000, SYNTHETIC_DT):
            fsm.tick(t)
            total += drain(fsm)
        self.assertEqual(total, 1)
        self.assertTrue(fsm.fault_mask() & T.FAULT_PERSIST_WRITE)
        fsm, out = new_fsm(p, store)  # reset
        self.assertEqual(out.count(T.EV_REQUEST_SUPPRESSED), 0)
        for t in range(0, 1000, SYNTHETIC_DT):
            fsm.tick(t)
            total += drain(fsm)
        self.assertEqual(total, 2)  # SECOND request: the hazard RequestAnyway accepts

    def test_persist_failure_withhold_never_requests_while_storage_fails(self):
        p = params_with_persist_policy(FP.PERSIST_WITHHOLD_UNTIL_PERSISTED)
        store = MockPersistentStore()
        fsm, out = new_fsm(p, store)
        to_parachute_deploy(fsm)
        store.fail_writes = True
        total = 0
        for t in range(0, 30000, SYNTHETIC_DT):
            fsm.tick(t)
            total += drain(fsm)
        self.assertEqual(total, 0)
        self.assertEqual(out.count(T.EV_REQUEST_WITHHELD), 1)
        self.assertTrue(fsm.fault_mask() & T.FAULT_REQUEST_WITHHELD)
        self.assertEqual(fsm.chute_status(), T.CHUTE_NOT_REQUESTED)
        store.fail_writes = False
        for t in range(30000, 31000, SYNTHETIC_DT):
            fsm.tick(t)
            total += drain(fsm)
        self.assertEqual(total, 1)
        self.assertTrue(store.record().one_shot_flags & T.ONESHOT_CHUTE_REQUESTED)
        fsm2, _ = new_fsm(p, store)
        for t in range(0, 2000, SYNTHETIC_DT):
            fsm2.tick(t)
            total += drain(fsm2)
        self.assertEqual(total, 1)

    def test_persist_failure_policy_unset_means_params_incomplete_and_no_request(self):
        p = synthetic_flight_params(VETO)
        p.interlock.persist_failure_policy.clear()
        self.assertFalse(p.is_complete())
        fsm, _ = new_fsm(p, MockPersistentStore())
        to_parachute_deploy(fsm)
        for t in range(0, 5000, SYNTHETIC_DT):
            fsm.tick(t)
        self.assertEqual(drain(fsm), 0)


if __name__ == "__main__":
    unittest.main()
