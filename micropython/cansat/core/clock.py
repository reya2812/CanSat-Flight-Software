# clock.py - uint32 uptime from a MicroPython-style ticks counter (D-017).
#
# The C++ reference uses millis(): a uint32 that wraps at 2**32 ms (~49.7 days).
# MicroPython's time.ticks_ms() wraps at its own TICKS_PERIOD instead.
#
# MicroPython semantics, read from the source on 2026-11-18 (micropython/micropython
# master: extmod/modtime.c, py/mpconfig.h, py/smallint.h, ports/esp32/mpconfigport.h,
# ports/esp32/mphalport.c) and docs.micropython.org/en/latest/library/time.html:
#   ticks_ms()        = mp_hal_ticks_ms() & (TICKS_PERIOD - 1); on esp32
#                       mp_hal_ticks_ms() = esp_timer_get_time() / 1000 (ms since boot).
#   TICKS_PERIOD      = MP_SMALL_INT_POSITIVE_MASK + 1 unless a port overrides it.
#                       esp32 sets MICROPY_OBJ_REPR_A on a 32-bit word and does not
#                       override it -> 2**30 ms (~12.4 days). Docs: "guaranteed to be a
#                       power of two, but otherwise may differ from port to port".
#   ticks_diff(a, b)  = ((a - b + P/2) & (P - 1)) - P/2, range [-P/2, P/2 - 1];
#                       valid only if a and b are at most P/2 - 1 ticks apart.
#   ticks_add(t, d)   = (t + d) & (P - 1); raises OverflowError unless
#                       -(P/2 - 1) <= d <= P/2 - 1 (modtime.c compares d + P/2 - 1 >= P - 1;
#                       [ASSUMPTION] the comparison is unsigned, since P is built from an
#                       unsigned mask - not confirmed on a board).
#   Period discovery  : ticks_add(0, -1) + 1 (documented).
#
# This module does NOT assume the period: it reads it from the ticks source at
# start-up (ticks_period()), so a different build or port is handled. now_ms()
# must be called at least once every max_poll_interval_ms() (= P/2 - 1), or the
# elapsed time is ambiguous; the flight loop calls it every tick.
from cansat.core.num import u32_add
from cansat.hal.interfaces import Clock


def ticks_period(src):
    """TICKS_PERIOD of a ticks source, discovered as the MicroPython docs describe."""
    p = src.ticks_add(0, -1) + 1
    if p < 2 or p & (p - 1):
        raise ValueError("ticks period is not a power of two: " + str(p))
    return p


class TicksUptimeClock(Clock):
    def __init__(self, ticks_source, start_uptime_ms=None):
        self._src = ticks_source
        self._period = ticks_period(ticks_source)
        self._last = ticks_source.ticks_ms()
        # Default: uptime = ticks since the counter started (~boot on the ESP32).
        self._uptime = (self._last if start_uptime_ms is None else start_uptime_ms) & 0xFFFFFFFF

    def period(self):
        return self._period

    def max_poll_interval_ms(self):
        return self._period // 2 - 1

    def now_ms(self):
        raw = self._src.ticks_ms()
        d = self._src.ticks_diff(raw, self._last)
        if d > 0:
            self._uptime = u32_add(self._uptime, d)
            self._last = raw
        # d <= 0: no time passed, or the source stepped backwards; never go backwards.
        return self._uptime
