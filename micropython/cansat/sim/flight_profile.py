# flight_profile.py - turns a Scenario's segments into a continuous truth trajectory.
# [SIMULATED] (port of firmware/sim/FlightProfile.cpp). Scripted approximation,
# not a physics model. Arithmetic reproduces the C++ laptop build exactly
# (fused multiply-add and C powf, see sim_math.py) so sensor frames match.
import math

from cansat.core.num import f32, u32
from cansat.mock.truth import TruthSource, TruthState
from cansat.sim.sim_math import fma32, powf

_ISA_EXPONENT = f32(5.255)


def pressure_at_altitude(ground_pressure_pa, alt_m):
    """[ASSUMPTION] ISA approximation: p = p0 * (1 - h/44330)^5.255 (as C++)."""
    return f32(ground_pressure_pa * powf(f32(1.0 - f32(alt_m / 44330.0)), _ISA_EXPONENT))


def _kinematics(alt0, v0, az, T):
    # C++: alt = alt0 + v0*T + 0.5f*az*T*T   -> fmadd(x, T, fmadd(v0, T, alt0)), x = (0.5*az)*T
    #      vz  = v0 + az*T                    -> fmadd(az, T, v0)
    x = f32(f32(0.5 * az) * T)
    alt = fma32(x, T, fma32(v0, T, alt0))
    vz = fma32(az, T, v0)
    return alt, vz


class _Resolved:
    def __init__(self, seg, start_ms, duration_ms, alt0, v0):
        self.seg, self.start_ms, self.duration_ms, self.alt0, self.v0 = seg, start_ms, duration_ms, alt0, v0


class FlightProfile(TruthSource):
    def __init__(self, scenario):
        self._sc = scenario
        self._segs = []
        alt, vz, t = 0.0, 0.0, 0
        for s in scenario.segments:
            v0 = s.vz_mps if s.set_vz else vz
            dur = s.duration_ms
            if s.end_at_ground:
                dur = (int(math.ceil(f32(f32(alt / -v0) * 1000.0)))
                       if (v0 < 0.0 and alt > 0.0 and s.az_mps2 == 0.0) else 0)
            r = _Resolved(s, t, dur, alt, v0)
            T = f32(dur / 1000.0)
            alt, vz = _kinematics(r.alt0, r.v0, s.az_mps2, T)
            if s.end_at_ground:
                alt, vz = 0.0, 0.0
            t = u32(t + dur)
            self._segs.append(r)
        self._total = t

    def total_ms(self):
        return self._total

    def segment_count(self):
        return len(self._segs)

    def segment_start_ms(self, i):
        return self._segs[i].start_ms

    def segment_duration_ms(self, i):
        return self._segs[i].duration_ms

    def truth_at(self, truth_ms):
        sc = self._sc
        st = TruthState()
        st.truth_ms = truth_ms
        st.temp_c, st.bus_v, st.current_ma = sc.temp_c, sc.bus_v, sc.current_ma
        st.pressure_pa = sc.ground_pressure_pa
        if not self._segs:
            return st
        idx = 0
        for i, r in enumerate(self._segs):
            if r.start_ms <= truth_ms:
                idx = i
        while (idx + 1 < len(self._segs) and self._segs[idx].duration_ms == 0 and
               self._segs[idx + 1].start_ms <= truth_ms):
            idx += 1
        r = self._segs[idx]
        elapsed = u32(truth_ms - r.start_ms)
        if elapsed > r.duration_ms:
            elapsed = r.duration_ms  # hold end state after the script
        T = f32(elapsed / 1000.0)
        alt, vz = _kinematics(r.alt0, r.v0, r.seg.az_mps2, T)
        if r.seg.end_at_ground and alt < 0.0:
            alt = 0.0
        if r.seg.end_at_ground and elapsed == r.duration_ms:
            vz = 0.0
        st.segment = idx
        st.label = r.seg.label
        st.alt_m = alt
        st.vz_mps = vz
        st.pressure_pa = pressure_at_altitude(sc.ground_pressure_pa, alt)
        st.accel_g = list(r.seg.accel_g)
        st.gyro_dps = list(r.seg.gyro_dps)
        st.mounted = r.seg.mounted
        return st
