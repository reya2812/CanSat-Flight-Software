# param.py - a value that starts UNSET and has no default.  (port of lib/core/Param.h)
#
# [TEAM DECISION] Firmware holds no default values for flight thresholds or
# deployment timings. Every such value is a Param that is unset until assigned
# from an approved source (or, in tests/simulation only, from a SYNTHETIC_*
# constant). There is deliberately no accessor that returns a fallback value.
#
# Differences from C++ (D-017 module 1 review, item 7):
#   - C++ get(T& out) returns bool and writes `out`; here get() returns
#     (ok, value) and require() returns the value or raises ParamUnset.
#   - C++ Param<float>::set(NaN or inf) stores it; every later comparison with
#     NaN is false, which silently disables or alters detection (e.g.
#     `alt >= NaN` never true, `|a| < NaN` never free fall). Here set() raises
#     ValueError, so a bad value is caught when parameters are loaded.
#   - C++ Param<T> is type-checked
# at compile time; here the kind is checked at set() time and a wrong type
# raises ValueError instead of being converted. Float params are stored
# rounded to 32 bits, like C++ Param<float>.
import math

from cansat.core.num import is_u32, f32

KIND_U32 = "u32"
KIND_BOOL = "bool"
KIND_FLOAT = "float"
KIND_ENUM = "enum"  # small non-negative int code; Unset (0) is accepted by set() but never "complete"


def _check(kind, v):
    if kind == KIND_U32:
        return is_u32(v)
    if kind == KIND_BOOL:
        return v is True or v is False
    if kind == KIND_FLOAT:
        return (isinstance(v, (int, float)) and not isinstance(v, bool)) and math.isfinite(v)
    if kind == KIND_ENUM:
        return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
    return False


class ParamUnset(Exception):
    """require() was called on an unset Param: a missing completeness check (a bug)."""


class Param:
    def __init__(self, kind):
        if kind not in (KIND_U32, KIND_BOOL, KIND_FLOAT, KIND_ENUM):
            raise ValueError("unknown Param kind")
        self.kind = kind
        self._set = False
        self._value = None

    def set(self, v):
        if not _check(self.kind, v):
            raise ValueError("Param value has the wrong type or range for kind " + self.kind)
        if self.kind == KIND_FLOAT:
            v = f32(float(v))  # C++ Param<float> stores a 32-bit float
        self._value = v
        self._set = True

    def clear(self):
        self._set = False
        self._value = None

    def is_set(self):
        return self._set

    def get(self):
        """Return (True, value) when set, else (False, None). No fallback exists.

        Call-site rule (enforced by tools/scan_guards.py): always unpack into two
        names and test the flag, e.g. `ok, v = p.get()`. Never index the tuple.
        """
        if not self._set:
            return False, None
        return True, self._value

    def require(self):
        """Value of a Param that a completeness check has already guaranteed.

        Raises ParamUnset instead of returning None, so a missing is_complete()
        guard fails loudly at construction rather than misbehaving later.
        """
        if not self._set:
            raise ParamUnset("required parameter is unset (kind " + self.kind + ")")
        return self._value
