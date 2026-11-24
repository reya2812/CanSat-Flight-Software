# Laptop tests for esp32/apps/sensors_test.py with a fake machine module and
# fake IMU / BMP280 / INA219. They check decoding, the allowed writes, and that
# one missing sensor does not stop the others. They say nothing about hardware.
import os
import runpy
import struct
import types
import unittest

import fakes

SCRIPT = os.path.join(fakes.ESP32, "apps", "sensors_test.py")
# Bosch datasheet worked example [ASSUMPTION, recalled]: these calibration
# values with adc_t=519888, adc_p=415148 give about 25.08 C and 100653 Pa.
CALIB = (27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)


def fake_machine(found=(0x40, 0x68, 0x76), log=None):
    log = log if log is not None else []
    imu = {0x75: b"\x70", 0x6B: b"\x40", 0x1C: b"\x00", 0x1B: b"\x00",
           0x3B: struct.pack(">7h", 0, 0, 16384, 0, 0, 0, 0)}
    adc_p, adc_t = 415148, 519888
    baro = {0xD0: b"\x58", 0x88: struct.pack("<HhhHhhhhhhhh", *CALIB), 0xF3: b"\x00",
            0xF7: bytes([adc_p >> 12, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4,
                         adc_t >> 12, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4])}
    ina = {0x00: b"\x39\x9F", 0x01: struct.pack(">h", 500), 0x02: struct.pack(">H", 925 << 3)}
    chips = {0x68: imu, 0x76: baro, 0x40: ina}
    m = types.ModuleType("machine")
    m.Pin = lambda n: n

    class Bus:
        def __init__(self, bid, scl=None, sda=None, freq=None):
            log.append(("ctor", bid, scl, sda, freq))

        def scan(self):
            return list(found)

        def readfrom_mem(self, addr, r, n):
            return chips[addr][r][:n]

        def writeto_mem(self, addr, r, buf):
            log.append(("write", addr, r, bytes(buf)))
    m.I2C = Bus
    return m, log


class SensorsTest(unittest.TestCase):
    def run_app(self, **kw):
        m, log = fake_machine(**kw)
        g = runpy.run_path(SCRIPT, run_name="sensors_test")
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

    def test_all_three_decoded(self):
        n, log, text = self.run_app()
        self.assertEqual(log[0], ("ctor", 0, 22, 21, 100000))
        self.assertIn("MPU-6500 at 0x68", text)
        self.assertIn("BMP280 at 0x76", text)
        self.assertIn("INA219 at 0x40", text)
        row = [line for line in text.splitlines() if line.startswith(" 0.00")][0]
        self.assertIn(" 0.00  0.00  1.00", row)
        self.assertIn("1006.5", row)           # about 100653 Pa
        self.assertIn("25.08", row)
        self.assertIn(" 3.700    50.0", row)   # 925*4 mV; 500*10 uV / 0.1 ohm
        self.assertGreater(n, 0)

    def test_only_allowed_writes(self):
        _, log, _ = self.run_app()
        writes = {(e[1], e[2], e[3]) for e in log if e[0] == "write"}
        self.assertEqual(writes, {(0x68, 0x6B, b"\x00"), (0x76, 0xF4, b"\x25")})

    def test_missing_sensor_does_not_stop_others(self):
        n, _, text = self.run_app(found=(0x68,))
        self.assertIn("BARO  : not found", text)
        self.assertIn("(no INA219)", text)
        self.assertGreater(n, 0)
        n, _, text = self.run_app(found=())
        self.assertIsNone(n)


if __name__ == "__main__":
    unittest.main()
