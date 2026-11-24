# sensor_validator.py - decides which samples flight logic may use (SW-12).
# (port of lib/core/SensorValidator.h/.cpp; see that file for the evidence list, OD-066)
import math

from cansat.core import types as T

# [ASSUMPTION] BMP280 measuring range 300-1100 hPa (datasheet, recalled).
BARO_MIN_PA = 30000.0
BARO_MAX_PA = 110000.0
# [ASSUMPTION] MPU6050 +-16 g full scale (datasheet, recalled).
IMU_MAX_ABS_G = 16.0
# [UNVERIFIED] INA219 "up to 3.2 A" with 0.1 ohm shunt (docs/03); [ASSUMPTION] 26 V bus max.
POWER_MAX_ABS_MA = 3200.0
POWER_MAX_BUS_V = 26.0

REJECT_NONE = 0
REJECT_INVALID_FLAG = 1 << 0
REJECT_NON_FINITE = 1 << 1
REJECT_RANGE = 1 << 2
REJECT_ZERO_READ = 1 << 3
REJECT_STALE_REPEAT = 1 << 4
REJECT_STALE_AGE = 1 << 5
REJECT_COMM = 1 << 6
REJECT_NOT_FRESH = 1 << 7
REJECT_STUCK = 1 << 8


class ValidatedFrame:
    def __init__(self, now_ms, raw):
        self.now_ms = now_ms
        self.raw = raw  # the SensorFrame (C++ copies it; callers never mutate it afterwards)
        self.baro_ok = self.imu_ok = self.power_ok = self.switches_ok = False
        self.baro_reject = self.imu_reject = self.power_reject = self.switches_reject = 0


class _Age:
    def __init__(self):
        self.has = False
        self.last = 0


class SensorValidator:
    def __init__(self, params):
        self._p = params
        self._baro, self._imu, self._power, self._sw = _Age(), _Age(), _Age(), _Age()
        self._has_prev_imu = False
        self._prev_imu = [0.0] * 6
        self._imu_run = 0
        self._faults = 0
        self._newly_faulted = 0
        self._newly_recovered = 0

    def fault_mask(self):
        return self._faults

    def newly_faulted(self):
        return self._newly_faulted

    def newly_recovered(self):
        return self._newly_recovered

    def _age_check(self, t_ms, now_ms, a):
        r = 0
        if a.has and t_ms <= a.last:
            r |= REJECT_STALE_REPEAT
        ok, stale = self._p.release.sample_stale_ms.get()
        if ok and now_ms >= t_ms and now_ms - t_ms > stale:
            r |= REJECT_STALE_AGE
        if r == 0:
            a.has = True
            a.last = t_ms
        return r

    def _imu_stuck(self, m):
        v = (m.ax_g, m.ay_g, m.az_g, m.gx_dps, m.gy_dps, m.gz_dps)
        same = self._has_prev_imu
        if same:
            for i in range(6):
                if v[i] != self._prev_imu[i]:
                    same = False
                    break
        self._imu_run = self._imu_run + 1 if same else 1
        for i in range(6):
            self._prev_imu[i] = v[i]
        self._has_prev_imu = True
        ok, limit = self._p.validation.imu_stuck_identical_samples.get()
        if ok and limit > 0 and self._imu_run >= limit:
            return REJECT_STUCK
        return 0

    def _set_fault(self, bit, bad):
        was = (self._faults & bit) != 0
        if bad and not was:
            self._faults |= bit
            self._newly_faulted |= bit
        elif not bad and was:
            self._faults &= ~bit
            self._newly_recovered |= bit

    def validate(self, f, now_ms):
        self._newly_faulted = 0
        self._newly_recovered = 0
        v = ValidatedFrame(now_ms, f)
        fin = math.isfinite

        # ---- barometer ----
        b = f.baro
        r = 0
        if not b.comm_ok:
            r |= REJECT_COMM
        if not b.valid:
            r |= REJECT_INVALID_FLAG
        if r == 0:
            if not b.data_ready:
                r |= REJECT_NOT_FRESH
            elif not fin(b.pressure_pa) or not fin(b.temp_c):
                r |= REJECT_NON_FINITE
            elif b.pressure_pa == 0.0 and b.temp_c == 0.0:
                r |= REJECT_ZERO_READ
            elif b.pressure_pa < BARO_MIN_PA or b.pressure_pa > BARO_MAX_PA:
                r |= REJECT_RANGE
        if r == 0:
            r |= self._age_check(b.t_ms, now_ms, self._baro)
        v.baro_reject = r
        v.baro_ok = r == 0
        self._set_fault(T.FAULT_BARO_INVALID, not v.baro_ok)

        # ---- IMU ----
        m = f.imu
        r = 0
        if not m.comm_ok:
            r |= REJECT_COMM
        if not m.valid:
            r |= REJECT_INVALID_FLAG
        if r == 0:
            if not m.data_ready:
                r |= REJECT_NOT_FRESH
            elif not (fin(m.ax_g) and fin(m.ay_g) and fin(m.az_g) and
                      fin(m.gx_dps) and fin(m.gy_dps) and fin(m.gz_dps)):
                r |= REJECT_NON_FINITE
            elif (m.ax_g == 0.0 and m.ay_g == 0.0 and m.az_g == 0.0 and m.gx_dps == 0.0 and
                  m.gy_dps == 0.0 and m.gz_dps == 0.0):
                r |= REJECT_ZERO_READ  # heuristic: exactly zero on all six axes
            elif abs(m.ax_g) > IMU_MAX_ABS_G or abs(m.ay_g) > IMU_MAX_ABS_G or abs(m.az_g) > IMU_MAX_ABS_G:
                r |= REJECT_RANGE
            if r == 0 or r == REJECT_ZERO_READ:
                r |= self._imu_stuck(m)
        if r == 0:
            r |= self._age_check(m.t_ms, now_ms, self._imu)
        v.imu_reject = r
        v.imu_ok = r == 0
        self._set_fault(T.FAULT_IMU_INVALID, not v.imu_ok)
        self._set_fault(T.FAULT_IMU_SATURATED, v.imu_ok and m.saturated)

        # ---- power ----
        p = f.power
        r = 0
        if not p.comm_ok:
            r |= REJECT_COMM
        if not p.valid:
            r |= REJECT_INVALID_FLAG
        if r == 0:
            if not p.data_ready:
                r |= REJECT_NOT_FRESH
            elif not fin(p.bus_v) or not fin(p.current_ma):
                r |= REJECT_NON_FINITE
            elif abs(p.current_ma) > POWER_MAX_ABS_MA or p.bus_v < 0.0 or p.bus_v > POWER_MAX_BUS_V:
                r |= REJECT_RANGE
        if r == 0:
            r |= self._age_check(p.t_ms, now_ms, self._power)
        v.power_reject = r
        v.power_ok = r == 0
        self._set_fault(T.FAULT_POWER_INVALID, not v.power_ok)

        # ---- switches (GPIO: validity + age only) ----
        s = f.switches
        r = 0
        if not s.valid:
            r |= REJECT_INVALID_FLAG
        if r == 0:
            r |= self._age_check(s.t_ms, now_ms, self._sw)
        v.switches_reject = r
        v.switches_ok = r == 0
        self._set_fault(T.FAULT_SWITCH_INVALID, not v.switches_ok)
        return v
