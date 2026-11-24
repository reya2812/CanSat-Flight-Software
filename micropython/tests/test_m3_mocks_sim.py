# Module 3: mocks, virtual clock, fault injection, flight profile, runner.
# One-to-one port of firmware/test/test_step2_sim.cpp (39 cases).
# [SIMULATED] Software-only; SYNTHETIC_* values are test-only.
import math
import unittest

from cansat.core.num import f32
from cansat.mock import fault_injector as FI
from cansat.mock.fault_injector import FaultInjector, FaultWindow
from cansat.mock.memory_log import MemoryLogSink
from cansat.mock.rng import Rng
from cansat.mock.sensors import (MPU6050_FULL_SCALE_G, MockBarometer, MockImu, MockPowerMonitor, MockSwitches,
                                 SensorNoise)
from cansat.mock.truth import TruthSource, TruthState
from cansat.mock.virtual_clock import VirtualClock
from cansat.sim.flight_profile import FlightProfile, pressure_at_altitude
from cansat.sim.runner import SIM_CSV_HEADER, run
from cansat.sim.scenario import Scenario, Segment
from cansat.sim.scenarios import all_synthetic_scenarios, find_synthetic_scenario

SYNTHETIC_P_PA = f32(100000.0)
SYNTHETIC_T_C = f32(21.5)
SYNTHETIC_ACC_Z_G = f32(1.0)
SYNTHETIC_BUS_V = f32(3.7)
SYNTHETIC_I_MA = f32(120.0)
SYNTHETIC_NOISE_PA = f32(5.0)
SYNTHETIC_BIG_G = f32(25.0)
SYNTHETIC_OOR = f32(12345.0)

(C_T, C_BOOT, C_UP, C_SEG, C_ALT, C_VZ, C_MOUNTED, C_BV, C_P, C_TEMP, C_IV, C_ISAT, C_AX, C_AY, C_AZ,
 C_GX, C_GY, C_GZ, C_PV, C_BUS, C_I, C_SV, C_SW1, C_SW2, C_BCOMM, C_BREADY, C_ICOMM, C_IREADY, C_PCOMM,
 C_PREADY, C_FAULTS, C_EVENTS, K_COLS) = range(33)


class FixedTruth(TruthSource):
    def __init__(self):
        self.st = TruthState()
        self.st.pressure_pa = SYNTHETIC_P_PA
        self.st.temp_c = SYNTHETIC_T_C
        self.st.accel_g[2] = SYNTHETIC_ACC_Z_G
        self.st.bus_v = SYNTHETIC_BUS_V
        self.st.current_ma = SYNTHETIC_I_MA
        self.st.mounted = True

    def truth_at(self, t):
        s = TruthState()
        s.__dict__.update(self.st.__dict__)
        s.accel_g, s.gyro_dps = list(self.st.accel_g), list(self.st.gyro_dps)
        s.truth_ms = t
        return s


def rows(log):
    return [l.split(",") for l in log.lines if l and l[0] != "#" and not l.startswith("truth_ms,")]


def run_scenario(name, log):
    sc = find_synthetic_scenario(name)
    assert sc is not None
    return run(sc, log)


def W(target, kind, a, b, mag=0.0):
    return FaultWindow(target, kind, a, b, mag)


class ClockRng(unittest.TestCase):
    def test_clock_starts_at_zero_on_first_boot(self):
        c = VirtualClock()
        self.assertTrue(c.now_ms() == 0 and c.truth_ms() == 0 and c.boot_count() == 1 and not c.booting())

    def test_clock_advances_deterministically_and_never_backwards(self):
        c = VirtualClock()
        c.advance(250)
        self.assertEqual(c.now_ms(), 250)
        self.assertTrue(c.advance_to(1000))
        self.assertEqual(c.now_ms(), 1000)
        self.assertFalse(c.advance_to(999))
        self.assertEqual(c.truth_ms(), 1000)

    def test_clock_reset_restarts_uptime_after_reboot_gap(self):
        c = VirtualClock()
        c.advance_to(5000)
        c.simulate_reset(300)
        self.assertEqual(c.boot_count(), 2)
        self.assertTrue(c.booting())
        self.assertEqual(c.now_ms(), 0)
        c.advance_to(5299)
        self.assertTrue(c.booting())
        c.advance_to(5300)
        self.assertTrue(not c.booting() and c.now_ms() == 0)
        c.advance_to(5450)
        self.assertTrue(c.now_ms() == 150 and c.truth_ms() == 5450)

    def test_rng_is_deterministic_and_bounded(self):
        a, b, c = Rng(7), Rng(7), Rng(8)
        differs = False
        for _ in range(1000):
            x = a.uniform(2.0)
            self.assertEqual(x, b.uniform(2.0))
            self.assertTrue(-2.0 <= x <= 2.0)
            differs = differs or x != c.uniform(2.0)
        self.assertTrue(differs)
        self.assertNotEqual(Rng(0).next(), 0)


class Faults(unittest.TestCase):
    def test_fault_window_is_start_inclusive_end_exclusive(self):
        f = FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.DROPOUT, 100, 200))
        self.assertFalse(f.query(FI.TARGET_BARO, 99).dropout)
        self.assertTrue(f.query(FI.TARGET_BARO, 100).dropout)
        self.assertTrue(f.query(FI.TARGET_BARO, 199).dropout)
        self.assertFalse(f.query(FI.TARGET_BARO, 200).dropout)

    def test_fault_query_filters_by_target_and_combines_kinds(self):
        f = FaultInjector()
        f.add(W(FI.TARGET_IMU, FI.NOISE, 0, 100, 0.1))
        f.add(W(FI.TARGET_IMU, FI.NOISE, 0, 100, 0.2))
        f.add(W(FI.TARGET_IMU, FI.STALE, 50, 100))
        f.add(W(FI.TARGET_BARO, FI.DROPOUT, 0, 100))
        a = f.query(FI.TARGET_IMU, 60)
        self.assertAlmostEqual(a.noise_amp, 0.3, delta=1e-6)
        self.assertTrue(a.stale and not a.dropout)
        self.assertFalse(f.query(FI.TARGET_POWER, 60).dropout)


class Profile(unittest.TestCase):
    def test_pressure_model_is_p0_at_ground_and_falls_with_altitude(self):
        self.assertAlmostEqual(pressure_at_altitude(f32(101325.0), 0.0), 101325.0, delta=0.01)
        p100 = pressure_at_altitude(f32(101325.0), f32(100.0))
        self.assertLess(p100, 101325.0)
        self.assertAlmostEqual(101325.0 - p100, 1200.0, delta=50.0)

    def test_profile_kinematics_segments_and_end_at_ground(self):
        sc = Scenario()
        sc.ground_pressure_pa = SYNTHETIC_P_PA
        up = Segment("up", 2000, True, True, 5.0)
        fall = Segment("fall", 1000, False, True, 0.0, -4.0)
        down = Segment("down", end_at_ground=True)
        sc.segments = [up, fall, down]
        p = FlightProfile(sc)
        self.assertEqual(p.segment_count(), 3)
        self.assertEqual(p.segment_duration_ms(2), 2000)
        self.assertEqual(p.total_ms(), 5000)
        self.assertAlmostEqual(p.truth_at(1000).alt_m, 5.0, delta=1e-4)
        self.assertTrue(p.truth_at(1000).mounted)
        self.assertAlmostEqual(p.truth_at(2000).alt_m, 10.0, delta=1e-4)
        self.assertEqual(p.truth_at(2500).label, "fall")
        self.assertFalse(p.truth_at(2500).mounted)
        self.assertAlmostEqual(p.truth_at(3000).alt_m, 8.0, delta=1e-3)
        self.assertAlmostEqual(p.truth_at(3000).vz_mps, -4.0, delta=1e-3)
        self.assertAlmostEqual(p.truth_at(5000).alt_m, 0.0, delta=1e-3)
        self.assertAlmostEqual(p.truth_at(9000).alt_m, 0.0, delta=1e-3)
        self.assertEqual(p.truth_at(9000).vz_mps, 0.0)
        self.assertGreater(p.truth_at(2500).pressure_pa, p.truth_at(2000).pressure_pa - 1.0)

    def test_nominal_profile_reaches_100m_and_ends_on_ground(self):
        p = FlightProfile(find_synthetic_scenario("nominal"))
        self.assertAlmostEqual(p.truth_at(p.segment_start_ms(2)).alt_m, 100.0, delta=0.01)
        self.assertAlmostEqual(p.truth_at(p.total_ms()).alt_m, 0.0, delta=0.01)


def baro(c, t, f, noise=None, seed=1):
    return MockBarometer(c, t, f, noise or SensorNoise(), seed)


class Barometer(unittest.TestCase):
    def test_baro_reads_truth_with_uptime_timestamp(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        b = baro(c, t, f)
        self.assertTrue(b.begin())
        c.advance_to(400)
        s = b.read()
        self.assertTrue(s.valid and s.t_ms == 400)
        self.assertTrue(s.pressure_pa == SYNTHETIC_P_PA and s.temp_c == SYNTHETIC_T_C)

    def test_baro_not_detected_makes_begin_fail_and_reads_invalid(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.NOT_DETECTED, 0, 10))
        b = baro(c, t, f)
        self.assertFalse(b.begin())
        c.advance_to(50)
        self.assertFalse(b.read().valid)
        self.assertTrue(b.begin())
        self.assertTrue(b.read().valid)

    def test_baro_read_before_begin_is_invalid(self):
        self.assertFalse(baro(VirtualClock(), FixedTruth(), FaultInjector()).read().valid)

    def test_baro_dropout_is_invalid_then_recovers(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.DROPOUT, 100, 200))
        b = baro(c, t, f)
        b.begin()
        c.advance_to(150)
        self.assertFalse(b.read().valid)
        c.advance_to(200)
        self.assertTrue(b.read().valid)

    def test_baro_stale_repeats_last_fresh_sample_and_timestamp(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.STALE, 100, 300))
        b = baro(c, t, f)
        b.begin()
        c.advance_to(50)
        fresh = b.read()
        t.st.pressure_pa = f32(SYNTHETIC_P_PA - 500.0)
        c.advance_to(200)
        stale = b.read()
        self.assertTrue(stale.valid)
        self.assertEqual(stale.t_ms, fresh.t_ms)
        self.assertEqual(stale.pressure_pa, fresh.pressure_pa)
        c.advance_to(300)
        after = b.read()
        self.assertTrue(after.t_ms == 300 and after.pressure_pa == SYNTHETIC_P_PA - 500.0)

    def test_baro_stale_without_history_is_invalid(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.STALE, 0, 100))
        b = baro(c, t, f)
        b.begin()
        self.assertFalse(b.read().valid)

    def test_baro_noise_is_bounded_and_deterministic(self):
        c1, c2, t, f = VirtualClock(), VirtualClock(), FixedTruth(), FaultInjector()
        n = SensorNoise(pressure_pa=SYNTHETIC_NOISE_PA)
        a, b = baro(c1, t, f, n, 99), baro(c2, t, f, n, 99)
        a.begin()
        b.begin()
        varied, first = False, None
        for i in range(200):
            c1.advance(10)
            c2.advance(10)
            pa = a.read().pressure_pa
            self.assertEqual(pa, b.read().pressure_pa)
            self.assertLessEqual(abs(pa - SYNTHETIC_P_PA), SYNTHETIC_NOISE_PA + 0.01)
            first = pa if i == 0 else first
            varied = varied or pa != first
        self.assertTrue(varied)

    def test_baro_invalid_values_are_reported_valid_for_later_validation(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_BARO, FI.ZERO_READ, 0, 10))
        f.add(W(FI.TARGET_BARO, FI.NAN_VALUE, 10, 20))
        f.add(W(FI.TARGET_BARO, FI.OUT_OF_RANGE, 20, 30, SYNTHETIC_OOR))
        b = baro(c, t, f)
        b.begin()
        s = b.read()
        self.assertTrue(s.valid and s.pressure_pa == 0.0 and s.temp_c == 0.0)
        c.advance_to(10)
        s = b.read()
        self.assertTrue(s.valid and math.isnan(s.pressure_pa))
        c.advance_to(20)
        s = b.read()
        self.assertTrue(s.valid and s.pressure_pa == SYNTHETIC_OOR)


class ImuPower(unittest.TestCase):
    def test_imu_reads_truth_without_saturation(self):
        m = MockImu(VirtualClock(), FixedTruth(), FaultInjector(), SensorNoise(), 1)
        self.assertTrue(m.begin())
        s = m.read()
        self.assertTrue(s.valid and not s.saturated and s.az_g == SYNTHETIC_ACC_Z_G and s.ax_g == 0.0)

    def test_imu_clips_at_16g_and_flags_saturation(self):
        t = FixedTruth()
        t.st.accel_g[2] = SYNTHETIC_BIG_G
        t.st.accel_g[0] = -SYNTHETIC_BIG_G
        m = MockImu(VirtualClock(), t, FaultInjector(), SensorNoise(), 1)
        m.begin()
        s = m.read()
        self.assertTrue(s.valid and s.saturated)
        self.assertTrue(s.az_g == MPU6050_FULL_SCALE_G and s.ax_g == -MPU6050_FULL_SCALE_G)

    def test_imu_zero_read_looks_like_free_fall_but_is_reported_valid(self):
        t, f = FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_IMU, FI.ZERO_READ, 0, 100))
        m = MockImu(VirtualClock(), t, f, SensorNoise(), 1)
        m.begin()
        s = m.read()
        self.assertTrue(s.valid)
        self.assertEqual((s.ax_g, s.ay_g, s.az_g, s.gx_dps, s.gy_dps, s.gz_dps), (0.0,) * 6)
        self.assertTrue(t.st.mounted)

    def test_imu_dropout_and_stale(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_IMU, FI.DROPOUT, 100, 200))
        f.add(W(FI.TARGET_IMU, FI.STALE, 200, 300))
        m = MockImu(c, t, f, SensorNoise(), 1)
        m.begin()
        c.advance_to(50)
        fresh = m.read()
        c.advance_to(150)
        self.assertFalse(m.read().valid)
        c.advance_to(250)
        st = m.read()
        self.assertTrue(st.valid and st.t_ms == fresh.t_ms)

    def test_power_reads_truth_and_handles_faults(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        f.add(W(FI.TARGET_POWER, FI.OUT_OF_RANGE, 100, 200, SYNTHETIC_OOR))
        f.add(W(FI.TARGET_POWER, FI.DROPOUT, 200, 300))
        p = MockPowerMonitor(c, t, f, SensorNoise(), 1)
        self.assertTrue(p.begin())
        s = p.read()
        self.assertTrue(s.valid and s.bus_v == SYNTHETIC_BUS_V and s.current_ma == SYNTHETIC_I_MA)
        c.advance_to(150)
        s = p.read()
        self.assertTrue(s.valid and s.current_ma == SYNTHETIC_OOR)
        c.advance_to(250)
        self.assertFalse(p.read().valid)


class Switches(unittest.TestCase):
    def test_switch_levels_follow_truth_and_polarity(self):
        c, t, f = VirtualClock(), FixedTruth(), FaultInjector()
        sw = MockSwitches(c, t, f, False, True)
        s = sw.read()
        self.assertTrue(s.valid and s.raw == [False, True])
        t.st.mounted = False
        self.assertEqual(sw.read().raw, [True, False])
        self.assertTrue(sw.level_means_closed(0, False) and sw.level_means_closed(1, True))

    def test_switch_stuck_closed_overrides_released_truth(self):
        t, f = FixedTruth(), FaultInjector()
        t.st.mounted = False
        f.add(W(FI.TARGET_SWITCH1, FI.STUCK_CLOSED, 0, 1000))
        s = MockSwitches(VirtualClock(), t, f, True, True).read()
        self.assertTrue(s.valid and s.raw == [True, False])

    def test_switch_stuck_open_overrides_mounted_truth(self):
        f = FaultInjector()
        f.add(W(FI.TARGET_SWITCH2, FI.STUCK_OPEN, 0, 1000))
        self.assertEqual(MockSwitches(VirtualClock(), FixedTruth(), f, True, True).read().raw, [True, False])

    def test_switch_bounce_toggles_with_period(self):
        c, f = VirtualClock(), FaultInjector()
        f.add(W(FI.TARGET_SWITCH1, FI.BOUNCE, 100, 400, 50.0))
        sw = MockSwitches(c, FixedTruth(), f, True, True)
        for t, want in ((110, True), (160, False), (210, True), (400, True)):
            c.advance_to(t)
            self.assertEqual(sw.read().raw[0], want, t)

    def test_switch_dropout_invalidates_sample(self):
        f = FaultInjector()
        f.add(W(FI.TARGET_SWITCH1, FI.DROPOUT, 0, 100))
        self.assertFalse(MockSwitches(VirtualClock(), FixedTruth(), f, True, True).read().valid)


class Runner(unittest.TestCase):
    def test_runner_nominal_visits_all_segments_in_order(self):
        s = run_scenario("nominal", MemoryLogSink())
        self.assertEqual(s.segment_sequence, ["mounted_on_ground", "ascent", "hold_at_altitude", "free_fall",
                                              "chute_opening", "descent", "landing_impact", "landed"])
        self.assertEqual((s.baro_invalid, s.imu_invalid, s.power_invalid, s.switch_invalid), (0, 0, 0, 0))
        self.assertEqual((s.resets, s.final_boot, s.log_write_failures), (0, 1, 0))

    def test_runner_log_is_labelled_simulated_and_well_formed(self):
        log = MemoryLogSink()
        run_scenario("nominal", log)
        self.assertIn("SIMULATED", log.lines[0])
        self.assertIn("SYNTHETIC", log.lines[0])
        self.assertIn(SIM_CSV_HEADER, log.lines)
        for r in rows(log):
            self.assertEqual(len(r), K_COLS)

    def test_runner_nominal_logs_markers_including_chute_request_point(self):
        log = MemoryLogSink()
        run_scenario("nominal", log)
        release = chute = booted = False
        for r in rows(log):
            if "MARK:scripted release" in r[C_EVENTS]:
                release = True
                self.assertEqual(r[C_SEG], "free_fall")
            if "MARK:parachute deployment request point" in r[C_EVENTS]:
                chute = True
                self.assertIn("nothing actuated", r[C_EVENTS])
            booted = booted or "BEGIN:baro=ok/imu=ok/power=ok" in r[C_EVENTS]
        self.assertTrue(release and chute and booted)

    def test_runner_nominal_switches_open_at_release_and_imu_saturates_only_at_chute_opening(self):
        log = MemoryLogSink()
        s = run_scenario("nominal", log)
        self.assertGreater(s.imu_saturated, 0)
        for r in rows(log):
            if r[C_ISAT] == "1":
                self.assertEqual(r[C_SEG], "chute_opening")
            if r[C_MOUNTED] == "1":
                self.assertEqual((r[C_SW1], r[C_SW2]), ("0", "0"))
            if r[C_MOUNTED] == "0":
                self.assertEqual((r[C_SW1], r[C_SW2]), ("1", "1"))
            if r[C_SEG] == "free_fall":
                self.assertLess(abs(float(r[C_AZ])), 0.2)

    def test_every_synthetic_scenario_runs_and_is_deterministic(self):
        scs = all_synthetic_scenarios()
        self.assertGreaterEqual(len(scs), 9)
        for sc in scs:
            a, b = MemoryLogSink(), MemoryLogSink()
            s1 = run(sc, a)
            run(sc, b)
            self.assertEqual(a.lines, b.lines)
            self.assertTrue(s1.ticks > 0 and s1.log_write_failures == 0 and sc.description)

    def test_runner_baro_dropout_counts_invalid_samples(self):
        log = MemoryLogSink()
        s = run_scenario("baro_dropout", log)
        self.assertEqual((s.baro_invalid, s.imu_invalid), (60, 0))
        on = off = False
        for r in rows(log):
            if r[C_BV] == "0":
                self.assertEqual(r[C_FAULTS], "baro.dropout")
            on = on or "FAULT_ON:baro.dropout" in r[C_EVENTS]
            off = off or "FAULT_OFF:baro.dropout" in r[C_EVENTS]
        self.assertTrue(on and off)

    def test_runner_stale_imu_freezes_timestamp_across_release(self):
        log = MemoryLogSink()
        run_scenario("stale_imu", log)
        frozen, n = None, 0
        for r in rows(log):
            if r[C_FAULTS] == "imu.stale":
                frozen = frozen or r[C_AZ]
                self.assertEqual(r[C_AZ], frozen)
                n += 1
        self.assertEqual(n, 40)

    def test_runner_stuck_switch_reads_closed_through_free_fall(self):
        log = MemoryLogSink()
        run_scenario("stuck_switch_released", log)
        n = 0
        for r in rows(log):
            self.assertEqual((r[C_SW1], r[C_SW2]), ("0", "0"))
            if r[C_SEG] == "free_fall":
                n += 1
                self.assertEqual(r[C_MOUNTED], "0")
        self.assertGreater(n, 0)

    def test_runner_mounted_imu_zero_looks_like_free_fall_while_mounted(self):
        log = MemoryLogSink()
        run_scenario("mounted_imu_zero", log)
        n = 0
        for r in rows(log):
            self.assertEqual(r[C_MOUNTED], "1")
            if r[C_FAULTS] == "imu.zero_read":
                n += 1
                self.assertEqual((r[C_IV], r[C_AZ]), ("1", "0.000"))
                self.assertLess(float(r[C_VZ]), 0.0)
        self.assertEqual(n, 160)

    def test_runner_reset_mid_flight_restarts_uptime_and_reinitialises(self):
        log = MemoryLogSink()
        s = run_scenario("reset_mid_flight", log)
        self.assertEqual((s.resets, s.final_boot, s.booting_rows), (2, 3, 16))
        n = 0
        for r in rows(log):
            if "BOOT_COMPLETE" in r[C_EVENTS]:
                n += 1
                self.assertEqual(r[C_UP], "0")
                self.assertIn("BEGIN:baro=ok/imu=ok/power=ok", r[C_EVENTS])
            if "BOOTING" in r[C_EVENTS]:
                self.assertEqual(r[C_BV], "")
        self.assertEqual(n, 2)

    def test_runner_imu_not_detected_invalid_for_whole_run(self):
        log = MemoryLogSink()
        s = run_scenario("imu_not_detected", log)
        self.assertEqual(s.imu_invalid, s.sample_rows)
        self.assertIn("imu=FAIL", rows(log)[0][C_EVENTS])

    def test_runner_counts_log_write_failures(self):
        log = MemoryLogSink()
        log.fail_writes = True
        self.assertGreater(run_scenario("nominal", log).log_write_failures, 0)


if __name__ == "__main__":
    unittest.main()
