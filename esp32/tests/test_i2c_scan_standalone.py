# Laptop tests for esp32/apps/i2c_scan_standalone.py with a FAKE machine
# module. They check the script's logic and safety (pins passed, error
# classes kept apart, no data writes, no output pins). They say nothing
# about the real board or wiring.
import os
import runpy
import types
import unittest

import fakes

SCRIPT = os.path.join(fakes.ESP32, "apps", "i2c_scan_standalone.py")


def make_machine(levels=None, devices=(), hw_init_error=None, scan_error=None, soft=True, log=None):
    """levels: {pull: (sda, scl)} returned by Pin.value() for that pull setting."""
    log = log if log is not None else []
    levels = levels or {None: (1, 1), "UP": (1, 1), "DOWN": (1, 1)}
    m = types.ModuleType("machine")

    class Pin:
        IN = "IN"
        PULL_UP = "UP"
        PULL_DOWN = "DOWN"

        def __init__(self, n, mode=None, pull=None):
            if mode not in (None, "IN"):
                raise AssertionError("output mode used: %r" % (mode,))
            self.n, self.pull = n, pull
            log.append(("pin", n, mode, pull))

        def value(self):
            sda, scl = levels.get(self.pull, (1, 1))
            return sda if self.n == 21 else scl

    class Bus:
        def __init__(self, kind, bid, scl, sda, freq):
            self.kind, self.bid, self.scl, self.sda, self.freq = kind, bid, scl.n, sda.n, freq
            log.append(("ctor", kind, bid, self.scl, self.sda, freq))

        def scan(self):
            log.append(("scan", self.kind, self.bid, self.freq))
            if scan_error:
                raise scan_error
            return list(devices)

        def __repr__(self):
            return "%s(%s, scl=%d, sda=%d, freq=%d)" % (self.kind, self.bid, self.scl, self.sda, self.freq)

        def __getattr__(self, name):   # any read/write method is a test failure
            raise AssertionError("bus method %s used" % name)

    def I2C(bid, scl=None, sda=None, freq=None):
        if hw_init_error and hw_init_error[0] == bid:
            raise hw_init_error[1]
        return Bus("I2C", bid, scl, sda, freq)
    m.Pin = Pin
    m.I2C = I2C
    if soft:
        m.SoftI2C = lambda scl=None, sda=None, freq=None: Bus("SoftI2C", "-", scl, sda, freq)
    return m, log


def load():
    return runpy.run_path(SCRIPT, run_name="i2c_scan_standalone")   # not __main__: does not auto-run


class StandaloneScan(unittest.TestCase):
    def run_scan(self, **kw):
        m, log = make_machine(**kw)
        out = []
        res = load()["main"](m, out.append)
        return res, log, "\n".join(out)

    def test_configured_pins_and_frequencies_reach_every_constructor(self):
        res, log, text = self.run_scan()
        ctors = [c for c in log if c[0] == "ctor"]
        self.assertEqual(len(ctors), 6)    # hw bus 0/1 x 2 freqs + soft x 2
        for c in ctors:
            self.assertEqual((c[3], c[4]), (22, 21))     # scl=22, sda=21
        self.assertEqual(sorted({c[5] for c in ctors}), [10000, 100000])
        self.assertIn("I2C(0, scl=22, sda=21, freq=100000)", text)

    def test_empty_scan_is_reported_as_empty_not_error(self):
        res, _, text = self.run_scan()
        self.assertTrue(all(r[1] == "EMPTY" for r in res))
        self.assertIn("EMPTY=6", text)
        self.assertNotIn("INIT_ERROR", text.split("== SUMMARY")[1])

    def test_init_error_kept_separate_from_scan_results(self):
        res, _, text = self.run_scan(hw_init_error=(1, ValueError("bad id")))
        states = {r[0].strip(): r[1] for r in res}
        self.assertEqual(states["hw I2C(1)  10000 Hz"], "INIT_ERROR")
        self.assertEqual(states["hw I2C(0) 100000 Hz"], "EMPTY")
        self.assertIn("ValueError('bad id')", text)

    def test_scan_error_kept_separate(self):
        res, _, text = self.run_scan(scan_error=OSError(116))
        self.assertTrue(all(r[1] == "SCAN_ERROR" for r in res))

    def test_devices_found(self):
        res, _, text = self.run_scan(devices=[0x68, 0x76, 0x40])
        self.assertIn("addresses seen on any scan: 0x40 0x68 0x76", text)

    def test_pull_down_interpretation(self):
        _, _, text = self.run_scan(levels={None: (1, 1), "UP": (1, 1), "DOWN": (1, 1)})
        self.assertIn("SDA stays HIGH against the internal pull-down", text)
        _, _, text = self.run_scan(levels={None: (1, 1), "UP": (1, 1), "DOWN": (0, 0)})
        self.assertIn("SDA drops LOW with the internal pull-down", text)
        self.assertIn("SCL drops LOW", text)
        _, _, text = self.run_scan(levels={None: (0, 1), "UP": (0, 1), "DOWN": (0, 0)})
        self.assertIn("something holds it low", text)

    def test_only_scan_traffic_no_reads_writes_or_outputs(self):
        _, log, _ = self.run_scan(devices=[0x68])
        self.assertEqual({c[0] for c in log}, {"pin", "ctor", "scan"})
        for c in log:
            if c[0] == "pin":
                self.assertIn(c[2], (None, "IN"))

    def test_without_softi2c_and_without_machine(self):
        res, _, text = self.run_scan(soft=False)
        self.assertEqual(len(res), 4)
        self.assertIn("SoftI2C not available", text)
        out = []
        self.assertEqual(load()["main"](None, out.append), [])   # laptop: no machine module
        self.assertIn("run this on the ESP32", "\n".join(out))

    def test_source_is_standalone_and_safe(self):
        from cansat import guards
        with open(SCRIPT) as f:
            src = f.read()
        code = "\n".join(c for _, c in guards.code_lines(src))
        for tok in ("import cs_", "from cs_", "flight_config", "radio_config", "Pin.OUT", "OPEN_DRAIN", "PWM",
                    "writeto", "readfrom", "open(", "SDCard", "network", "espnow"):
            self.assertNotIn(tok, code, tok)
        self.assertEqual(guards.actuator_violations(os.path.dirname(SCRIPT)), [])


if __name__ == "__main__":
    unittest.main()
