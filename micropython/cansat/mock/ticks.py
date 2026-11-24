# ticks.py - CPython emulation of MicroPython time.ticks_ms()/ticks_diff()/ticks_add().
# [SIMULATED] Laptop tests only.
#
# Formulas copied from MicroPython extmod/modtime.c (master, read 2026-11-18); see
# cansat/core/clock.py for the full source references. The default period is the
# esp32 port's value derived from that source (2**30). Tests also run other
# power-of-two periods, because the docs say the period may differ by port/build.

MICROPYTHON_ESP32_TICKS_PERIOD = 1 << 30  # from source: MP_SMALL_INT_POSITIVE_MASK + 1, REPR_A, 32-bit


class EmulatedTicks:
    def __init__(self, start_ms=0, period=MICROPYTHON_ESP32_TICKS_PERIOD):
        if period < 2 or period & (period - 1):
            raise ValueError("period must be a power of two")
        self.period = period
        self._ms = start_ms  # true elapsed ms (unbounded), like esp_timer_get_time()/1000

    def advance(self, ms):
        if ms < 0:
            raise ValueError("time never goes backwards")
        self._ms += ms

    def ticks_ms(self):
        return self._ms & (self.period - 1)

    def ticks_add(self, t, delta):
        # modtime.c: if (delta + P/2 - 1 >= P - 1) raise OverflowError  (unsigned compare)
        p = self.period
        if ((delta + p // 2 - 1) & 0xFFFFFFFFFFFFFFFF) >= p - 1:
            raise OverflowError("ticks interval overflow")
        return (t + delta) & (p - 1)

    def ticks_diff(self, a, b):
        half = self.period >> 1
        return ((a - b + half) & (self.period - 1)) - half
