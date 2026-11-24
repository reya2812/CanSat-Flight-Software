# Smoke tests: execute the board programs under CPython with FAKE machine /
# network / espnow modules, to catch import/name errors and check the refusal
# paths. They say nothing about real MicroPython or hardware behaviour.
import contextlib
import io
import os
import runpy
import sys
import types
import unittest

import fakes
from fakes import FLIGHT_MAC, GROUND_MAC, FakeI2C, full_bus
import cs_util

APPS = os.path.join(fakes.ESP32, "apps")


class StopLoop(BaseException):
    pass


def fake_modules(own_mac, role, macs=True, sent=None):
    net = types.ModuleType("network")
    net.STA_IF = 0

    class WLAN:
        PM_NONE = 0

        def __init__(self, _):
            pass

        def active(self, v=None):
            return True

        def disconnect(self):
            pass

        def config(self, *a, **k):
            if a:
                return {"mac": own_mac, "channel": 1}[a[0]]
    net.WLAN = WLAN
    esp = types.ModuleType("espnow")
    esp.MAX_DATA_LEN = 250

    class ESPNow:
        peers_table = {}

        def active(self, v):
            pass

        def add_peer(self, mac):
            pass

        def send(self, mac, msg, sync=True):
            if sent is not None:
                sent.append(msg)
            return True

        def recv(self, timeout_ms=None):
            return (None, None)
    esp.ESPNow = ESPNow
    role_mod = types.ModuleType("board_role")
    role_mod.ROLE = role
    rc = types.ModuleType("radio_config")
    import radio_config as real
    for k in dir(real):
        if k.isupper():
            setattr(rc, k, getattr(real, k))
    if macs:
        rc.FLIGHT_MAC, rc.GROUND_MAC = cs_util.format_mac(FLIGHT_MAC), cs_util.format_mac(GROUND_MAC)
    machine = fakes.fake_machine(FakeI2C(full_bus()))
    machine.unique_id = lambda: b"\x01\x02"
    return {"network": net, "espnow": esp, "board_role": role_mod, "radio_config": rc, "machine": machine}


class AppSmoke(unittest.TestCase):
    def run_app(self, name, mods, loops=40):
        calls = [0]
        orig_sleep = cs_util.sleep_ms

        def sleep_ms(ms):
            calls[0] += 1
            if calls[0] >= loops:
                raise KeyboardInterrupt   # the apps catch this and stop cleanly
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        cs_util.sleep_ms = sleep_ms
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                runpy.run_path(os.path.join(APPS, name), run_name="__main__")
        finally:
            cs_util.sleep_ms = orig_sleep
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return out.getvalue()

    def test_flight_node_runs_and_sends(self):
        sent = []
        text = self.run_app("flight_node.py", fake_modules(FLIGHT_MAC, "FLIGHT", sent=sent))
        self.assertIn("own MAC 24:0a:c4:00:00:01", text)
        self.assertIn("boot_id", text)
        self.assertIn("stopped by user", text)
        self.assertGreaterEqual(len(sent), 1)

    def test_flight_node_refuses_without_macs_wrong_role_or_wrong_board(self):
        text = self.run_app("flight_node.py", fake_modules(FLIGHT_MAC, "FLIGHT", macs=False))
        self.assertIn("REFUSING TO START", text)
        text = self.run_app("flight_node.py", fake_modules(FLIGHT_MAC, "GROUND"))
        self.assertIn("REFUSING TO START", text)
        sent = []
        text = self.run_app("flight_node.py", fake_modules(GROUND_MAC, "FLIGHT", sent=sent))
        self.assertIn("GROUND board", text)
        self.assertEqual(sent, [])               # nothing transmitted by a refused node

    def test_flight_node_fsw_requested_is_refused_by_boot_checks(self):
        mods = fake_modules(FLIGHT_MAC, "FLIGHT")
        import flight_config as real
        fc = types.ModuleType("flight_config")
        for k in dir(real):
            if k.isupper():
                setattr(fc, k, getattr(real, k))
        fc.RUN_FLIGHT_SOFTWARE = True
        mods["flight_config"] = fc
        text = self.run_app("flight_node.py", mods)
        self.assertIn("FLIGHT SOFTWARE REFUSED TO START", text)

    def test_ground_node_runs_and_refuses_wrong_board(self):
        text = self.run_app("ground_node.py", fake_modules(GROUND_MAC, "GROUND"))
        self.assertIn("CanSat ground station", text)
        self.assertIn("NO_DATA", text)
        text = self.run_app("ground_node.py", fake_modules(FLIGHT_MAC, "GROUND"))
        self.assertIn("REFUSING TO START", text)

    def test_flight_diag_and_board_info_run(self):
        text = self.run_app("flight_diag.py", fake_modules(FLIGHT_MAC, "FLIGHT"), loops=10 ** 6)
        self.assertIn("== SUMMARY:", text)
        self.assertIn("matches radio_config.FLIGHT_MAC", text)
        text = self.run_app("board_info.py", fake_modules(FLIGHT_MAC, "FLIGHT"))
        self.assertIn("STA MAC       : 24:0a:c4:00:00:01", text)
        self.assertIn("espnow module : PRESENT", text)
        self.assertIn("this board IS the configured FLIGHT board", text)


if __name__ == "__main__":
    unittest.main()
