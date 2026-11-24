# Laptop tests for esp32/apps/imu_test.py with a fake machine module and a fake
# IMU. They check the script's logic and that its only write is clearing the
# SLEEP bit. They say nothing about the real sensor.
import os
import runpy
import struct
import types
import unittest

import fakes

SCRIPT = os.path.join(fakes.ESP32, "apps", "imu_test.py")


def fake_machine(found=(0x68,), who=0x71, pwr=0x40, log=None):
    log = log if log is not None else []
    regs = {0x75: who, 0x6B: pwr, 0x1C: 0x00, 0x1B: 0x00}
    data = struct.pack(">7h", 0, 0, 16384, 0, 131, -262, 0)   # az = 1 g, gx = 1 dps, gy = -2 dps
    m = types.ModuleType("machine")
    m.Pin = lambda n: n

    class Bus:
        def __init__(self, bid, scl=None, sda=None, freq=None):
            log.append(("ctor", bid, scl, sda, freq))

        def scan(self):
            return list(found)

        def readfrom_mem(self, addr, reg, n):
            if reg == 0x3B:
                return data[:n]
            return bytes([regs[reg]])

        def writeto_mem(self, addr, reg, buf):
            log.append(("write", addr, reg, bytes(buf)))
            regs[reg] = buf[0]
    m.I2C = Bus
    return m, log


class ImuTest(unittest.TestCase):
    def run_app(self, **kw):
        m, log = fake_machine(**kw)
        g = runpy.run_path(SCRIPT, run_name="imu_test")
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

    def test_reads_and_scales(self):
        n, log, text = self.run_app()
        self.assertEqual(log[0], ("ctor", 0, 22, 21, 100000))
        self.assertIn("WHO_AM_I = 0x71 -> MPU-9250", text)
        self.assertIn("  0.00   0.00   1.00", text)
        self.assertIn("1.0    -2.0", text)
        self.assertGreater(n, 0)

    def test_only_write_clears_sleep_bit(self):
        _, log, _ = self.run_app(pwr=0x41)
        self.assertEqual([e for e in log if e[0] == "write"], [("write", 0x68, 0x6B, bytes([0x01]))])
        _, log, _ = self.run_app(pwr=0x01)          # already awake: no write at all
        self.assertEqual([e for e in log if e[0] == "write"], [])

    def test_no_imu_or_unknown_chip_stops_without_writing(self):
        n, log, text = self.run_app(found=(0x40,))
        self.assertIsNone(n)
        self.assertIn("no IMU at 0x68 or 0x69", text)
        n, log, text = self.run_app(who=0x12)
        self.assertIsNone(n)
        self.assertIn("UNKNOWN chip", text)
        self.assertEqual([e for e in log if e[0] == "write"], [])


if __name__ == "__main__":
    unittest.main()
