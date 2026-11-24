# Laptop test for esp32/apps/pin_toggle.py with fake machine/time modules.
# Checks the toggle sequence and that it stays inside its approved exception
# (D-022): open-drain only, GPIO21/22 only, always released at the end.
# Says nothing about hardware.
import contextlib
import io
import os
import runpy
import sys
import types
import unittest

import fakes

SCRIPT = os.path.join(fakes.ESP32, "apps", "pin_toggle.py")


def fake_modules(log, interrupt_after=None):
    m = types.ModuleType("machine")

    class Pin:
        IN = "IN"
        OPEN_DRAIN = "OPEN_DRAIN"

        def __init__(self, n, mode=None, pull=None, value=None):
            log.append(("init", n, mode, value))
            self.n = n

        def value(self, v=None):
            if v is not None:
                log.append(("set", self.n, v))
    m.Pin = Pin
    t = types.ModuleType("time")
    clock = [0]
    t.ticks_ms = lambda: clock[0]
    t.ticks_diff = lambda a, b: a - b

    def sleep_ms(ms):
        clock[0] += ms
        if interrupt_after is not None and clock[0] >= interrupt_after:
            raise KeyboardInterrupt
    t.sleep_ms = sleep_ms
    return {"machine": m, "time": t}


class PinToggle(unittest.TestCase):
    def run_toggle(self, interrupt_after=None):
        log = []
        mods = fake_modules(log, interrupt_after)
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        out = io.StringIO()
        try:
            g = runpy.run_path(SCRIPT, run_name="pin_toggle")
            with contextlib.redirect_stdout(out):
                g["main"]()
        finally:
            for k, v in saved.items():
                sys.modules[k] = v
        return log, out.getvalue()

    def test_toggles_both_lines_low_high_for_duration_then_releases(self):
        log, text = self.run_toggle()
        self.assertEqual(log[:2], [("init", 21, "OPEN_DRAIN", 1), ("init", 22, "OPEN_DRAIN", 1)])
        sets = [e for e in log if e[0] == "set"]
        body = sets[:-2]                                   # last two = final release
        self.assertEqual(len(body), 60 * 2)               # 60 s = 30 cycles x (2 pins LOW + 2 pins HIGH)
        for i in range(0, len(body), 4):
            self.assertEqual(body[i:i + 4], [("set", 21, 0), ("set", 22, 0), ("set", 21, 1), ("set", 22, 1)])
        self.assertEqual(sets[-2:], [("set", 21, 1), ("set", 22, 1)])
        self.assertEqual(log[-2:], [("init", 21, "IN", None), ("init", 22, "IN", None)])
        self.assertEqual(text.count("LOW\n"), 30)
        self.assertIn("stopped: both lines released", text)

    def test_ctrl_c_while_low_still_releases(self):
        log, text = self.run_toggle(interrupt_after=1000)   # interrupted during the first LOW
        sets = [e for e in log if e[0] == "set"]
        self.assertEqual(sets, [("set", 21, 0), ("set", 22, 0), ("set", 21, 1), ("set", 22, 1)])
        self.assertEqual(log[-2:], [("init", 21, "IN", None), ("init", 22, "IN", None)])

    def test_only_gpio21_22_and_only_open_drain(self):
        log, _ = self.run_toggle()
        self.assertEqual({e[1] for e in log}, {21, 22})
        self.assertEqual({e[2] for e in log if e[0] == "init"}, {"OPEN_DRAIN", "IN"})


if __name__ == "__main__":
    unittest.main()
