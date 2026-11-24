# sensors.py - mock BMP280, MPU6050, INA219 and limit switches. [SIMULATED]
# (port of lib/hal_mock/MockSensors.h; same fault precedence and noise draws as C++)
#
# These are NOT drivers. Each samples a TruthSource at the VirtualClock's truth
# time, adds deterministic SYNTHETIC noise, then applies active faults.
# Fault precedence in read(): not initialised / NotDetected / Dropout (invalid) >
# CommFailure (invalid, comm_ok False) > Stale (repeat last sample incl. old
# timestamp) > NotReady (previous values, new timestamp, data_ready False) >
# StuckOutput (previous values, new timestamp, data_ready True) > fresh value +
# noise > ZeroRead > NaNValue > OutOfRange (overrides reported VALID).
from cansat.core import types as T
from cansat.core.num import f32
from cansat.hal.interfaces import Barometer, DigitalInputs, Imu, PowerMonitor
from cansat.mock import fault_injector as FI
from cansat.mock.rng import Rng

MPU6050_FULL_SCALE_G = 16.0  # [ASSUMPTION] MPU6050 max range, datasheet recalled
NAN = float("nan")


class SensorNoise:
    """Baseline uniform noise amplitudes; SYNTHETIC values from scenarios, default none."""

    def __init__(self, pressure_pa=0.0, temp_c=0.0, accel_g=0.0, gyro_dps=0.0, bus_v=0.0, current_ma=0.0):
        self.pressure_pa = f32(pressure_pa)
        self.temp_c = f32(temp_c)
        self.accel_g = f32(accel_g)
        self.gyro_dps = f32(gyro_dps)
        self.bus_v = f32(bus_v)
        self.current_ma = f32(current_ma)


def _copy(sample, cls):
    c = cls()
    c.__dict__.update(sample.__dict__)
    return c


class _MockBase:
    TARGET = None
    SAMPLE = None

    def __init__(self, clock, truth, faults, noise, seed):
        self._clock, self._truth, self._faults, self._noise = clock, truth, faults, noise
        self._rng = Rng(seed)
        self._initialized = False
        self._has_last = False
        self._last = None

    def begin(self):
        self._initialized = not self._faults.query(self.TARGET, self._clock.truth_ms()).not_detected
        self._has_last = False
        return self._initialized

    def read(self):
        s = self.SAMPLE()
        s.t_ms = self._clock.now_ms()
        a = self._faults.query(self.TARGET, self._clock.truth_ms())
        if not self._initialized or a.not_detected or a.dropout:
            return s
        if a.comm_failure:
            return s
        if a.stale:
            return _copy(self._last, self.SAMPLE) if self._has_last else s
        if (a.not_ready or a.stuck_output) and self._has_last:
            r = _copy(self._last, self.SAMPLE)
            r.t_ms = s.t_ms
            r.data_ready = not a.not_ready
            return r
        self._fresh(s, self._truth.truth_at(self._clock.truth_ms()), a)
        s.valid = s.comm_ok = s.data_ready = True
        self._overrides(s, a)
        self._last = _copy(s, self.SAMPLE)
        self._has_last = True
        return s


class MockBarometer(_MockBase, Barometer):
    TARGET = FI.TARGET_BARO
    SAMPLE = T.BaroSample

    def _fresh(self, s, t, a):
        s.pressure_pa = f32(t.pressure_pa + self._rng.uniform(f32(self._noise.pressure_pa + a.noise_amp)))
        s.temp_c = f32(t.temp_c + self._rng.uniform(self._noise.temp_c))

    def _overrides(self, s, a):
        if a.zero:
            s.pressure_pa = s.temp_c = 0.0
        if a.nan:
            s.pressure_pa = s.temp_c = NAN
        if a.out_of_range:
            s.pressure_pa = a.out_of_range_value


class MockImu(_MockBase, Imu):
    TARGET = FI.TARGET_IMU
    SAMPLE = T.ImuSample

    def _fresh(self, s, t, a):
        acc, gyr = [0.0] * 3, [0.0] * 3
        amp = f32(self._noise.accel_g + a.noise_amp)
        for i in range(3):
            acc[i] = f32(t.accel_g[i] + self._rng.uniform(amp))
            gyr[i] = f32(t.gyro_dps[i] + self._rng.uniform(self._noise.gyro_dps))
            if acc[i] > MPU6050_FULL_SCALE_G:
                acc[i] = MPU6050_FULL_SCALE_G
                s.saturated = True
            elif acc[i] < -MPU6050_FULL_SCALE_G:
                acc[i] = -MPU6050_FULL_SCALE_G
                s.saturated = True
        s.ax_g, s.ay_g, s.az_g = acc
        s.gx_dps, s.gy_dps, s.gz_dps = gyr

    def _overrides(self, s, a):
        if a.zero:
            s.ax_g = s.ay_g = s.az_g = s.gx_dps = s.gy_dps = s.gz_dps = 0.0
            s.saturated = False
        if a.nan:
            s.ax_g = s.ay_g = s.az_g = NAN
        if a.out_of_range:
            s.ax_g = a.out_of_range_value


class MockPowerMonitor(_MockBase, PowerMonitor):
    TARGET = FI.TARGET_POWER
    SAMPLE = T.PowerSample

    def _fresh(self, s, t, a):
        s.bus_v = f32(t.bus_v + self._rng.uniform(self._noise.bus_v))
        s.current_ma = f32(t.current_ma + self._rng.uniform(f32(self._noise.current_ma + a.noise_amp)))

    def _overrides(self, s, a):
        if a.zero:
            s.bus_v = s.current_ma = 0.0
        if a.nan:
            s.bus_v = s.current_ma = NAN
        if a.out_of_range:
            s.current_ma = a.out_of_range_value


class MockSwitches(DigitalInputs):
    """Two limit switches. Truth "mounted" means both closed. closed_level_high[k] is
    the SYNTHETIC wiring assumption for the level meaning "closed" (OD-051)."""

    def __init__(self, clock, truth, faults, closed_level_high_1, closed_level_high_2):
        self._clock, self._truth, self._faults = clock, truth, faults
        self._closed_high = [closed_level_high_1, closed_level_high_2]

    def read(self):
        s = T.SwitchSample()
        s.t_ms = self._clock.now_ms()
        t = self._clock.truth_ms()
        truth = self._truth.truth_at(t)
        any_dropout = False
        for k, target in enumerate((FI.TARGET_SWITCH1, FI.TARGET_SWITCH2)):
            a = self._faults.query(target, t)
            if a.dropout or a.not_detected:
                any_dropout = True
            closed = truth.mounted
            if a.stuck_closed:
                closed = True
            if a.stuck_open:
                closed = False
            if a.bounce and ((t - a.bounce_start_ms) // a.bounce_period_ms) % 2 == 1:
                closed = not closed
            s.raw[k] = self._closed_high[k] if closed else not self._closed_high[k]
        s.valid = not any_dropout
        if not s.valid:
            s.raw[0] = s.raw[1] = False
        return s

    def level_means_closed(self, k, level):
        return level == self._closed_high[k]
