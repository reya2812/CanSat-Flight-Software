# virtual_clock.py - deterministic simulated time. [SIMULATED] (port of VirtualClock.h)
#   truth time - simulated wall clock; never resets.
#   uptime     - what the flight computer sees via Clock.now_ms(); restarts at 0
#                after a simulated reset. During the reboot gap now_ms() is 0.
from cansat.core.num import u16, u32
from cansat.hal.interfaces import Clock


class VirtualClock(Clock):
    def __init__(self):
        self._truth = 0
        self._boot_start = 0
        self._boot_count = 1

    def now_ms(self):
        return 0 if self.booting() else u32(self._truth - self._boot_start)

    def truth_ms(self):
        return self._truth

    def boot_count(self):
        return self._boot_count

    def booting(self):
        return self._truth < self._boot_start

    def advance(self, ms):
        self._truth = u32(self._truth + ms)

    def advance_to(self, truth_ms):
        """Moves forward only; returns False (and does nothing) for a backwards target."""
        if truth_ms < self._truth:
            return False
        self._truth = truth_ms
        return True

    def simulate_reset(self, reboot_ms):
        self._boot_start = u32(self._truth + reboot_ms)
        self._boot_count = u16(self._boot_count + 1)
