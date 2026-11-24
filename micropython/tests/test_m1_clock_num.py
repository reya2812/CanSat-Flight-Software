# Module 1: uint32 helpers, float32 rounding, ticks emulation and the uptime clock.
import unittest

from cansat.core import num
from cansat.core.clock import TicksUptimeClock, ticks_period
from cansat.mock.ticks import EmulatedTicks, MICROPYTHON_ESP32_TICKS_PERIOD

U32 = 1 << 32


class Uint32(unittest.TestCase):
    def test_wrap_like_cpp(self):
        self.assertEqual(num.u32(U32), 0)
        self.assertEqual(num.u32(-1), 0xFFFFFFFF)
        self.assertEqual(num.u32_add(0xFFFFFFFF, 2), 1)
        self.assertEqual(num.u32_sub(5, 0xFFFFFFFE), 7)  # elapsed across a wrap
        self.assertEqual(num.u32_sub(0, 1), 0xFFFFFFFF)  # C++: (uint32_t)0 - 1
        self.assertEqual(num.u16(0x1FFFF), 0xFFFF)
        self.assertEqual(num.u8(256), 0)

    def test_is_u32(self):
        self.assertTrue(num.is_u32(0) and num.is_u32(0xFFFFFFFF))
        self.assertFalse(num.is_u32(-1) or num.is_u32(U32) or num.is_u32(True) or num.is_u32(1.0))


class Float32(unittest.TestCase):
    def test_rounds_to_binary32(self):
        self.assertEqual(num.f32(0.1), 0.10000000149011612)
        self.assertEqual(num.f32(101325.0), 101325.0)
        self.assertEqual(num.f32(1.0 / 5.255), 0.19029495120048523)
        self.assertEqual(num.f32(num.f32(0.3)), num.f32(0.3))

    def test_trace_values_round_trip(self):
        # The C++ trace prints floats with %.9g, which round-trips binary32.
        for text in ("101322.648", "25.0069103", "-0.0156850796", "0.990564227", "3.89215636"):
            v = num.f32(float(text))
            self.assertEqual(num.f32(float("%.9g" % v)), v)


class Ticks(unittest.TestCase):
    def test_esp32_period_derived_from_source(self):
        # MP_SMALL_INT_POSITIVE_MASK + 1 with MICROPY_OBJ_REPR_A on a 32-bit word.
        mask = ~(0x80000000 | 0x40000000) & 0xFFFFFFFF
        self.assertEqual(MICROPYTHON_ESP32_TICKS_PERIOD, mask + 1)

    def test_ticks_wrap_and_diff(self):
        t = EmulatedTicks(start_ms=(1 << 30) - 3)
        a = t.ticks_ms()
        t.advance(10)
        b = t.ticks_ms()
        self.assertEqual(b, 7)
        self.assertEqual(t.ticks_diff(b, a), 10)
        self.assertEqual(t.ticks_diff(a, b), -10)
        self.assertEqual(t.ticks_add(a, 10), b)

    def test_diff_range(self):
        t = EmulatedTicks(period=16)
        self.assertEqual(t.ticks_diff(8, 0), -8)  # half period: [-p/2, p/2 - 1]
        self.assertEqual(t.ticks_diff(7, 0), 7)

    def test_rejects_bad_period_and_backwards_time(self):
        with self.assertRaises(ValueError):
            EmulatedTicks(period=12)
        with self.assertRaises(ValueError):
            EmulatedTicks().advance(-1)


class TicksSemantics(unittest.TestCase):
    """Emulation follows MicroPython extmod/modtime.c, for several power-of-two periods."""

    PERIODS = (1 << 4, 1 << 10, 1 << 30)

    def test_period_discovery_as_documented(self):
        for p in self.PERIODS:
            self.assertEqual(ticks_period(EmulatedTicks(period=p)), p)

    def test_ticks_ms_wraps_at_period(self):
        for p in self.PERIODS:
            t = EmulatedTicks(start_ms=p - 1, period=p)
            self.assertEqual(t.ticks_ms(), p - 1)
            t.advance(1)
            self.assertEqual(t.ticks_ms(), 0)

    def test_ticks_diff_range_and_sign_flip_at_half_period(self):
        for p in self.PERIODS:
            t = EmulatedTicks(period=p)
            h = p // 2
            self.assertEqual(t.ticks_diff(h - 1, 0), h - 1)    # largest valid positive
            self.assertEqual(t.ticks_diff(h, 0), -h)           # docs: exactly P/2 flips sign
            self.assertEqual(t.ticks_diff(0, h - 1), -(h - 1))
            self.assertEqual(t.ticks_diff(2, p - 3), 5)         # across the wrap

    def test_ticks_add_limits(self):
        for p in self.PERIODS:
            t = EmulatedTicks(period=p)
            h = p // 2
            self.assertEqual(t.ticks_add(p - 1, 1), 0)
            self.assertEqual(t.ticks_add(0, h - 1), h - 1)
            self.assertEqual(t.ticks_add(0, -(h - 1)), (-(h - 1)) & (p - 1))
            for bad in (h, -h, p, -p):
                with self.assertRaises(OverflowError):
                    t.ticks_add(0, bad)

    def test_bad_period_rejected_by_clock(self):
        class Odd(EmulatedTicks):
            def ticks_add(self, t, d):
                return 11
        with self.assertRaises(ValueError):
            TicksUptimeClock(Odd())

    def test_clock_crosses_wrap_for_every_period(self):
        for p in self.PERIODS:
            t = EmulatedTicks(start_ms=p - 3, period=p)
            c = TicksUptimeClock(t, start_uptime_ms=0)
            self.assertEqual(c.period(), p)
            self.assertEqual(c.max_poll_interval_ms(), p // 2 - 1)
            total = 0
            step = max(1, p // 4)
            for _ in range(12):  # three full periods
                t.advance(step)
                total += step
                self.assertEqual(c.now_ms(), total)

    def test_poll_at_limit_ok_beyond_limit_wrong(self):
        p = 1 << 10
        t = EmulatedTicks(period=p)
        c = TicksUptimeClock(t, start_uptime_ms=0)
        t.advance(c.max_poll_interval_ms())
        self.assertEqual(c.now_ms(), p // 2 - 1)
        t.advance(p // 2)  # exactly half a period since the last poll: ambiguous
        self.assertEqual(c.now_ms(), p // 2 - 1)  # documented limitation: the step is lost


class UptimeClock(unittest.TestCase):
    def test_starts_at_ticks_since_boot(self):
        t = EmulatedTicks(start_ms=1234)
        self.assertEqual(TicksUptimeClock(t).now_ms(), 1234)

    def test_monotonic_across_ticks_period(self):
        t = EmulatedTicks(start_ms=(1 << 30) - 100)
        c = TicksUptimeClock(t, start_uptime_ms=0)
        seen = []
        for _ in range(50):
            t.advance(7)
            seen.append(c.now_ms())
        self.assertEqual(seen, [7 * (i + 1) for i in range(50)])

    def test_wraps_at_2_pow_32_like_millis(self):
        t = EmulatedTicks()
        c = TicksUptimeClock(t, start_uptime_ms=0xFFFFFFFF - 4)
        t.advance(10)
        self.assertEqual(c.now_ms(), 5)

    def test_long_run_matches_uint32_millis(self):
        # 2**33 ms of 1e8-ms steps: crosses several ticks periods and two uint32 wraps.
        t = EmulatedTicks()
        c = TicksUptimeClock(t, start_uptime_ms=0)
        true_ms = 0
        while true_ms < (1 << 33):
            t.advance(100000000)
            true_ms += 100000000
            self.assertEqual(c.now_ms(), true_ms & 0xFFFFFFFF)

    def test_never_goes_backwards(self):
        class Jumpy:
            def __init__(self):
                self.v = [100, 90, 90, 120]

            def ticks_ms(self):
                return self.v.pop(0)

            def ticks_diff(self, a, b):
                return a - b

            def ticks_add(self, t, d):
                return (t + d) & ((1 << 30) - 1)

        c = TicksUptimeClock(Jumpy(), start_uptime_ms=0)
        self.assertEqual([c.now_ms(), c.now_ms(), c.now_ms()], [0, 0, 20])

    def test_polling_slower_than_half_period_is_ambiguous(self):
        # Documented limitation: now_ms() must run at least every TICKS_PERIOD/2.
        t = EmulatedTicks(period=1 << 10)
        c = TicksUptimeClock(t, start_uptime_ms=0)
        t.advance(600)  # more than half of 1024
        self.assertNotEqual(c.now_ms(), 600)


if __name__ == "__main__":
    unittest.main()
