# num.py - fixed-width integer and float32 helpers (portable: CPython + MicroPython).
#
# Python integers never overflow and CPython floats are 64-bit. The C++
# reference uses uint32_t / uint16_t / uint8_t that wrap, and 32-bit floats.
# Core code that must match the C++ behaviour uses these helpers explicitly.
import struct

U32_MASK = 0xFFFFFFFF
U16_MASK = 0xFFFF
U8_MASK = 0xFF


def u32(x):
    """Wrap an integer to uint32_t (C++ unsigned arithmetic)."""
    return x & U32_MASK


def u16(x):
    return x & U16_MASK


def u8(x):
    return x & U8_MASK


def u32_add(a, b):
    return (a + b) & U32_MASK


def u32_sub(a, b):
    """a - b as uint32_t, e.g. elapsed time across a wrap: u32_sub(5, 0xFFFFFFFE) == 7."""
    return (a - b) & U32_MASK


def is_u32(x):
    return isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= U32_MASK




def f32(x):
    """Round a number to the nearest IEEE-754 binary32 value (C++ float).

    CPython computes in 64-bit doubles; rounding at the same points where the
    C++ code stores a float keeps the two implementations close. MicroPython's
    ESP32 build already uses 32-bit floats, where this is a no-op.
    """
    return struct.unpack("<f", struct.pack("<f", x))[0]
