# Laptop tests for esp32/apps/ina219_test.py with a fake machine module and a
# fake INA219. They check the decoding and that the script never writes to the
# chip. They say nothing about the real sensor.
import os
import runpy
import types
import unittest

import fakes

SCRIPT = os.path.join(fakes.ESP32, "apps", "ina219_test.py")


def fake_machine(found=(0x40,), cfg=0x399F, shunt=1234, bus=(1250 << 3) | 0x02, log=None):
    log = log if log is not None else []
    regs = {0x00: cfg, 0x01: shunt & 0xFFFF, 0x02: bus}
    m = types.ModuleType("machine")
    m.Pin = lambda n: n

    class Bus:
        def __init__(self, bid, scl=None, sda=None, freq=None):
            log.append(("ctor", bid, scl, sda, freq))

        def scan(self):
            return list(found)

        def readfrom_mem(self, addr, r, n):
            return bytes([regs[r] >> 8, regs[r] & 0xFF])

        def __getattr__(self, name):          # any write method is a test failure
            raise AssertionError("bus method %s used" % name)
    m.I2C = Bus
    return m, log


class Ina219Test(unittest.TestCase):
    def run_app(self, **kw):
        m, log = fake_machine(**kw)
        g = runpy.run_path(SCRIPT, run_name="ina219_test")
        clock = [0]
        t = types.ModuleType("time")
        t.ticks_ms = lambda: clock[0]
        t.ticks_diff = lambda a, b: a - b

        def sleep_ms(ms):
            clock[0] += ms
        t.sleep_ms = sleep_ms
        g["main"].__globals__["time"] = t
        g["main"].__globals__["DURATION_S"] = 1
        out = []
        n = g["main"](m, out.append)
        return n, log, "\n".join(out)

    def test_decodes_bus_shunt_current(self):
        n, log, text = self.run_app()
        self.assertEqual(log[0], ("ctor", 0, 22, 21, 100000))
        self.assertIn("(INA219 power-on default)", text)
        self.assertIn("  5.000  |    12.34 |      123.4 |    617.0 | -", text)   # 1250*4 mV; 1234*10 uV / 0.1 ohm
        self.assertEqual(n, 4)

    def test_negative_shunt_overflow_and_range_flags(self):
        _, _, text = self.run_app(cfg=0x219F, shunt=-4000, bus=(100 << 3) | 0x01)   # PGA bits 00: +/-40 mV
        self.assertIn("shunt range +/-40 mV", text)
        self.assertIn("-40.00", text)
        self.assertIn("OVERFLOW shunt at range limit", text)

    def test_not_found_and_non_default_config(self):
        n, _, text = self.run_app(found=(0x68,))
        self.assertIsNone(n)
        self.assertIn("no INA219", text)
        _, _, text = self.run_app(cfg=0x1234)
        self.assertIn("NOT the INA219 default", text)

    def test_source_never_writes(self):
        with open(SCRIPT) as f:
            src = f.read()
        for tok in ("writeto", "Pin.OUT", "OPEN_DRAIN", "PWM"):
            self.assertNotIn(tok, src)


if __name__ == "__main__":
    unittest.main()
