# Module 2: exact threshold boundaries (>= vs >) taken from the C++ source.
# The 68 parity traces never land exactly on these boundaries, so they are
# tested directly here. SYNTHETIC values (synthetic_flight_params). SIMULATED.
import struct
import unittest

from cansat.core import fmath
from cansat.core import types as T
from cansat.core.num import f32
from cansat.core.sensor_validator import SensorValidator, REJECT_STALE_AGE, REJECT_STUCK
from cansat.config import flight_params as FP
from tests.helpers_m2 import boot, detector, frame, params, run, seeded_store, vframe

S = T.STATE_ASCENT


class PatchedAltitude:
    """Altitude = -pressure, so altitude differences are exact integers."""

    def __enter__(self):
        self.old = fmath.altitude_above_reference
        fmath.altitude_above_reference = lambda p, ref: f32(-p)
        return self

    def __exit__(self, *a):
        fmath.altitude_above_reference = self.old


class DetectorBoundaries(unittest.TestCase):
    def test_switch_debounce_is_inclusive(self):  # C++: now - since >= t_db (100)
        d, _ = detector()
        d.update(vframe(0, sw_open=True), S, False)
        d.update(vframe(99, sw_open=True), S, False)
        self.assertFalse(d.mount_open())
        d.update(vframe(100, sw_open=True), S, False)
        self.assertTrue(d.mount_open())

    def test_freefall_duration_is_inclusive(self):  # now - below_since >= t_ff (150)
        d, _ = detector()
        low = dict(acc=(0.0, 0.0, 0.1))
        d.update(vframe(0, **low), S, False)
        d.update(vframe(149, **low), S, False)
        self.assertFalse(d.freefall())
        d.update(vframe(150, **low), S, False)
        self.assertTrue(d.freefall())

    def test_freefall_threshold_is_strict(self):  # |a| < a_ff (0.3)
        th = f32(0.3)

        def step(x, n):  # move x by n float32 steps (x > 0)
            return struct.unpack("<f", struct.pack("<i", struct.unpack("<i", struct.pack("<f", x))[0] + n))[0]
        az = None
        for n in range(-8, 9):  # |a| = sqrt(round(az*az)) lands exactly on th for some nearby az
            if fmath.accel_mag(0.0, 0.0, step(th, n)) == th:
                az = step(th, n)
                break
        self.assertIsNotNone(az)
        below = az
        for _ in range(16):
            if fmath.accel_mag(0.0, 0.0, below) < th:
                break
            below = step(below, -1)
        self.assertLess(fmath.accel_mag(0.0, 0.0, below), th)

        def run_at(z):
            d, _ = detector()
            for t in (0, 200):
                v = vframe(t)
                v.raw.imu.ax_g = v.raw.imu.ay_g = 0.0
                v.raw.imu.az_g = z
                d.update(v, S, False)
            return d.freefall()
        self.assertFalse(run_at(az))     # exactly at the threshold: not free fall
        self.assertTrue(run_at(below))   # just below: free fall

    def test_baro_drop_and_window_are_inclusive(self):  # age >= w_b (500), drop >= dh_min (1.0)
        with PatchedAltitude():
            d, _ = detector()
            d.update(vframe(0, pressure=1000.0), S, False)
            d.update(vframe(499, pressure=1001.0), S, False)
            self.assertFalse(d.baro_descent())  # nothing 500 ms old yet
            d.update(vframe(500, pressure=1001.0), S, False)
            self.assertTrue(d.baro_descent())   # drop exactly 1.0 m
            d2, _ = detector()
            d2.update(vframe(0, pressure=1000.0), S, False)
            d2.update(vframe(500, pressure=1000.5), S, False)
            self.assertFalse(d2.baro_descent())

    def test_uncorroborated_after_confirm_window_is_strict(self):  # now - cand_t > t_confirm (1000)
        d, sink = detector()
        for t in range(0, 1201, 50):
            d.update(vframe(t, sw_open=True), S, False)
            if t == 1100:
                self.assertNotIn(T.EV_RELEASE_UNCORROBORATED, sink.types())
        # candidate appears at t=100 (debounce); event at 1150 = first t with t-100 > 1000
        ev = [e for e in sink.events if e.type == T.EV_RELEASE_UNCORROBORATED]
        self.assertEqual([e.t_ms for e in ev], [1150])

    def test_delayed_fallback_delay_is_inclusive(self):  # now - so_since >= fallback (300)
        with PatchedAltitude():
            d, sink = detector(FP.POLICY_DELAYED_FALLBACK)
            fall = dict(acc=(0.0, 0.0, 0.1), sw_open=False)
            t, p = 0, 1000.0
            while t <= 2000:
                d.update(vframe(t, pressure=p, **fall), S, False)
                t += 50
                p += 1.0  # 1 m per 50 ms: descent once 500 ms of history exist
            so = [e.t_ms for e in sink.events if e.type == T.EV_RELEASE_SENSORS_ONLY]
            conf = [e.t_ms for e in sink.events if e.type == T.EV_RELEASE_CONFIRMED]
            self.assertEqual(len(so), 1)
            self.assertEqual(conf, [so[0] + 300])

    def test_ascent_gain_and_duration_are_inclusive(self):  # alt >= gain (20), held >= 500
        with PatchedAltitude():
            d, sink = detector()
            d.restore_ground_reference(101325.0)
            d.update(vframe(0, pressure=-20.0), T.STATE_READY_ON_DRONE, False)
            d.update(vframe(499, pressure=-20.0), T.STATE_READY_ON_DRONE, False)
            self.assertNotIn(T.EV_ASCENT_DETECTED, sink.types())
            d.update(vframe(500, pressure=-20.0), T.STATE_READY_ON_DRONE, False)
            self.assertEqual([e.t_ms for e in sink.events if e.type == T.EV_ASCENT_DETECTED], [500])


class SelfCheckBoundary(unittest.TestCase):
    # Gap found while porting: the C++ suite only checks that 20 frames pass.
    # SYNTHETIC selfcheck_samples = 10, debounce = 100 ms: the mount reads "closed"
    # (known) from the frame at t=100, so good frames count from t=100.

    def test_self_check_needs_exactly_selfcheck_samples_consecutive_good_frames(self):
        d, sink = detector()
        for t in range(0, 551, 50):
            d.update(vframe(t), T.STATE_POWER_ON_SELF_CHECK, False)
            if t == 500:  # 9th counted frame
                self.assertNotIn(T.EV_SELF_CHECK_PASS, sink.types())
        self.assertEqual([e.t_ms for e in sink.events if e.type == T.EV_SELF_CHECK_PASS], [550])

    def test_self_check_count_restarts_after_a_bad_frame(self):
        d, sink = detector()
        for t in range(0, 501, 50):  # 9 counted frames (100..500)
            d.update(vframe(t), T.STATE_POWER_ON_SELF_CHECK, False)
        bad = vframe(550)
        bad.baro_ok = False  # invalid barometer: not a good frame, the count restarts
        d.update(bad, T.STATE_POWER_ON_SELF_CHECK, False)
        for t in range(600, 1001, 50):  # 9 counted frames again
            d.update(vframe(t), T.STATE_POWER_ON_SELF_CHECK, False)
        self.assertNotIn(T.EV_SELF_CHECK_PASS, sink.types())
        d.update(vframe(1050), T.STATE_POWER_ON_SELF_CHECK, False)
        self.assertEqual([e.t_ms for e in sink.events if e.type == T.EV_SELF_CHECK_PASS], [1050])


class ValidatorBoundaries(unittest.TestCase):
    def test_stale_age_is_strict(self):  # now - t > stale (200)
        v = SensorValidator(params())
        f = frame(1000)
        self.assertTrue(v.validate(f, 1200).baro_ok)
        v2 = SensorValidator(params())
        self.assertTrue(v2.validate(frame(1000), 1201).baro_reject & REJECT_STALE_AGE)

    def test_imu_stuck_at_exactly_n_identical(self):  # run >= 5
        v = SensorValidator(params())
        rejects = []
        for k in range(6):
            f = frame(100 * k)
            f.imu.ax_g, f.imu.ay_g, f.imu.az_g = f32(0.01), f32(0.02), f32(1.0)
            rejects.append(bool(v.validate(f, 100 * k).imu_reject & REJECT_STUCK))
        self.assertEqual(rejects, [False, False, False, False, True, True])


class StateMachineBoundaries(unittest.TestCase):
    def test_chute_timeout_alarm_is_inclusive_and_never_a_transition(self):  # now - request >= 3000
        fs = boot(seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED))
        falling = dict(sw_open=True, pressure=100100.0, acc=(0.0, 0.0, 0.05))
        events, reqs = run(fs, 50, 3400, **falling)
        self.assertEqual(reqs, [(300, T.REQ_RELEASE_PARACHUTE)])
        alarm = [e.t_ms for e in events if e.type == T.EV_CHUTE_OPEN_NOT_CONFIRMED]
        self.assertEqual(alarm, [3300])
        self.assertEqual(fs.state(), T.STATE_PARACHUTE_DEPLOY)
        self.assertEqual(fs.chute_status(), T.CHUTE_OPENING_NOT_SENSED_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
