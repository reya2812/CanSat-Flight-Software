# test_esp32_hw_diag.py - LAPTOP tests for bringup/esp32_hw_diag.py (CPython, unittest).
#
# These tests run the diagnostic against a FAKE `machine` module and fake
# register maps. They check the script's logic: isolation of failures,
# PASS/FAIL/WARN/SKIP reporting, which registers it writes, and that the SD
# test stays disabled. They prove NOTHING about the real ESP32, the wiring or
# the sensors: that needs the bench run described in bringup/README.md.
#
# Run:  python3 -m unittest bringup/test_esp32_hw_diag.py      (from the repo root)
import os
import struct
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class FakePin:
    OUT = "OUT_SHOULD_NEVER_BE_USED"

    def __init__(self, n, *a, **k):
        if a or k:
            raise AssertionError("diagnostic configured a pin mode/value: %r %r" % (a, k))
        self.n = n


class FakeI2C:
    """Register-map devices: {addr: {reg: int}}. Missing address -> OSError, like a NACK."""

    def __init__(self, devices, fail_regs=()):
        self.devices = devices
        self.fail_regs = set(fail_regs)  # {(addr, reg)} raising OSError
        self.writes = []

    def scan(self):
        return sorted(self.devices)

    def _dev(self, addr, reg):
        if addr not in self.devices or (addr, reg) in self.fail_regs:
            raise OSError(19)  # ENODEV
        return self.devices[addr]

    def readfrom_mem(self, addr, reg, n):
        d = self._dev(addr, reg)
        if d.get("_word16"):  # INA219-style: each register address holds a 16-bit big-endian word
            v = d.get(reg, 0)
            return bytes([(v >> 8) & 0xFF, v & 0xFF])[:n]
        return bytes(d.get(reg + i, 0) & 0xFF for i in range(n))

    def writeto_mem(self, addr, reg, data):
        d = self._dev(addr, reg)
        self.writes.append((addr, reg, bytes(data)))
        for i, b in enumerate(data):
            d[reg + i] = b


def make_machine(i2c, sdcard_cls=None):
    m = types.ModuleType("machine")
    m.Pin = FakePin
    m.I2C = lambda *a, **k: i2c
    if sdcard_cls is not None:
        m.SDCard = sdcard_cls
    return m


# Bosch BMP280 datasheet worked example [ASSUMPTION: values recalled, verify in the PDF]:
# T1..P9 below, adc_T=519888 -> 25.08 C, adc_P=415148 -> ~100653.27 Pa.
EXAMPLE_CALIB = (27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)
EXAMPLE_ADC_T, EXAMPLE_ADC_P = 519888, 415148


def bmp280_regs(chip_id=0x58, adc_t=EXAMPLE_ADC_T, adc_p=EXAMPLE_ADC_P):
    r = {0xD0: chip_id, 0xF3: 0x00}
    raw = struct.pack("<HhhHhhhhhhhh", *EXAMPLE_CALIB)
    for i, b in enumerate(raw):
        r[0x88 + i] = b
    for reg, v in ((0xF7, adc_p), (0xFA, adc_t)):
        r[reg], r[reg + 1], r[reg + 2] = (v >> 12) & 0xFF, (v >> 4) & 0xFF, (v << 4) & 0xF0
    return r


def mpu_regs(who=0x71, accel=(0, 0, 16384), gyro=(131, -131, 0)):
    r = {0x75: who, 0x6B: 0x40, 0x1B: 0x00, 0x1C: 0x00}  # asleep at power-on
    vals = list(accel) + [1000] + list(gyro)
    for i, v in enumerate(vals):
        r[0x3B + 2 * i], r[0x3B + 2 * i + 1] = (v >> 8) & 0xFF, v & 0xFF
    return r


def ina_regs(cfg=0x399F, shunt=0x0000, bus=0x0000):
    # 16-bit registers [ASSUMPTION, recalled]: 0x00 config, 0x01 shunt voltage, 0x02 bus voltage
    return {"_word16": True, 0x00: cfg, 0x01: shunt, 0x02: bus}


def full_bus():
    return {0x68: mpu_regs(), 0x76: bmp280_regs(), 0x77: bmp280_regs(), 0x40: ina_regs()}


class DiagTest(unittest.TestCase):
    def load(self, i2c, sdcard_cls=None, sd_enabled=False):
        sys.modules["machine"] = make_machine(i2c, sdcard_cls)
        sys.path.insert(0, HERE)
        try:
            sys.modules.pop("esp32_hw_diag", None)
            import esp32_hw_diag as diag
        finally:
            sys.path.pop(0)
        diag.SD_SUPPLY_CONFIRMED = sd_enabled
        diag.sleep_ms = lambda ms: None
        return diag

    def tearDown(self):
        sys.modules.pop("machine", None)
        sys.modules.pop("esp32_hw_diag", None)

    def run_diag(self, diag):
        lines = []
        rep = diag.main(out=lines.append)
        return rep, "\n".join(lines)

    def status(self, rep, prefix):
        return [s for s, n, _ in rep.rows if n.startswith(prefix)]

    # ---- happy path ----
    def test_all_devices_identified_and_read(self):
        i2c = FakeI2C(full_bus())
        rep, text = self.run_diag(self.load(i2c))
        self.assertIn("0x40 0x68 0x76 0x77", text)  # hex addresses printed
        self.assertEqual(self.status(rep, "I2C scan"), ["PASS"])
        self.assertEqual(self.status(rep, "IMU @0x68"), ["PASS"])
        self.assertIn("MPU-9250", text)
        self.assertEqual(self.status(rep, "BMP280 @"), ["PASS", "PASS"])
        self.assertEqual(self.status(rep, "INA219 @0x40"), ["PASS"])
        self.assertEqual(self.status(rep, "SD card"), ["SKIP"])
        self.assertEqual(rep.counts()["FAIL"], 0)

    def test_bmp280_compensation_matches_recalled_datasheet_example(self):
        diag = self.load(FakeI2C({}))
        t, p = diag.bmp280_compensate(EXAMPLE_ADC_T, EXAMPLE_ADC_P, EXAMPLE_CALIB)
        self.assertAlmostEqual(t, 25.08, delta=0.01)
        self.assertAlmostEqual(p, 100653.27, delta=0.5)

    # ---- documented writes only ----
    def test_only_documented_writes_and_imu_restored(self):
        i2c = FakeI2C(full_bus())
        self.run_diag(self.load(i2c))
        self.assertEqual(i2c.writes, [(0x68, 0x6B, b"\x00"), (0x68, 0x6B, b"\x40"),   # wake, restore
                                      (0x76, 0xF4, b"\x25"), (0x77, 0xF4, b"\x25")])  # one forced read each
        self.assertFalse([w for w in i2c.writes if w[0] == 0x40])  # INA219 read-only

    def test_awake_imu_is_not_written(self):
        bus = full_bus()
        bus[0x68][0x6B] = 0x01
        i2c = FakeI2C(bus)
        self.run_diag(self.load(i2c))
        self.assertFalse([w for w in i2c.writes if w[0] == 0x68])

    # ---- isolation: one failure never stops the others ----
    def test_failing_device_does_not_stop_the_rest(self):
        i2c = FakeI2C(full_bus(), fail_regs={(0x68, 0x3B), (0x76, 0x88)})
        rep, _ = self.run_diag(self.load(i2c))
        self.assertEqual(self.status(rep, "IMU @0x68"), ["FAIL"])
        self.assertEqual(self.status(rep, "BMP280 @0x76"), ["FAIL"])
        self.assertEqual(self.status(rep, "BMP280 @0x77"), ["PASS"])
        self.assertEqual(self.status(rep, "INA219 @0x40"), ["PASS"])
        self.assertEqual(self.status(rep, "SD card"), ["SKIP"])
        self.assertIn((0x68, 0x6B, b"\x40"), i2c.writes)  # IMU restored even after the failed read

    def test_missing_devices_fail_individually(self):
        rep, _ = self.run_diag(self.load(FakeI2C({0x40: ina_regs()})))
        self.assertEqual(self.status(rep, "IMU"), ["FAIL"])
        self.assertIn("FAIL", self.status(rep, "BMP280"))
        self.assertEqual(self.status(rep, "INA219 @0x40"), ["PASS"])

    def test_empty_bus_fails_scan_and_skips_sensors(self):
        rep, _ = self.run_diag(self.load(FakeI2C({})))
        self.assertEqual(self.status(rep, "I2C scan"), ["FAIL"])
        self.assertEqual([s for s, n, _ in rep.rows if n in ("IMU", "BMP280", "INA219")], ["SKIP"] * 3)

    def test_i2c_init_error_is_reported(self):
        diag = self.load(FakeI2C({}))

        def boom(*a, **k):
            raise ValueError("bad pins")
        diag.machine.I2C = boom
        rep, _ = self.run_diag(diag)
        self.assertEqual(self.status(rep, "I2C init"), ["FAIL"])

    # ---- identification, not address assumptions ----
    def test_unknown_imu_identity_is_warned_with_raw_hex_and_still_read(self):
        bus = full_bus()
        bus[0x68][0x75] = 0x12
        i2c = FakeI2C(bus)
        rep, text = self.run_diag(self.load(i2c))
        self.assertEqual(self.status(rep, "IMU @0x68"), ["WARN"])
        self.assertIn("UNKNOWN: WHO_AM_I=0x12", text)
        self.assertIn("accel g:", text)  # not treated as unusable
        self.assertIn((0x68, 0x6B, b"\x40"), i2c.writes)  # still restored

    def test_unknown_bmp_chip_id_is_warned_not_measured(self):
        bus = full_bus()
        bus[0x76] = bmp280_regs(chip_id=0x60)  # a BME280 at a BMP280 address
        i2c = FakeI2C(bus)
        rep, _ = self.run_diag(self.load(i2c))
        self.assertEqual(self.status(rep, "BMP280 @0x76"), ["WARN"])
        self.assertNotIn((0x76, 0xF4, b"\x25"), i2c.writes)

    def test_ina219_non_default_config_is_warned(self):
        bus = full_bus()
        bus[0x40] = ina_regs(cfg=0x1234)
        rep, _ = self.run_diag(self.load(FakeI2C(bus)))
        self.assertEqual(self.status(rep, "INA219 @0x40"), ["WARN"])

    def test_ina219_registers_are_decoded_as_16_bit_words(self):
        bus = full_bus()
        bus[0x40] = ina_regs(shunt=0xFF38, bus=(1000 << 3) | 0x2)  # -200 x 10 uV; 1000 x 4 mV, CNVR=1
        rep, text = self.run_diag(self.load(FakeI2C(bus)))
        self.assertEqual(self.status(rep, "INA219 @0x40"), ["PASS"])
        self.assertIn("shunt_raw=-200 (-2.00 mV) bus=4.000 V CNVR=1 OVF=0", text)

    def test_bmp280_no_measurement_value_fails(self):
        bus = full_bus()
        bus[0x77] = bmp280_regs(adc_p=0x80000)
        rep, _ = self.run_diag(self.load(FakeI2C(bus)))
        self.assertEqual(self.status(rep, "BMP280 @0x77"), ["FAIL"])

    # ---- duplicate addresses ----
    def test_single_bmp280_warns_about_possible_shared_address(self):
        bus = full_bus()
        del bus[0x77]
        rep, text = self.run_diag(self.load(FakeI2C(bus)))
        self.assertEqual(self.status(rep, "BMP280 duplicates"), ["WARN"])
        self.assertIn("cannot be addressed independently", text)
        self.assertIn("CANNOT tell two devices at one address apart", text)
        self.assertIn("test each BMP280 alone", text)

    def test_two_bmp280s_report_that_mapping_needs_a_physical_check(self):
        rep, text = self.run_diag(self.load(FakeI2C(full_bus())))
        self.assertEqual(self.status(rep, "BMP280 mapping"), ["INFO"])
        self.assertIn("disconnect one", text)

    # ---- SD card ----
    def test_sd_disabled_by_default_never_touches_the_card(self):
        made = []

        class SD:
            def __init__(self, **k):
                made.append(k)
        diag = self.load(FakeI2C(full_bus()), SD)
        self.assertIs(diag.SD_SUPPLY_CONFIRMED, False)
        with open(os.path.join(HERE, "esp32_hw_diag.py")) as f:
            self.assertIn("SD_SUPPLY_CONFIRMED = False", f.read())
        rep, _ = self.run_diag(diag)
        self.assertEqual(self.status(rep, "SD card"), ["SKIP"])
        self.assertEqual(made, [])

    def test_sd_enabled_mounts_lists_unmounts_and_never_writes(self):
        calls = []

        class SD:
            def __init__(self, **k):
                calls.append(("init", sorted(k)))

            def deinit(self):
                calls.append(("deinit",))
        diag = self.load(FakeI2C(full_bus()), SD, sd_enabled=True)
        fake_os = types.SimpleNamespace(
            mount=lambda dev, p: calls.append(("mount", p)),
            listdir=lambda p: calls.append(("listdir", p)) or ["DCIM"],
            umount=lambda p: calls.append(("umount", p)))
        diag.os = fake_os  # only these three: any write/open/remove would raise AttributeError
        rep, _ = self.run_diag(diag)
        self.assertEqual(self.status(rep, "SD card"), ["PASS"])
        self.assertEqual([c[0] for c in calls], ["init", "mount", "listdir", "umount", "deinit"])

    def test_sd_enabled_without_driver_fails_clearly(self):
        rep, text = self.run_diag(self.load(FakeI2C(full_bus()), None, sd_enabled=True))
        self.assertEqual(self.status(rep, "SD card"), ["FAIL"])
        self.assertIn("no machine.SDCard", text)

    # ---- safety / portability ----
    def test_source_has_no_actuator_output_or_flight_imports(self):
        with open(os.path.join(HERE, "esp32_hw_diag.py")) as f:
            code = "\n".join(l.split("#")[0] for l in f.read().split("\n"))
        for tok in ("PWM", "Pin.OUT", "Pin.OPEN_DRAIN", "DAC", "UART", "cansat", "open(", ".write(",
                    "signed=", "struct.Struct"):
            self.assertNotIn(tok, code, tok)

    def test_runs_without_machine_and_reports_platform_fail(self):
        sys.modules.pop("machine", None)
        sys.path.insert(0, HERE)
        try:
            sys.modules.pop("esp32_hw_diag", None)
            import esp32_hw_diag as diag
        finally:
            sys.path.pop(0)
        rep = diag.main(out=lambda s: None)
        self.assertEqual(self.status(rep, "Platform"), ["FAIL"])


if __name__ == "__main__":
    unittest.main()
