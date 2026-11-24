# Sensor drivers and the sensor suite against FAKE register maps. LOGIC ONLY:
# register maps/formulas are [ASSUMPTION] (recalled datasheets) on both sides,
# so these tests cannot catch a wrong datasheet recollection - the bench can.
import math
import unittest

import fakes
from fakes import FakeI2C, bmp280_regs, flight_cfg, full_bus, ina_regs, mpu_regs, set_bmp_adc, set_mpu_raw
import cs_proto as P
from cs_bmp280 import BMP280, altitude_m
from cs_ina219 import INA219
from cs_mpu import MpuImu
from cs_sensors import MAX_CONSECUTIVE_ERRORS, SensorChannel, SensorSuite


class Bmp280(unittest.TestCase):
    def test_identifies_and_reads_datasheet_example_nonblocking(self):
        i2c = FakeI2C({0x76: bmp280_regs()})
        b = BMP280(i2c, 0x76)
        self.assertTrue(b.begin())
        self.assertEqual(b.chip, "BMP280")
        self.assertEqual(i2c.writes, [(0x76, 0xF4, b"\x25")])     # trigger only
        r = b.read(10)
        self.assertTrue(r.valid)
        self.assertTrue(r.data_ready)
        self.assertAlmostEqual(r.temp_c, 25.08, places=2)
        self.assertAlmostEqual(r.pressure_pa, 100653.27, delta=0.05)
        self.assertEqual(r.t_ms, 10)

    def test_bme280_supported_for_temperature_and_pressure(self):
        b = BMP280(FakeI2C({0x77: bmp280_regs(chip_id=0x60)}), 0x77)
        self.assertTrue(b.begin())
        self.assertEqual(b.chip, "BME280")

    def test_unknown_or_unsupported_chip_id_not_trusted(self):
        for cid in (0x55, 0x12):
            b = BMP280(FakeI2C({0x76: bmp280_regs(chip_id=cid)}), 0x76)
            self.assertFalse(b.begin())
            self.assertEqual(b.status, P.ST_UNKNOWN_CHIP)
            self.assertIn("0x%02X" % cid, b.error)

    def test_invalid_calibration_fails_init(self):
        calib = (0,) + fakes.EXAMPLE_CALIB[1:]
        b = BMP280(FakeI2C({0x76: bmp280_regs(calib=calib)}), 0x76)
        self.assertFalse(b.begin())
        self.assertEqual(b.status, P.ST_INIT_FAILED)

    def test_conversion_in_progress_is_not_ready_not_error(self):
        regs = bmp280_regs()
        regs[0xF3] = 0x08
        b = BMP280(FakeI2C({0x76: regs}), 0x76)
        b.begin()
        r = b.read(0)
        self.assertFalse(r.valid)
        self.assertTrue(r.comm_ok)
        self.assertEqual(r.status, P.ST_NOT_READY)

    def test_skipped_measurement_value_is_not_ready(self):
        regs = bmp280_regs()
        set_bmp_adc(regs, 0x80000, 0x80000)
        b = BMP280(FakeI2C({0x76: regs}), 0x76)
        b.begin()
        r = b.read(0)
        self.assertFalse(r.valid)
        self.assertFalse(r.data_ready)

    def test_out_of_range_value_is_implausible(self):
        regs = bmp280_regs()
        set_bmp_adc(regs, fakes.EXAMPLE_ADC_T, 1000)   # absurd pressure
        b = BMP280(FakeI2C({0x76: regs}), 0x76)
        b.begin()
        r = b.read(0)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, P.ST_IMPLAUSIBLE)

    def test_altitude_matches_flight_software_formula(self):
        from cansat.core.fmath import altitude_above_reference
        for p in (101325.0, 95000.0, 90000.0, 100000.0):
            self.assertAlmostEqual(altitude_m(p, 101325.0), altitude_above_reference(p, 101325.0), delta=0.02)
        self.assertEqual(altitude_m(100000.0, 100000.0), 0.0)


class Mpu(unittest.TestCase):
    def test_identifies_each_supported_chip(self):
        for who, name in ((0x68, "MPU-6050"), (0x70, "MPU-6500"), (0x71, "MPU-9250"), (0x73, "MPU-9255")):
            m = MpuImu(FakeI2C({0x68: mpu_regs(who=who)}), 0x68)
            self.assertTrue(m.begin(), name)
            self.assertEqual(m.chip, name)

    def test_unknown_who_am_i_never_valid(self):
        i2c = FakeI2C({0x68: mpu_regs(who=0x98)})
        m = MpuImu(i2c, 0x68)
        self.assertFalse(m.begin())
        self.assertEqual(m.status, P.ST_UNKNOWN_CHIP)
        self.assertIn("0x98", m.error)
        self.assertEqual(i2c.writes, [])        # nothing written to an unidentified chip

    def test_wakes_only_if_asleep_and_scales_by_chip_ranges(self):
        i2c = FakeI2C({0x68: mpu_regs(asleep=True, accel=(8192, 0, 4096), gyro=(655, 0, -655), afs=1, gfs=2)})
        m = MpuImu(i2c, 0x68)
        m.begin()
        self.assertEqual(i2c.writes, [(0x68, 0x6B, b"\x00")])
        self.assertEqual((m.accel_fs_g, m.gyro_fs_dps), (4, 1000))
        r = m.read(5)
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.ax_g, 1.0)
        self.assertAlmostEqual(r.az_g, 0.5)
        self.assertAlmostEqual(r.gx_dps, 20.0, places=1)
        self.assertTrue(r.data_ready)
        i2c2 = FakeI2C({0x68: mpu_regs(asleep=False)})
        MpuImu(i2c2, 0x68).begin()
        self.assertEqual(i2c2.writes, [])

    def test_temperature_formula_per_family(self):
        r = MpuImu(FakeI2C({0x68: mpu_regs(who=0x68, temp=-340)}), 0x68)
        r.begin()
        self.assertAlmostEqual(r.read(0).temp_c, 35.53, places=2)
        r = MpuImu(FakeI2C({0x68: mpu_regs(who=0x71, temp=3339)}), 0x68)
        r.begin()
        self.assertAlmostEqual(r.read(0).temp_c, 31.0, places=1)

    def test_all_zero_output_is_implausible(self):
        m = MpuImu(FakeI2C({0x68: mpu_regs(accel=(0, 0, 0), gyro=(0, 0, 0), temp=0)}), 0x68)
        m.begin()
        r = m.read(0)
        self.assertFalse(r.valid)
        self.assertEqual(r.status, P.ST_IMPLAUSIBLE)

    def test_saturation_flag(self):
        m = MpuImu(FakeI2C({0x68: mpu_regs(accel=(32767, 0, 0))}), 0x68)
        m.begin()
        r = m.read(0)
        self.assertTrue(r.valid)
        self.assertTrue(r.saturated)


class Ina219(unittest.TestCase):
    def test_never_writes_and_gated_by_default(self):
        i2c = FakeI2C({0x40: ina_regs()})
        d = INA219(i2c, 0x40, 0.1)
        self.assertTrue(d.begin())
        r = d.read(0)
        self.assertEqual(i2c.writes, [])
        self.assertEqual(r.status, P.ST_DISABLED)
        self.assertFalse(r.bus_valid)
        self.assertFalse(r.current_valid)
        self.assertEqual(r.current_ma, 0.0)          # no invented current
        self.assertAlmostEqual(r.raw_bus_v, 3.7, places=2)

    def test_current_from_shunt_only_when_declared_connected(self):
        d = INA219(FakeI2C({0x40: ina_regs(shunt_raw=1234)}), 0x40, 0.1, bus_connected=True, shunt_connected=True)
        d.begin()
        r = d.read(0)
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.shunt_mv, 12.34)
        self.assertAlmostEqual(r.current_ma, 123.4)
        self.assertAlmostEqual(r.power_mw, 3.7 * 123.4, places=1)
        d = INA219(FakeI2C({0x40: ina_regs()}), 0x40, 0.1, bus_connected=True, shunt_connected=False)
        d.begin()
        r = d.read(0)
        self.assertTrue(r.bus_valid)
        self.assertFalse(r.current_valid)
        self.assertFalse(r.valid)
        self.assertIsNone(r.power_mw)

    def test_shunt_over_pga_range_and_overflow_are_invalid(self):
        d = INA219(FakeI2C({0x40: ina_regs(shunt_raw=32000, ovf=1)}), 0x40, 0.1, True, True)
        d.begin()
        r = d.read(0)
        self.assertFalse(r.bus_valid)
        self.assertFalse(r.current_valid)
        self.assertEqual(r.status, P.ST_IMPLAUSIBLE)

    def test_non_default_config_reported(self):
        d = INA219(FakeI2C({0x40: ina_regs(config=0x1234)}), 0x40, 0.1)
        d.begin()
        self.assertFalse(d.config_is_default)
        self.assertIn("0x1234", d.error)

    def test_shunt_connected_without_resistance_refuses(self):
        d = INA219(FakeI2C({0x40: ina_regs()}), 0x40, None, shunt_connected=True)
        self.assertFalse(d.begin())


class Channel(unittest.TestCase):
    def test_exception_isolated_and_reinit_after_repeated_errors(self):
        regs = mpu_regs()
        i2c = FakeI2C({0x68: regs})
        ch = SensorChannel("imu", MpuImu(i2c, 0x68), retry_ms=100)
        self.assertTrue(ch.begin(0))
        self.assertTrue(ch.sample(0, 0).valid)
        i2c.fail_regs.add((0x68, 0x3A))
        for k in range(MAX_CONSECUTIVE_ERRORS):
            r = ch.sample(k, k)
            self.assertEqual(r.status, P.ST_READ_ERROR)
            self.assertFalse(ch.valid())
        self.assertFalse(ch.init_ok)
        self.assertIsNone(ch.sample(50, 50))       # waiting for retry
        self.assertFalse(ch.valid())
        i2c.fail_regs.clear()
        self.assertTrue(ch.sample(200, 200).valid)
        self.assertEqual(ch.n_init, 2)

    def test_failed_reinit_never_leaves_old_valid_reading(self):
        i2c = FakeI2C({0x76: bmp280_regs()})
        ch = SensorChannel("baro1", BMP280(i2c, 0x76), retry_ms=100)
        ch.begin(0)
        ch.sample(0, 0)
        self.assertTrue(ch.valid())
        i2c.fail_regs.add((0x76, None))
        for k in range(1, 5):
            ch.sample(k * 200, k * 200)
        self.assertFalse(ch.valid())
        self.assertNotEqual(ch.status, P.ST_OK)

    def test_absent_sensor_channel(self):
        ch = SensorChannel("baro2", None, 100)
        self.assertIsNone(ch.sample(0, 0))
        self.assertEqual(ch.status, P.ST_NOT_PRESENT)
        self.assertFalse(ch.valid())


class Suite(unittest.TestCase):
    def suite(self, devices, **cfg):
        i2c = FakeI2C(devices)
        return SensorSuite(flight_cfg(**cfg)).discover(i2c, 0), i2c

    def test_full_bus_identified(self):
        s, _ = self.suite(full_bus())
        self.assertEqual(s.baro1.driver.addr, 0x76)
        self.assertEqual(s.baro2.driver.addr, 0x77)
        self.assertEqual(s.imu.driver.chip, "MPU-9250")
        self.assertTrue(s.power.init_ok)
        self.assertFalse(s.baro_dup_suspect)
        s.sample(0, 0)
        s.sample(50, 50)
        self.assertTrue(s.baro1.valid() and s.baro2.valid() and s.imu.valid())
        self.assertEqual(s.power.status, P.ST_DISABLED)
        self.assertAlmostEqual(s.alt_m, 0.0)        # reference = first valid reading
        self.assertTrue(s.reference_auto)

    def test_single_barometer_raises_duplicate_suspicion_and_one_channel_only(self):
        s, _ = self.suite({0x68: mpu_regs(), 0x76: bmp280_regs()})
        self.assertTrue(s.baro_dup_suspect)
        self.assertEqual(s.baro_identified, [0x76])
        self.assertIsNone(s.baro2.driver)            # never reported as two sensors
        self.assertEqual(s.baro2.status, P.ST_NOT_PRESENT)

    def test_primary_barometer_selectable(self):
        s, _ = self.suite(full_bus(), BARO_PRIMARY_ADDR=0x77)
        self.assertEqual(s.baro1.driver.addr, 0x77)
        self.assertEqual(s.baro2.driver.addr, 0x76)

    def test_unidentified_device_at_baro_address_never_valid(self):
        s, _ = self.suite({0x76: bmp280_regs(chip_id=0x33)})
        self.assertEqual(s.baro1.status, P.ST_UNKNOWN_CHIP)
        self.assertEqual(s.baro_identified, [])
        s.sample(0, 0)
        self.assertFalse(s.baro1.valid())
        self.assertIsNone(s.alt_m)

    def test_missing_sensors_and_empty_bus(self):
        s, _ = self.suite({})
        for ch in s.channels():
            self.assertEqual(ch.status, P.ST_NOT_PRESENT)
        s.sample(0, 0)    # must not raise

    def test_scan_failure_reported_not_raised(self):
        s = SensorSuite(flight_cfg()).discover(FakeI2C({}, scan_raises=OSError(110)), 0)
        self.assertIn("scan raised", s.scan_error)

    def test_one_failing_sensor_does_not_affect_others(self):
        s, i2c = self.suite(full_bus())
        i2c.fail_regs.add((0x68, None))
        s.sample(0, 0)
        s.sample(50, 50)
        self.assertFalse(s.imu.valid())
        self.assertTrue(s.baro1.valid())
        self.assertTrue(s.baro2.valid())

    def test_configured_reference_pressure(self):
        s, _ = self.suite(full_bus(), BARO_REFERENCE_PA=101325.0)
        s.sample(0, 0)
        s.sample(50, 50)
        self.assertFalse(s.reference_auto)
        self.assertAlmostEqual(s.alt_m, altitude_m(s.baro1.last.pressure_pa, 101325.0))
        self.assertTrue(s.alt_m > 0)

    def test_second_imu_reported_not_used(self):
        s, _ = self.suite({0x68: mpu_regs(), 0x69: mpu_regs(who=0x68)})
        self.assertEqual(s.imu.driver.addr, 0x68)
        self.assertEqual([c.driver.addr for c in s.extra], [0x69])

    def test_frozen_imu_values_are_not_rejected_by_driver_but_visible(self):
        # stuck-output detection is the flight software's validator's job (imu_stuck_identical_samples)
        s, _ = self.suite({0x68: mpu_regs()})
        s.sample(0, 0)
        a = s.imu.last
        s.sample(50, 50)
        self.assertEqual((a.ax_g, a.gz_dps), (s.imu.last.ax_g, s.imu.last.gz_dps))
        self.assertTrue(math.isfinite(s.imu.last.ax_g))


if __name__ == "__main__":
    unittest.main()
