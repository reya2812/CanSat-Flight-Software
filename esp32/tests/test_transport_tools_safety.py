# ESP-NOW transport (fake network/espnow modules), laptop tools (fake
# subprocess), identity checks, and the actuator-safety scan of esp32/.
# LOGIC ONLY: the real espnow API is [ASSUMPTION] until run on the boards.
import contextlib
import io
import json
import os
import tempfile
import types
import unittest

import fakes
from fakes import FLIGHT_MAC, GROUND_MAC
import cs_util as U
from cs_espnow import EspNowTransport


class FakeNetwork:
    STA_IF = 0

    def __init__(self, mac=FLIGHT_MAC):
        self.calls = []
        net = self

        class WLAN:
            PM_NONE = 0

            def __init__(self, _):
                pass

            def active(self, v=None):
                net.calls.append(("active", v))
                return True

            def disconnect(self):
                net.calls.append(("disconnect",))

            def config(self, *a, **k):
                if a:
                    return {"mac": mac, "channel": 6}[a[0]]
                net.calls.append(("config", k))
        self.WLAN = WLAN


class FakeEspNowModule:
    def __init__(self):
        self.instances = []
        mod = self

        class ESPNow:
            def __init__(self):
                self.peers = []
                self.active_calls = []
                self.sent = []
                self.rx = []
                self.peers_table = {GROUND_MAC: [-63, 1234]}
                mod.instances.append(self)

            def active(self, v):
                self.active_calls.append(v)

            def add_peer(self, mac):
                if mac in self.peers:
                    raise OSError("ESP_ERR_ESPNOW_EXIST")
                self.peers.append(mac)

            def send(self, mac, msg, sync=True):
                self.sent.append((mac, msg, sync))
                return True

            def recv(self, timeout_ms=None):
                self.last_timeout = timeout_ms
                return self.rx.pop(0) if self.rx else (None, None)

            def stats(self):
                return (1, 1, 0, 0, 0)
        self.ESPNow = ESPNow


class Transport(unittest.TestCase):
    def make(self):
        net, esp = FakeNetwork(), FakeEspNowModule()
        return EspNowTransport(6, [GROUND_MAC], net, esp), net, esp

    def test_station_mode_no_access_point_and_peer_registered(self):
        t, net, esp = self.make()
        self.assertIn(("active", True), net.calls)
        self.assertIn(("disconnect",), net.calls)
        self.assertIn(("config", {"channel": 6}), net.calls)
        self.assertNotIn("connect", [c[0] for c in net.calls])
        e = esp.instances[0]
        self.assertEqual(e.active_calls, [True])
        self.assertEqual(e.peers, [GROUND_MAC])
        self.assertEqual(t.own_mac(), FLIGHT_MAC)

    def test_send_is_non_blocking_and_recv_polls(self):
        t, _, esp = self.make()
        e = esp.instances[0]
        self.assertTrue(t.send(GROUND_MAC, b"x"))
        self.assertIs(e.sent[0][2], False)          # sync=False: never waits for the peer
        self.assertIsNone(t.recv())
        self.assertEqual(e.last_timeout, 0)         # timeout 0: never blocks
        e.rx.append((bytearray(GROUND_MAC), bytearray(b"hello")))
        self.assertEqual(t.recv(), (GROUND_MAC, b"hello"))
        self.assertEqual(t.rssi(GROUND_MAC), -63)
        self.assertIsNone(t.rssi(b"\x02" * 6))

    def test_recover_reinitialises_and_tolerates_existing_peer(self):
        t, _, esp = self.make()
        t.recover()
        self.assertEqual(esp.instances[0].active_calls, [True, False])
        self.assertEqual(esp.instances[1].peers, [GROUND_MAC])


class Identity(unittest.TestCase):
    RC = types.SimpleNamespace(FLIGHT_MAC="24:0a:c4:00:00:01", GROUND_MAC="24:0a:c4:00:00:02")

    def test_mac_parsing(self):
        self.assertEqual(U.parse_mac("24:0A:C4:00:00:01"), FLIGHT_MAC)
        self.assertEqual(U.parse_mac("24-0a-c4-00-00-01"), FLIGHT_MAC)
        for bad in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", "01:00:5e:00:00:01", "24:0a:c4", "zz:0a:c4:00:00:01",
                    "240:a:c4:00:00:01", None):
            with self.assertRaises(U.MacError):
                U.parse_mac(bad)

    def test_unset_or_equal_macs_refused(self):
        with self.assertRaises(U.MacError):
            U.check_role_macs(None, "24:0a:c4:00:00:02")
        with self.assertRaises(U.MacError):
            U.check_role_macs("24:0a:c4:00:00:01", "24:0A:C4:00:00:01")

    def test_node_refuses_wrong_board_or_role(self):
        own, peer = U.check_node_identity(U.ROLE_FLIGHT, "FLIGHT", FLIGHT_MAC, self.RC)
        self.assertEqual((own, peer), (FLIGHT_MAC, GROUND_MAC))
        with self.assertRaises(U.MacError) as cm:
            U.check_node_identity(U.ROLE_FLIGHT, "FLIGHT", GROUND_MAC, self.RC)
        self.assertIn("GROUND board", str(cm.exception))
        with self.assertRaises(U.MacError):
            U.check_node_identity(U.ROLE_GROUND, "FLIGHT", GROUND_MAC, self.RC)   # deployed as flight
        with self.assertRaises(U.MacError):
            U.check_node_identity(U.ROLE_GROUND, None, GROUND_MAC, self.RC)       # never deployed

    def test_shipped_radio_config_has_the_confirmed_board_mapping(self):
        # user-confirmed 2026-11-24: flight = board wired to the sensors
        import radio_config
        f, g = U.check_role_macs(radio_config.FLIGHT_MAC, radio_config.GROUND_MAC)
        self.assertEqual(U.format_mac(f), "4c:c3:82:ec:c9:d8")
        self.assertEqual(U.format_mac(g), "70:4b:ca:02:ce:30")

    def test_uptime_accumulates_across_tick_wrap(self):
        up = U.Uptime(U.TICKS_PERIOD - 100)
        self.assertEqual(up.update(50), 150)
        self.assertEqual(up.update(50 + 1000), 1150)
        self.assertEqual(up.update(40), 1150)        # tick going backwards is ignored


# ---------------------------------------------------------------------------
import esp32tool_common as C          # noqa: E402
import flash_micropython as FM        # noqa: E402
import deploy as D                    # noqa: E402

ESPTOOL_V5 = """esptool v5.6.0
Connected to ESP32 on /dev/cu.usbserial-0001:
Chip type:          ESP32-D0WD-V3 (revision v3.1)
Features:           Wi-Fi, BT, Dual Core, 240MHz
MAC:                24:0a:c4:00:00:01
Hard resetting via RTS pin...
"""
ESPTOOL_V4 = """esptool.py v4.7.0
Detecting chip type... ESP32
Chip is ESP32-D0WDQ6 (revision v1.0)
MAC: 24:0a:c4:00:00:02
Hard resetting via RTS pin...
"""
ESPTOOL_S3 = "Chip type:          ESP32-S3 (QFN56) (revision v0.2)\nMAC:                24:0a:c4:00:00:01\n"


class FakeRun:
    def __init__(self, identity_text=ESPTOOL_V5, mac_sequence=None):
        self.calls = []
        self.identity_text = identity_text
        self.mac_sequence = list(mac_sequence or [])

    def __call__(self, cmd, **k):
        self.calls.append(cmd)
        out = ""
        if "version" in cmd:
            out = "esptool v5.6.0"
        elif "read-mac" in cmd or "read_mac" in cmd:
            out = self.identity_text
            if self.mac_sequence:
                out = out.replace("24:0a:c4:00:00:01", self.mac_sequence.pop(0))
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    def ran(self, word):
        return [c for c in self.calls if word in c]


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fw = os.path.join(self.tmp.name, "ESP32_GENERIC-20260101-v1.29.0.bin")
        with open(self.fw, "wb") as f:
            f.write(b"\xe9" + b"\x00" * (1600 * 1024))
        self.records = os.path.join(self.tmp.name, "records.jsonl")
        self.rc_orig = C.load_radio_config
        C.load_radio_config = lambda path=None: types.SimpleNamespace(FLIGHT_MAC=None, GROUND_MAC=None)

    def tearDown(self):
        C.load_radio_config = self.rc_orig
        self.tmp.cleanup()

    def flash(self, *extra, run=None, typed=""):
        run = run or FakeRun()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = FM.main(["--port", "/dev/cu.fake", "--role", "flight", "--firmware", self.fw] + list(extra),
                         run=run, input_fn=lambda prompt: typed, records_path=self.records)
        return rc, run

    def test_parse_esptool_output_v4_v5(self):
        self.assertEqual(C.parse_esptool_identity(ESPTOOL_V5), ("ESP32-D0WD-V3 (revision v3.1)", FLIGHT_MAC))
        self.assertEqual(C.parse_esptool_identity(ESPTOOL_V4), ("ESP32-D0WDQ6 (revision v1.0)", GROUND_MAC))
        self.assertTrue(C.is_classic_esp32("ESP32-D0WD-V3 (revision v3.1)"))
        self.assertFalse(C.is_classic_esp32("ESP32-S3 (QFN56) (revision v0.2)"))
        self.assertFalse(C.is_classic_esp32(None))

    def test_firmware_name_checks(self):
        for bad in ("ESP32_GENERIC_S3-20260101-v1.29.0.bin", "ESP32_GENERIC-SPIRAM-20260101-v1.29.0.bin",
                    "ESP32_GENERIC-20260101-v1.30.0-preview.12.bin", "firmware.bin"):
            p = os.path.join(self.tmp.name, bad)
            with open(p, "wb") as f:
                f.write(b"\x00" * (1600 * 1024))
            with self.assertRaises(C.ToolError):
                FM.check_firmware(p)
        name, size, digest = FM.check_firmware(self.fw)
        with self.assertRaises(C.ToolError):
            FM.check_firmware(self.fw, sha256="00" * 32)

    def test_dry_run_by_default_never_erases(self):
        rc, run = self.flash()
        self.assertEqual(rc, 0)
        self.assertEqual(run.ran("erase-flash"), [])
        self.assertEqual(run.ran("write-flash"), [])
        self.assertFalse(os.path.exists(self.records))

    def test_wrong_confirmation_aborts(self):
        rc, run = self.flash("--execute", typed="yes")
        self.assertEqual(rc, 3)
        self.assertEqual(run.ran("erase-flash"), [])

    def test_confirmed_flash_erases_writes_and_records(self):
        rc, run = self.flash("--execute", typed="FLASH FLIGHT 00:00:01")
        self.assertEqual(rc, 0)
        erase, = run.ran("erase-flash")
        write, = run.ran("write-flash")
        self.assertEqual(write[-3:], ["-z", "0x1000", self.fw])
        self.assertIn("esp32", erase)
        with open(self.records) as f:
            rec = json.loads(f.read())
        self.assertEqual((rec["role"], rec["mac"], rec["event"]), ("flight", "24:0a:c4:00:00:01", "flash"))

    def test_board_swapped_after_confirmation_aborts(self):
        run = FakeRun(mac_sequence=["24:0a:c4:00:00:01", "24:0a:c4:00:00:09"])
        rc, run = self.flash("--execute", typed="FLASH FLIGHT 00:00:01", run=run)
        self.assertEqual(rc, 2)
        self.assertEqual(run.ran("erase-flash"), [])

    def test_refuses_non_esp32_chip(self):
        rc, run = self.flash("--execute", typed="FLASH FLIGHT 00:00:01", run=FakeRun(ESPTOOL_S3))
        self.assertEqual(rc, 2)
        self.assertEqual(run.ran("erase-flash"), [])

    def test_refuses_the_other_roles_board(self):
        C.load_radio_config = lambda path=None: types.SimpleNamespace(FLIGHT_MAC=None, GROUND_MAC="24:0a:c4:00:00:01")
        rc, run = self.flash("--execute", typed="FLASH FLIGHT 00:00:01")
        self.assertEqual(rc, 2)
        self.assertEqual(run.ran("erase-flash"), [])

    def test_same_firmware_on_both_boards(self):
        C.append_record({"event": "flash", "role": "ground", "sha256": "ab" * 32, "firmware": "other.bin"},
                        self.records)
        rc, run = self.flash()
        self.assertEqual(rc, 2)
        rc, run = self.flash("--allow-different-firmware")
        self.assertEqual(rc, 0)

    def test_esptool_v4_command_names(self):
        self.assertEqual(C.esptool_cmd("erase-flash", 4), "erase_flash")
        self.assertEqual(C.esptool_cmd("erase-flash", 5), "erase-flash")


class Deploy(unittest.TestCase):
    MP_OUT = "MAC=24:0a:c4:00:00:01\nVER=3.4.0; MicroPython v1.29.0\nESPNOW=1\nROLE=\n"

    def setUp(self):
        self.rc_orig = C.load_radio_config
        C.load_radio_config = lambda path=None: types.SimpleNamespace(FLIGHT_MAC="24:0a:c4:00:00:01",
                                                                      GROUND_MAC="24:0a:c4:00:00:02")
        self.rec_orig = C.append_record
        C.append_record = lambda *a, **k: None

    def tearDown(self):
        C.load_radio_config = self.rc_orig
        C.append_record = self.rec_orig

    def run_deploy(self, role, out=None, extra=()):
        calls = []

        def run(cmd, **k):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=0, stdout=out or self.MP_OUT, stderr="")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = D.main(["--role", role, "--port", "/dev/cu.fake"] + list(extra), run=run)
        return rc, calls

    def test_flight_deploy_copies_role_files_only(self):
        rc, calls = self.run_deploy("flight", extra=["--autorun"])
        self.assertEqual(rc, 0)
        cp = calls[-1]
        dsts = [cp[i + 1] for i, w in enumerate(cp) if w.startswith("/") and i + 1 < len(cp) and cp[i + 1].startswith(":")]
        self.assertIn(":lib/cs_sensors.py", dsts)
        self.assertIn(":board_role.py", dsts)
        self.assertIn(":main.py", dsts)
        self.assertNotIn(":lib/cs_display.py", dsts)
        self.assertFalse(any("cansat" in d for d in dsts))

    def test_with_fsw_copies_no_mock_or_sim(self):
        rc, calls = self.run_deploy("flight", extra=["--with-fsw", "--dry-run"])
        self.assertEqual(rc, 0)
        pairs = D.file_plan("flight", False, True, __file__)
        dsts = [d for _, d in pairs]
        self.assertIn("cansat/boot_checks.py", dsts)
        self.assertIn("cansat/core/flight_software.py", dsts)
        self.assertFalse(any("/mock/" in d or "/sim/" in d for d in dsts))
        with self.assertRaises(C.ToolError):
            D.file_plan("ground", False, True, __file__)

    def test_refuses_wrong_board(self):
        rc, calls = self.run_deploy("ground")
        self.assertEqual(rc, 2)
        self.assertEqual(len(calls), 1)    # identity query only, nothing copied

    def test_refuses_without_espnow_or_without_macs(self):
        rc, calls = self.run_deploy("flight", out=self.MP_OUT.replace("ESPNOW=1", "ESPNOW=0"))
        self.assertEqual(rc, 2)
        C.load_radio_config = lambda path=None: types.SimpleNamespace(FLIGHT_MAC=None, GROUND_MAC=None)
        rc, calls = self.run_deploy("flight")
        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])

    def test_dry_run_copies_nothing(self):
        rc, calls = self.run_deploy("flight", extra=["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)

    def test_role_file_text(self):
        ns = {}
        exec(D.role_file_text("flight", FLIGHT_MAC), ns)
        self.assertEqual(ns["ROLE"], "FLIGHT")


# ---------------------------------------------------------------------------
class SafetyScan(unittest.TestCase):
    """Extends (does not replace) the cansat guard rules to the esp32/ tree."""

    def test_no_actuator_output_code_in_esp32_tree(self):
        from cansat import guards
        v = guards.actuator_violations(fakes.ESP32)    # PWM, DAC, Pin.OUT/OPEN_DRAIN, servo/buzzer pins, is_physical
        self.assertEqual(v, [])

    def test_no_uart_servo_or_actuator_apis_referenced(self):
        from cansat import guards
        for sub in ("lib", "apps", "config"):
            for rel, full in guards.walk_files(os.path.join(fakes.ESP32, sub), ".py"):
                with open(full) as f:
                    code = "\n".join(c for _, c in guards.code_lines(f.read()))
                for tok in ("PWM", "UART", "Pin.OUT", "Pin.OPEN_DRAIN", "DAC", "ActuatorDriver", "ActuatorManager",
                            "DeploymentInterlock", ".apply(", "PIN_SERVO", "PIN_BUZZER", "machine.WDT",
                            "cansat.mock", "cansat.sim", "ctypes"):
                    self.assertFalse(tok in code, "%s/%s uses %r" % (sub, rel, tok))

    def test_board_code_is_micropython_portable(self):
        from cansat import guards
        for sub in ("lib", "apps", "config"):
            for rel, full in guards.walk_files(os.path.join(fakes.ESP32, sub), ".py"):
                with open(full) as f:
                    src = f.read()
                for n, c in guards.code_lines(src):
                    s = c.strip()
                    for mod in ("enum", "dataclasses", "typing", "abc", "subprocess", "json"):
                        self.assertFalse(s.startswith("import " + mod) or s.startswith("from " + mod + " "),
                                         "%s/%s:%d imports %s" % (sub, rel, n, mod))
                    self.assertNotIn("struct.Struct", c)
                    self.assertFalse(s.startswith("def ") and "->" in s, "%s/%s:%d annotation" % (sub, rel, n))
                compile(src, rel, "exec")

    def test_existing_flight_package_unchanged_by_this_work(self):
        # the guarded tree must still have no hal_mp and all pins TBD (scan_guards rules)
        root = os.path.join(fakes.REPO, "micropython")
        self.assertFalse(os.path.isdir(os.path.join(root, "cansat", "hal_mp")))
        from cansat.config import hardware_config as hc
        self.assertFalse(hc.required_hardware_resolved())

    def test_sd_gate_ships_disabled_and_fsw_off(self):
        import flight_config
        self.assertIs(flight_config.SD_SUPPLY_CONFIRMED, False)
        self.assertIs(flight_config.RUN_FLIGHT_SOFTWARE, False)
        self.assertIs(flight_config.INA219_BUS_CONNECTED, False)
        self.assertIs(flight_config.INA219_SHUNT_CONNECTED, False)


if __name__ == "__main__":
    unittest.main()
