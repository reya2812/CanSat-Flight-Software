# cs_sensors.py - uniform sensor channels and the flight-board sensor suite (portable).
#
# Every sensor is wrapped in a SensorChannel exposing the same things:
#   present, init_ok, status (cs_proto.ST_*), error, last (latest reading),
#   t_ms (timestamp of `last`), valid(), counters.
# A driver exception is caught inside its channel: one failed sensor never
# stops the others or the caller. A sensor whose init failed, or which fails
# MAX_CONSECUTIVE_ERRORS reads in a row, is re-initialised every retry_ms.
#
# SensorSuite.discover() identifies devices by ID register (never by address
# alone), never creates two channels for one I2C address, and raises
# baro_dup_suspect when fewer barometers answer than configured: two BMP280s
# strapped to the same address are electrically indistinguishable from one.
import cs_proto as P
from cs_bmp280 import ADDRESSES as BMP_ADDRS, BMP280, altitude_m
from cs_ina219 import INA219
from cs_mpu import ADDRESSES as MPU_ADDRS, MpuImu
from cs_util import ticks_add, ticks_diff

MAX_CONSECUTIVE_ERRORS = 3


class SensorChannel:
    def __init__(self, label, driver, retry_ms):
        self.label = label
        self.driver = driver
        self.retry_ms = retry_ms
        self.present = driver is not None
        self.init_ok = False
        self.status = P.ST_NOT_PRESENT
        self.error = "" if driver is not None else "no device answered"
        self.last = None
        self.t_ms = None
        self.n_ok = 0
        self.n_err = 0
        self.n_init = 0
        self.consecutive_err = 0
        self._next_init = None

    def begin(self, now):
        if self.driver is None:
            return False
        self.n_init += 1
        try:
            ok = self.driver.begin() is True
            self.status = self.driver.status
            self.error = self.driver.error
        except Exception as e:
            ok = False
            self.status = P.ST_INIT_FAILED
            self.error = "init raised %r" % (e,)
        self.init_ok = ok
        self.consecutive_err = 0
        self._next_init = None if ok else ticks_add(now, self.retry_ms)
        return ok

    def sample(self, now, t_ms):
        """Read once (re-initialising if due). Returns the reading or None. Never raises."""
        if self.driver is None:
            return None
        if not self.init_ok:
            if self._next_init is not None and ticks_diff(now, self._next_init) < 0:
                return None   # `last` is already an invalid reading from the failure
            if not self.begin(now):
                # never leave an older valid reading in `last` while the sensor is down
                self.last = self.driver.failed(t_ms, self.status, self.error)
                self.t_ms = t_ms
                return None
        try:
            r = self.driver.read(t_ms)
        except Exception as e:
            r = self.driver.failed(t_ms, P.ST_READ_ERROR, "read raised %r" % (e,))
        self.last = r
        self.t_ms = t_ms
        self.status = r.status
        self.error = r.error
        if r.status in (P.ST_READ_ERROR, P.ST_IMPLAUSIBLE):
            self.n_err += 1
            self.consecutive_err += 1
            if self.consecutive_err >= MAX_CONSECUTIVE_ERRORS:
                self.init_ok = False   # re-initialise (e.g. IMU reset back to sleep) after retry_ms
                self._next_init = ticks_add(now, self.retry_ms)
        else:
            self.consecutive_err = 0
            if r.valid:
                self.n_ok += 1
        return r

    def valid(self):
        return self.last is not None and self.last.valid

    def name(self):
        return self.driver.name() if self.driver is not None else self.label


class SensorSuite:
    def __init__(self, cfg):
        self.cfg = cfg
        self.scan = []
        self.scan_error = None
        self.baro1 = SensorChannel("baro1", None, cfg.SENSOR_RETRY_MS)
        self.baro2 = SensorChannel("baro2", None, cfg.SENSOR_RETRY_MS)
        self.imu = SensorChannel("imu", None, cfg.SENSOR_RETRY_MS)
        self.power = SensorChannel("power", None, cfg.SENSOR_RETRY_MS)
        self.extra = []              # identified-but-unused channels (e.g. a second IMU)
        self.baro_identified = []    # addresses holding a supported BMP280/BME280
        self.baro_dup_suspect = False
        self.reference_pa = getattr(cfg, "BARO_REFERENCE_PA", None)
        self.reference_auto = self.reference_pa is None
        self.alt_m = None
        self._next_sample = None

    def channels(self):
        return (self.baro1, self.baro2, self.imu, self.power)

    # ---- discovery ----
    def discover(self, i2c, now):
        cfg = self.cfg
        try:
            self.scan = sorted(i2c.scan())
        except Exception as e:
            self.scan = []
            self.scan_error = "I2C scan raised %r" % (e,)
        addrs = set(self.scan)
        retry = cfg.SENSOR_RETRY_MS
        # barometers: one channel per responding address, identified by chip ID
        baros = []
        for a in BMP_ADDRS:
            if a in addrs:
                ch = SensorChannel("baro@0x%02X" % a, BMP280(i2c, a), retry)
                ch.begin(now)
                baros.append(ch)
        good = [ch for ch in baros if ch.driver.chip is not None]
        self.baro_identified = [ch.driver.addr for ch in good]
        self.baro_dup_suspect = len(good) < cfg.EXPECTED_BAROMETERS
        primary = None
        want = getattr(cfg, "BARO_PRIMARY_ADDR", None)
        for ch in good:
            if want is not None and ch.driver.addr == want:
                primary = ch
        if primary is None and good:
            primary = good[0]          # lowest identified address
        if primary is None and baros:
            primary = baros[0]         # unidentified device: kept for reporting, never valid
        rest = [ch for ch in baros if ch is not primary]
        if primary is not None:
            primary.label = "baro1"
            self.baro1 = primary
        if rest:
            rest[0].label = "baro2"
            self.baro2 = rest[0]
        # IMU: first MPU-family address that answers; any other is reported, not used
        imus = []
        for a in MPU_ADDRS:
            if a in addrs:
                ch = SensorChannel("imu@0x%02X" % a, MpuImu(i2c, a), retry)
                ch.begin(now)
                imus.append(ch)
        if imus:
            imus[0].label = "imu"
            self.imu = imus[0]
            self.extra.extend(imus[1:])
        # INA219 at the configured address only
        if cfg.INA219_ADDR in addrs:
            drv = INA219(i2c, cfg.INA219_ADDR, cfg.INA219_SHUNT_OHMS,
                         getattr(cfg, "INA219_BUS_CONNECTED", False), getattr(cfg, "INA219_SHUNT_CONNECTED", False))
            self.power = SensorChannel("power", drv, retry)
            self.power.begin(now)
        return self

    # ---- sampling ----
    def due(self, now):
        return self._next_sample is None or ticks_diff(now, self._next_sample) >= 0

    def sample(self, now, t_ms):
        """Sample every channel once (each isolated) and update altitude."""
        self._next_sample = ticks_add(now, self.cfg.SENSOR_PERIOD_MS)
        for ch in self.channels():
            ch.sample(now, t_ms)
        self._update_altitude()

    def _update_altitude(self):
        self.alt_m = None
        if not self.baro1.valid():
            return
        p = self.baro1.last.pressure_pa
        if self.reference_pa is None:
            self.reference_pa = p   # first valid reading after boot (F_ALT_REF_AUTO)
        try:
            self.alt_m = altitude_m(p, self.reference_pa)
        except Exception:
            self.alt_m = None

    def power_gated(self):
        d = self.power.driver
        return d is None or d.gated()
