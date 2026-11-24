# sim_math.py - exact C++ float32 arithmetic for the LAPTOP simulator only. [SIMULATED]
#
# The simulator must feed the Python flight software the SAME sensor frames the
# C++ reference produced, so its truth model reproduces the C++ laptop build:
#   - fma32(): fused multiply-add rounded once to float32 (Apple clang contracts
#     a*b+c in FlightProfile into fmadd; verified by disassembly, module 3).
#   - powf(): the platform C library powf via ctypes (CPython only). If ctypes
#     cannot load it, falls back to float32-rounded math.pow and reports it.
# Flight code never imports this module (scan rule); MicroPython never runs it.
import math
import struct

from cansat.core.num import f32


def _bits(x):
    return struct.unpack("<q", struct.pack("<d", x))[0]


def _from_bits(b):
    return struct.unpack("<d", struct.pack("<q", b))[0]


def fma32(a, b, c):
    """round_to_float32(a*b + c) with a single rounding, for float32 inputs.

    a*b is exact in a double (48 significant bits). The sum is formed with TwoSum
    and rounded to odd in double precision, which makes the final rounding to
    float32 correct (no double-rounding error).
    """
    p = a * b  # exact for float32 a, b
    s = p + c
    bp = s - c
    e = (p - bp) + (c - (s - bp))  # TwoSum error: p + c == s + e exactly
    if e != 0.0 and (_bits(s) & 1) == 0 and math.isfinite(s):
        s = _from_bits(_bits(s) + (1 if (e > 0) == (s > 0) else -1))  # round to odd
    return f32(s)


try:
    import ctypes
    import ctypes.util

    _libm = ctypes.CDLL(ctypes.util.find_library("m") or None)
    _powf = _libm.powf
    _powf.restype = ctypes.c_float
    _powf.argtypes = (ctypes.c_float, ctypes.c_float)
    POWF_SOURCE = "C library powf (ctypes)"

    def powf(x, y):
        return _powf(x, y)
except (ImportError, OSError, AttributeError):  # pragma: no cover - platform dependent
    POWF_SOURCE = "math.pow rounded to float32 (fallback: frames may differ from C++ by 1 step)"

    def powf(x, y):
        return f32(math.pow(x, y))
