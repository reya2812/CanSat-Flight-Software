# rng.py - tiny deterministic PRNG (xorshift32) for repeatable synthetic noise. [SIMULATED]
# (port of lib/hal_mock/Rng.h; same sequence as C++)
from cansat.core.num import f32

M32 = 0xFFFFFFFF


class Rng:
    def __init__(self, seed):
        seed &= M32
        self._state = seed if seed != 0 else 0x9E3779B9

    def next(self):
        x = self._state
        x ^= (x << 13) & M32
        x ^= x >> 17
        x ^= (x << 5) & M32
        self._state = x
        return x

    def uniform(self, amplitude):
        """Uniform in [-amplitude, +amplitude]; always consumes one draw."""
        u = (self.next() >> 8) / 16777216.0  # exact in float32: k / 2**24
        return f32((u * 2.0 - 1.0) * amplitude)  # u*2-1 is exact; one rounding, as C++
