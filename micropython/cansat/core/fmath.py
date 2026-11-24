# fmath.py - float32 arithmetic shared by the detector.  (port of Altitude.h + accelMag)
#
# Every intermediate that C++ stores in a `float` is rounded with f32(), so
# CPython (64-bit floats) follows the C++ float32 results closely. On the
# ESP32, MicroPython floats are already 32-bit ([ASSUMPTION], recalled), so
# f32() changes nothing there.
#
# KNOWN DIFFERENCE (D-017 module 2): the C++ reference build (Apple clang,
# arm64, default -ffp-contract) compiles accelMag() with two FUSED multiply-adds
# (fmadd: one rounding per a*b+c). MicroPython cannot fuse, so accel_mag()
# rounds every operation separately. accel_mag_fma() reproduces the C++
# laptop build for parity diagnosis only; it is never used by flight code.
import math

from cansat.core.num import f32

_ISA_EXP = f32(1.0 / f32(5.255))  # C++: 1.0f / 5.255f, folded in float


def altitude_above_reference(pressure_pa, reference_pa):
    """[ASSUMPTION] ISA approximation, as the C++ altitudeAboveReference()."""
    ratio = f32(pressure_pa / reference_pa)
    return f32(44330.0 * f32(1.0 - f32(math.pow(ratio, _ISA_EXP))))


def accel_mag(ax, ay, az):
    """|a| with every operation rounded to float32 (what MicroPython does)."""
    s = f32(f32(f32(ax * ax) + f32(ay * ay)) + f32(az * az))
    return f32(math.sqrt(s))


def _fma32(a, b, c):
    # For float32 a, b the product is exact in a double; the sum is rounded to
    # double and then to float32. Double rounding can differ from a true fused
    # float32 result in rare halfway cases (diagnostic use only).
    return f32(a * b + c)


def accel_mag_fma(ax, ay, az):
    """|a| as compiled for the C++ laptop reference: fmadd(az,az, fmadd(ax,ax, ay*ay)).

    Operand order identified against C++ golden values (tests/golden_m2.txt).
    """
    s = _fma32(az, az, _fma32(ax, ax, f32(ay * ay)))
    return f32(math.sqrt(s))


# Which |a| implementation the detector uses. Flight code: accel_mag.
# Parity diagnosis may switch this to accel_mag_fma (tests only).
ACCEL_MAG = accel_mag
