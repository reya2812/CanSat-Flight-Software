# Module 1: boot-time checks and the build scan refuse unsafe builds.
# These replace the C++ compile-time guards and are WEAKER (see README).
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from cansat import boot_checks, guards
from cansat.config import build_flags, hardware_config
from tests import cpp_ref

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scan_guards  # noqa: E402


class MockDriver:
    def apply(self, request):
        pass

    def is_physical(self):
        return False


class LyingDriver(MockDriver):
    def is_physical(self):
        return True


class BrokenDriver(MockDriver):
    def is_physical(self):
        raise RuntimeError("no answer")


def copy_tree():
    d = tempfile.mkdtemp(prefix="cansat_guard_")
    dst = os.path.join(d, "mp")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return d, dst


def plant(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(text)


def failed_rules(root):
    return [name for name, hits in scan_guards.scan(root) if hits]


class BootChecks(unittest.TestCase):
    def test_clean_laptop_tree_boots(self):
        self.assertEqual(boot_checks.run_boot_checks(ROOT, [MockDriver()], target_hardware=False), [])

    def test_hardware_target_refused_with_cpp_items_minus_buzzers(self):
        fails = boot_checks.run_boot_checks(ROOT, [], target_hardware=True)
        items = sorted(f.split(": ", 1)[1] for f in fails if f.startswith("B4 unresolved"))
        h = cpp_ref.read("include/config/HardwareConfig.h")
        cpp = []
        for line in h.split("\n"):
            s = line.strip()
            if s.startswith("static_assert(") and "kPinTbd" in s or (s.startswith("static_assert(kHc12UartBaud")):
                name = s[len("static_assert("):].split("!=")[0].split("||")[-1].strip()
                cpp.append(name)
        cpp = sorted("HC12_UART_BAUD" if n == "kHc12UartBaud" else n for n in cpp)
        cpp = [n for n in cpp if n != "PIN_HC12_SET"]  # SET pin only required when used (both)
        self.assertIn("PIN_BUZZER_1", cpp)  # C++ still requires them
        expected = [n for n in cpp if not n.startswith("PIN_BUZZER_")]  # D-018: not until buzzer code exists
        self.assertEqual(items, expected)
        self.assertFalse(any("BUZZER" in f for f in fails))
        self.assertTrue(any("flight parameters not approved" in f for f in fails))
        with self.assertRaises(boot_checks.BootRefused):
            boot_checks.enforce_boot_checks(ROOT, [], target_hardware=True)

    def test_physical_flag_refused(self):
        old = build_flags.PHYSICAL_ACTUATORS_ENABLED
        build_flags.PHYSICAL_ACTUATORS_ENABLED = True
        try:
            fails = boot_checks.run_boot_checks(ROOT, [], target_hardware=False)
        finally:
            build_flags.PHYSICAL_ACTUATORS_ENABLED = old
        self.assertTrue(any(f.startswith("B1") for f in fails))

    def test_physical_or_unanswering_driver_refused(self):
        for d in (LyingDriver(), BrokenDriver()):
            fails = boot_checks.run_boot_checks(ROOT, [MockDriver(), d], target_hardware=False)
            self.assertTrue(any(f.startswith("B2") for f in fails), type(d).__name__)
            with self.assertRaises(boot_checks.BootRefused):
                boot_checks.enforce_boot_checks(ROOT, [d], target_hardware=False)

    def test_actuator_code_in_package_refused(self):
        tmp, root = copy_tree()
        try:
            for i, line in enumerate(("from machine import PWM\n", "p = Pin(PIN_SERVO_1, Pin.OUT)\n",
                                      "dac = machine.DAC(x)\n")):
                plant(root, "cansat/core/evil%d.py" % i, line)
            fails = boot_checks.run_boot_checks(root, [], target_hardware=False)
            flagged = set(f.split(":")[0][3:] for f in fails if f.startswith("B3"))
            self.assertEqual(flagged, {"cansat/core/evil0.py", "cansat/core/evil1.py", "cansat/core/evil2.py"})
        finally:
            shutil.rmtree(tmp)

    def test_physical_is_physical_in_package_refused(self):
        tmp, root = copy_tree()
        try:
            plant(root, "cansat/core/servo.py",
                  "class S:\n    def is_physical(self):\n        return True\n")
            fails = boot_checks.run_boot_checks(root, [], target_hardware=False)
            self.assertTrue(any("is_physical() returns True" in f for f in fails))
        finally:
            shutil.rmtree(tmp)

    def test_unscannable_mpy_refused(self):
        tmp, root = copy_tree()
        try:
            plant(root, "cansat/core/blob.mpy", "x")
            fails = boot_checks.run_boot_checks(root, [], target_hardware=False)
            self.assertTrue(any("unscannable" in f for f in fails))
        finally:
            shutil.rmtree(tmp)

    def test_comments_are_not_code(self):
        lines = guards.code_lines("x = 1  # PWM\n# Pin.OUT\n")
        self.assertEqual(lines, [(1, "x = 1  ")])


class OutputWhitelist(unittest.TestCase):
    """Module 1 review item 2: named non-actuator outputs in the hardware layer only."""

    def violations(self, rel, line):
        tmp, root = copy_tree()
        try:
            plant(root, rel, line)
            return [v for v in guards.actuator_violations(root) if v.startswith(rel + ":")]
        finally:
            shutil.rmtree(tmp)

    def test_sd_cs_and_hc12_set_allowed_in_hardware_layer(self):
        for name in ("PIN_SD_CS", "PIN_HC12_SET"):
            for tok in ("Pin.OUT", "Pin.OPEN_DRAIN"):
                line = "p = Pin(hardware_config.%s, %s)\n" % (name, tok)
                self.assertEqual(self.violations("cansat/hal_mp/sd.py", line), [], line)

    def test_refused_cases(self):
        cases = [
            ("cansat/core/sd.py", "p = Pin(hardware_config.PIN_SD_CS, Pin.OUT)\n", "outside"),
            ("cansat/hal_mp/x.py", "p = Pin(hardware_config.PIN_SERVO_1, Pin.OUT)\n", "actuator pin"),
            ("cansat/hal_mp/x.py", "p = Pin(hardware_config.PIN_BUZZER_2, Pin.OPEN_DRAIN)\n", "actuator pin"),
            ("cansat/hal_mp/x.py", "p = Pin(some_pin, Pin.OUT)\n", "exactly one"),
            ("cansat/hal_mp/x.py", "p = Pin(hw.PIN_SD_CS if a else hw.PIN_HC12_SET, Pin.OUT)\n", "exactly one"),
            ("cansat/hal_mp/x.py", "p = Pin(" + "5, Pin.OUT)  # PIN_SD_CS\n", "exactly one"),
            ("cansat/hal_mp/x.py", "b = hardware_config.PIN_BUZZER_1\n", "actuator pin"),
            ("cansat/hal_mp/x.py", "s = PWM(Pin(hardware_config.PIN_SD_CS))\n", "'PWM'"),
            ("cansat/hal_mp/x.py", "d = machine.DAC(x)\n", "DAC"),
        ]
        for rel, line, frag in cases:
            with self.subTest(line=line):
                v = self.violations(rel, line)
                self.assertTrue(any(frag in x for x in v), (frag, v))

    def test_split_line_is_refused(self):
        v = self.violations("cansat/hal_mp/x.py", "p = Pin(\n    hardware_config.PIN_SD_CS,\n    Pin.OUT)\n")
        self.assertTrue(v)

    def test_boot_refuses_output_pin_sharing_actuator_gpio(self):
        # SYNTHETIC in-memory values for this test only; hardware_config.py is not edited.
        saved = {n: getattr(hardware_config, n) for n in ("PIN_SD_CS", "PIN_HC12_SET", "PIN_SERVO_1")}
        try:
            self.assertEqual(boot_checks.output_pin_conflicts(), [])
            hardware_config.PIN_SD_CS = 5
            hardware_config.PIN_SERVO_1 = 5
            self.assertEqual(len(boot_checks.output_pin_conflicts()), 1)
            hardware_config.PIN_SERVO_1 = saved["PIN_SERVO_1"]
            hardware_config.PIN_HC12_SET = 5
            self.assertEqual(len(boot_checks.output_pin_conflicts()), 1)
            fails = boot_checks.run_boot_checks(ROOT, [], target_hardware=False)
            self.assertTrue(any(f.startswith("B5") for f in fails))
        finally:
            for n, v in saved.items():
                setattr(hardware_config, n, v)


class ScanGuards(unittest.TestCase):
    def test_clean_tree_passes(self):
        self.assertEqual(failed_rules(ROOT), [])
        with redirect_stdout(StringIO()):
            rc = scan_guards.main(["scan_guards.py", ROOT])
        self.assertEqual(rc, 0)

    def check_planted(self, rel, text, expect_fragment):
        tmp, root = copy_tree()
        try:
            plant(root, rel, text)
            failed = failed_rules(root)
            self.assertTrue(any(expect_fragment in f for f in failed), (expect_fragment, failed))
            with redirect_stdout(StringIO()):
                rc = scan_guards.main(["scan_guards.py", root])
            self.assertEqual(rc, 1)
        finally:
            shutil.rmtree(tmp)

    def test_each_rule_catches_a_planted_violation(self):
        cases = [
            ("cansat/core/x.py", "pwm = PWM(p)\n", "no actuator output code"),
            ("cansat/core/x.py", "drv.apply(1)\n", "only cansat/core/actuator_manager.py"),
            ("cansat/core/x.py", "class Src(ConnectionAssessmentSource):\n    pass\n", "ConnectionAssessmentSource"),
            ("cansat/core/x.mpy", "x", "no precompiled .mpy"),
            ("cansat/core/x.py", "import enum\n", "CPython-only"),
            ("cansat/core/x.py", "from typing import List\n", "CPython-only"),
            ("cansat/core/x.py", "import machine\n", "MicroPython-only"),
            ("tests/x.py", "import esp32\n", "MicroPython-only"),
            ("cansat/core/x.py", "import time\n", "does not import time"),
            ("cansat/core/x.py", "def f(a) -> int:\n    return a\n", "annotations"),
            ("cansat/hal_mp/x.py", "\n", "no hardware driver package"),
            ("cansat/config/hardware_config.py", "PIN_I2C_SDA = 21\n", "every pin in hardware_config.py"),
            ("cansat/config/hardware_config.py", "HC12_UART_BAUD = 9600\n", "every pin in hardware_config.py"),
            ("cansat/core/x.py", "p = Pin(" + "4)\n", "no Pin(<number>)"),  # split so this file stays clean
            ("cansat/core/x.py", "SYNTHETIC_DEBOUNCE_MS = 5\n", "no SYNTHETIC_"),
            ("cansat/config/x.py", "p.set(5)\n", "never assigns a Param"),
            ("cansat/core/x.py", "def broken(:\n", "parses"),
            ("cansat/core/x.py", "S = struct.Struct('<f')\n", "struct.Struct"),
            ("cansat/core/x.py", "v = p.get()[1]\n", "Param.get()"),
            ("cansat/sim/x.py", "from cansat.core.actuator_manager import ActuatorManager\n", "simulator does not reference"),
            ("cansat/core/x.py", "from cansat.sim.sim_math import powf\n", "flight code never imports"),
            ("cansat/core/x.py", "from cansat.mock.rng import Rng\n", "flight code never imports"),
            ("cansat/hal/x.py", "import ctypes\n", "flight code never imports"),
            ("cansat/core/x.py", "_, v = p.get()\n", "Param.get()"),
            ("cansat/core/x.py", "if p.get():\n    pass\n", "Param.get()"),
            ("cansat/core/flight_state_manager.py", "x = T.BaroSample()\n", "does not reference sensors"),
            ("cansat/core/flight_software.py", "from cansat.hal.interfaces import ActuatorDriver\n", "actuator path"),
        ]
        for rel, text, frag in cases:
            with self.subTest(rule=frag, file=rel):
                self.check_planted(rel, text, frag)

    def test_physical_flag_literal(self):
        tmp, root = copy_tree()
        try:
            p = os.path.join(root, "cansat/config/build_flags.py")
            with open(p) as f:
                s = f.read()
            with open(p, "w") as f:
                f.write(s.replace("PHYSICAL_ACTUATORS_ENABLED = False", "PHYSICAL_ACTUATORS_ENABLED = True"))
            self.assertTrue(any("PHYSICAL_ACTUATORS_ENABLED" in f for f in failed_rules(root)))
        finally:
            shutil.rmtree(tmp)

    def test_synthetic_allowed_in_tests_and_sim(self):
        tmp, root = copy_tree()
        try:
            plant(root, "cansat/sim/x.py", "SYNTHETIC_A = 1\n")
            plant(root, "tests/x.py", "SYNTHETIC_B = 1\n")
            self.assertEqual(failed_rules(root), [])
        finally:
            shutil.rmtree(tmp)


class HardwareConfigValues(unittest.TestCase):
    def test_all_pins_tbd_and_addresses_match_cpp(self):
        for name in dir(hardware_config):
            if name.startswith("PIN_") and name != "PIN_TBD":
                self.assertEqual(getattr(hardware_config, name), hardware_config.PIN_TBD, name)
        self.assertEqual(hardware_config.HC12_UART_BAUD, 0)
        self.assertFalse(hardware_config.HC12_SET_PIN_USED)
        self.assertFalse(hardware_config.required_hardware_resolved())
        h = cpp_ref.read("include/config/HardwareConfig.h")
        for cpp, py in (("kBmp280AddrCandidateA = 0x76", hardware_config.BMP280_ADDR_CANDIDATE_A),
                        ("kBmp280AddrCandidateB = 0x77", hardware_config.BMP280_ADDR_CANDIDATE_B),
                        ("kMpu6050Addr = 0x68", hardware_config.MPU6050_ADDR),
                        ("kIna219Addr = 0x40", hardware_config.INA219_ADDR),
                        ("kGroundStationUsbBaud = 115200", hardware_config.GROUND_STATION_USB_BAUD)):
            self.assertIn(cpp, h)
            self.assertEqual(int(cpp.split("= ")[1], 0), py)

    def test_build_flags_safe_defaults(self):
        self.assertIs(build_flags.PHYSICAL_ACTUATORS_ENABLED, False)
        self.assertIs(build_flags.TARGET_HARDWARE, False)
        self.assertIs(build_flags.FLIGHT_PARAMS_APPROVED, False)


if __name__ == "__main__":
    unittest.main()
