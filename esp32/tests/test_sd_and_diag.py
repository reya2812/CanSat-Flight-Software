# SD self-test and the flight-board diagnostic, against fakes. LOGIC ONLY.
import types
import unittest

import fakes
from fakes import FakeFS, FakeI2C, bmp280_regs, fake_machine, flight_cfg, full_bus, mpu_regs
import cs_proto as P
import cs_sd
from cs_diag import EV_DETECTED, EV_IDENTIFIED, EV_PLAUSIBLE, FAIL, PASS, SKIP, WARN, run_diag


class Sd(unittest.TestCase):
    def run_sd(self, fs, enabled=True, machine=None, token="abc"):
        cfg = flight_cfg(SD_SUPPLY_CONFIRMED=enabled)
        m = machine if machine is not None else fake_machine()
        return cs_sd.sd_selftest(m, fs, cfg, token, open_fn=fs.open), m

    def test_disabled_by_default_never_touches_card(self):
        self.assertIs(flight_cfg().SD_SUPPLY_CONFIRMED, False)
        fs = FakeFS()
        m = fake_machine()
        res, _ = self.run_sd(fs, enabled=False, machine=m)
        self.assertTrue(res.skipped)
        self.assertEqual(res.status, P.ST_DISABLED)
        self.assertEqual(fs.calls, [])
        self.assertEqual(m.SDCard.made, [])

    def test_gate_requires_literal_true(self):
        res, _ = self.run_sd(FakeFS(), enabled="yes")
        self.assertTrue(res.skipped)

    def test_write_remount_read_verify_delete_unmount(self):
        fs = FakeFS()
        res, m = self.run_sd(fs)
        self.assertTrue(res.ok, res.steps)
        self.assertEqual(res.status, P.ST_OK)
        ops = [c[0] for c in fs.calls]
        self.assertEqual(ops, ["mount", "open", "umount", "mount", "open", "remove", "umount"])
        path = "/sd/" + cs_sd.TEST_FILE
        self.assertNotIn(path, fs.files)                 # cleaned up
        self.assertIn("/sd/DCIM", fs.files)              # nothing else touched
        written = [c for c in fs.calls if c[0] == "open"]
        self.assertTrue(all(c[1] == path for c in written))
        self.assertEqual(fs.mounted, set())
        self.assertEqual(m.SDCard.made[0]["slot"], 2)

    def test_missing_card(self):
        fs = FakeFS(card_present=False)
        res, _ = self.run_sd(fs)
        self.assertFalse(res.ok)
        self.assertEqual(res.failed_step()[0], "mount")
        self.assertEqual(res.status, P.ST_NOT_PRESENT)

    def test_write_failure_still_unmounts(self):
        fs = FakeFS()
        fs.fail["write"] = OSError(30)  # EROFS
        res, _ = self.run_sd(fs)
        self.assertFalse(res.ok)
        self.assertEqual(res.failed_step()[0], "write")
        self.assertEqual(fs.mounted, set())

    def test_read_failure_and_corruption(self):
        fs = FakeFS()
        fs.fail["read"] = OSError(5)
        res, _ = self.run_sd(fs)
        self.assertEqual(res.failed_step()[0], "read")
        fs = FakeFS()
        fs.corrupt_read = True
        res, _ = self.run_sd(fs)
        self.assertEqual(res.failed_step()[0], "verify")
        self.assertEqual(res.status, P.ST_IMPLAUSIBLE)

    def test_no_driver_and_init_failure(self):
        res, _ = self.run_sd(FakeFS(), machine=fake_machine(sdcard=False))
        self.assertEqual(res.failed_step()[0], "driver")
        res, _ = self.run_sd(FakeFS(), machine=fake_machine(sdcard_raises=OSError(16)))
        self.assertEqual(res.failed_step()[0], "init")


class FakeNetwork:
    STA_IF = 0

    def __init__(self, mac):
        self.mac = mac

    def WLAN(self, _):
        mac = self.mac

        class W:
            def active(self, v=None):
                return True

            def config(self, k):
                return mac
        return W()


class Diag(unittest.TestCase):
    def diag(self, devices, sd=False, fs=None, rc=None, mac=fakes.FLIGHT_MAC, espnow=True, **cfg):
        out = []
        fs = fs or FakeFS()
        m = fake_machine(FakeI2C(devices))
        rep = run_diag(m, fs, flight_cfg(SD_SUPPLY_CONFIRMED=sd, **cfg), rc=rc, out=out.append, sleep=lambda ms: None,
                       now_fn=fakes.TickClock(), network_mod=FakeNetwork(mac), espnow_present=espnow, samples=5,
                       open_fn=fs.open)
        return rep, "\n".join(out)

    def test_full_bus_report_with_evidence_levels(self):
        rep, text = self.diag(full_bus())
        self.assertEqual(rep.status("I2C scan"), [PASS])
        self.assertEqual(rep.evidence("I2C scan"), [EV_DETECTED])
        self.assertEqual(rep.evidence("ID imu"), [EV_IDENTIFIED])
        self.assertEqual(rep.evidence("ID power"), [EV_DETECTED])   # INA219 has no ID register
        self.assertEqual(rep.status("IMU data"), [WARN])            # fake output never changes -> "frozen?"
        self.assertEqual(rep.status("baro1"), [PASS])
        self.assertEqual(rep.evidence("baro1"), [EV_PLAUSIBLE])
        self.assertEqual(rep.status("SD card"), [SKIP])
        self.assertIn("NOTHING here is PHYSICALLY VALIDATED", text)
        self.assertNotIn("VALIDATED}", text)
        self.assertEqual(rep.status("ESP-NOW module"), [PASS])

    def test_changing_imu_values_pass(self):
        regs = mpu_regs()
        bus = {0x68: regs}
        i2c = FakeI2C(bus)
        k = [0]
        orig = i2c.readfrom_mem

        def read(addr, reg, n):
            if reg == 0x3A:
                k[0] += 1
                fakes.set_mpu_raw(regs, (k[0], 3, 16384), 100, (1, 2, k[0]))
            return orig(addr, reg, n)
        i2c.readfrom_mem = read
        m = fake_machine(i2c)
        rep = run_diag(m, FakeFS(), flight_cfg(), out=lambda s: None, sleep=lambda ms: None,
                       now_fn=fakes.TickClock(), samples=4)
        self.assertEqual(rep.status("IMU data"), [PASS])
        self.assertEqual(rep.evidence("IMU data"), [EV_PLAUSIBLE])

    def test_missing_and_failing_devices_isolated(self):
        bus = full_bus()
        del bus[0x40]
        bus[0x68] = mpu_regs(who=0x12)
        rep, text = self.diag(bus)
        self.assertEqual(rep.status("ID power"), [FAIL])
        self.assertEqual(rep.status("ID imu"), [WARN])
        self.assertIn("UNKNOWN identity: WHO_AM_I=0x12", text)
        self.assertEqual(rep.status("baro1"), [PASS])

    def test_duplicate_barometer_warning(self):
        rep, text = self.diag({0x68: mpu_regs(), 0x77: bmp280_regs()})
        self.assertEqual(rep.status("Baro duplicates"), [WARN])
        self.assertIn("SAME address", text)

    def test_empty_bus_skips_sensor_sections(self):
        rep, _ = self.diag({})
        self.assertEqual(rep.status("I2C scan"), [FAIL])
        self.assertEqual(rep.status("IMU"), [SKIP])

    def test_sd_enabled_pass_and_missing_card_fail(self):
        rep, _ = self.diag(full_bus(), sd=True)
        self.assertEqual(rep.status("SD card"), [PASS])
        rep, _ = self.diag(full_bus(), sd=True, fs=FakeFS(card_present=False))
        self.assertEqual(rep.status("SD card"), [FAIL])

    def test_mac_checks(self):
        rc = types.SimpleNamespace(FLIGHT_MAC="24:0a:c4:00:00:01", GROUND_MAC="24:0a:c4:00:00:02")
        rep, _ = self.diag(full_bus(), rc=rc)
        self.assertEqual(rep.status("MAC"), [PASS])
        rep, _ = self.diag(full_bus(), rc=rc, mac=fakes.GROUND_MAC)
        self.assertEqual(rep.status("MAC"), [FAIL])

    def test_ina219_gated_is_info_not_measurement(self):
        rep, text = self.diag(full_bus())
        self.assertEqual(rep.status("INA219 data"), ["INFO"])
        self.assertIn("values NOT used", text)
        rep, _ = self.diag(full_bus(), INA219_BUS_CONNECTED=True, INA219_SHUNT_CONNECTED=True)
        self.assertEqual(rep.status("INA219 data"), [PASS])

    def test_no_machine_module(self):
        rep = run_diag(None, None, flight_cfg(), out=lambda s: None)
        self.assertEqual(rep.status("Platform"), [FAIL])

    def test_missing_espnow_reported(self):
        rep, _ = self.diag(full_bus(), espnow=False)
        self.assertEqual(rep.status("ESP-NOW module"), [FAIL])


if __name__ == "__main__":
    unittest.main()
