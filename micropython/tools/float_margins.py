#!/usr/bin/env python3
"""float_margins.py - how close the parity scenarios come to each float threshold.

Replays every C++ trace (as tools/parity.py does) and records, for every value the
detector computes, its distance from each SYNTHETIC threshold it can be compared
with. Conservative: values are counted even in states where that comparison is not
evaluated. A margin of a few float32 steps would mean a float-boundary difference
between C++ and MicroPython could flip a decision; such a case would be reported
for a decision, never accepted. SIMULATED, not hardware validation.

  python3 tools/float_margins.py
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import parity  # noqa: E402
from cansat.core import event_detector as ED  # noqa: E402
from cansat.core import fmath  # noqa: E402
from cansat.core.num import f32  # noqa: E402
from cansat.sim import synthetic_flight_params as SP  # noqa: E402


def ulp(x):
    b = struct.unpack("<i", struct.pack("<f", abs(x)))[0]
    return struct.unpack("<f", struct.pack("<i", b + 1))[0] - abs(x)


def collect(trace_dir):
    prm = SP.synthetic_flight_params(SP.CANDIDATE_POLICIES[0])  # thresholds do not depend on the policy
    r, t = prm.release, prm.transitions
    th = {
        "|a| < freefall_accel_max_g": r.freefall_accel_max_g.require(),
        "|a| >= chute_open_accel_min_g": t.chute_open_accel_min_g.require(),
        "||a|-1| > landed_accel_tol_g": t.landed_accel_tol_g.require(),
        "alt >= ascent_min_gain_m": t.ascent_min_gain_m.require(),
        "|alt| > landed_max_alt_above_ground_m": t.landed_max_alt_above_ground_m.require(),
        "drop >= baro_min_drop_m": r.baro_min_drop_m.require(),
    }
    best = {k: (float("inf"), None) for k in th}

    def note(k, v):
        m = abs(v - th[k])
        if m < best[k][0]:
            best[k] = (m, v)

    orig_mag, orig_alt, orig_baro = fmath.ACCEL_MAG, fmath.altitude_above_reference, ED.EventDetector._update_baro

    def mag(ax, ay, az):
        a = orig_mag(ax, ay, az)
        note("|a| < freefall_accel_max_g", a)
        note("|a| >= chute_open_accel_min_g", a)
        note("||a|-1| > landed_accel_tol_g", abs(f32(a - 1.0)))
        return a

    def alt(p, ref):
        a = orig_alt(p, ref)
        note("alt >= ascent_min_gain_m", a)
        note("|alt| > landed_max_alt_above_ground_m", abs(a))
        return a

    def baro(self, v):
        orig_baro(self, v)
        if not self._alt_valid:
            return
        for i in range(self._hist_n):
            idx = (self._hist_head - 1 - i + ED.BARO_HISTORY) % ED.BARO_HISTORY
            if (v.now_ms - self._hist_t[idx]) & 0xFFFFFFFF >= self._w_b:
                note("drop >= baro_min_drop_m", f32(self._hist_alt[idx] - self._alt_now))
                break

    fmath.ACCEL_MAG, fmath.altitude_above_reference, ED.EventDetector._update_baro = mag, alt, baro
    try:
        results = parity.run_all(trace_dir, use_fma=None)
    finally:
        fmath.ACCEL_MAG, fmath.altitude_above_reference, ED.EventDetector._update_baro = orig_mag, orig_alt, orig_baro
    return th, best, results


def golden_disagreement():
    """Largest C++ vs Python difference measured on tests/golden_m2.txt: (altitude m, |a| g)."""
    path = os.path.join(os.path.dirname(HERE), "tests", "golden_m2.txt")
    fb = lambda h: struct.unpack("<f", struct.pack("<I", int(h, 16)))[0]
    da = dm = 0.0
    with open(path) as f:
        for line in f:
            c = line.split()
            if c[0] == "A":
                da = max(da, abs(fmath.altitude_above_reference(f32(float(c[1])), f32(float(c[2]))) - fb(c[3])))
            elif c[0] == "M":
                ax, ay, az = (f32(float(v)) for v in c[1:4])
                dm = max(dm, abs(fmath.accel_mag(ax, ay, az) - fb(c[4])))
    return da, dm


def main(argv):
    trace_dir = argv[1] if len(argv) > 1 else parity.DEFAULT_TRACE_DIR
    th, best, results = collect(trace_dir)
    if not results:
        print("no traces (cd firmware && make traces)")
        return 2
    print("# SIMULATED - SYNTHETIC thresholds. Closest computed value to each threshold, %d traces" % len(results))
    da, dm = golden_disagreement()
    # A drop is a difference of two altitudes, so its disagreement can be twice da.
    dis = {k: (dm if "|a|" in k else (2 * da if "drop" in k else da)) for k in th}
    print("%-40s %10s %14s %12s %14s %12s %s" % ("comparison", "threshold", "closest value", "margin",
                                                  "float32 steps", "C++/Py diff", "verdict"))
    at_risk = 0
    for k, t in th.items():
        m, v = best[k]
        risk = m <= dis[k]
        at_risk += risk
        print("%-40s %10.4g %14.9g %12.3g %14.0f %12.3g %s" % (k, t, v, m, m / ulp(t), dis[k],
                                                              "FLOAT-BOUNDARY RISK" if risk else "clear"))
    print("# C++/Py diff = largest disagreement measured on tests/golden_m2.txt (x2 for a drop).")
    print("# %d comparison(s) came closer to the threshold than C++ and Python can disagree." % at_risk)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
