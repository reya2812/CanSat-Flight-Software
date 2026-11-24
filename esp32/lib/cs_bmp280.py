# cs_bmp280.py - Bosch BMP280 / BME280 (temperature + pressure path) I2C driver.
#
# Portable: the I2C object is injected (machine.I2C on the board, a fake in
# tests). Register map and compensation formula are [ASSUMPTION]: recalled from
# the Bosch BMP280 datasheet (same as bringup/esp32_hw_diag.py), NOT yet
# checked against the PDF. BME280 humidity is not read.
#
# Non-blocking two-phase forced mode: each read() collects the conversion
# triggered by the previous read() and triggers the next one, so no call ever
# waits for a conversion. The first read() after begin() returns NOT_READY.
#
# Writes to the chip (documented, minimal):
#   ctrl_meas (0xF4) = 0x25 per measurement: osrs_t x1, osrs_p x1, forced mode.
#   BRING-UP choice, NOT an approved flight oversampling/filter setting.
#   The config register (0xF5: standby, IIR filter) is never written.
import cs_proto as P

REG_ID = 0xD0
REG_CALIB = 0x88        # 24 bytes, little-endian: T1 u16, T2..T3 s16, P1 u16, P2..P9 s16
REG_STATUS = 0xF3       # bit 3: measuring
REG_CTRL_MEAS = 0xF4
REG_DATA = 0xF7         # press msb/lsb/xlsb, temp msb/lsb/xlsb (20-bit)
CTRL_FORCED_X1 = 0x25
ADC_SKIPPED = 0x80000   # value when no measurement was made
SUPPORTED = {0x58: "BMP280", 0x60: "BME280"}
KNOWN_UNSUPPORTED = {0x55: "BMP180", 0x56: "BMP280 engineering sample", 0x57: "BMP280 engineering sample"}
ADDRESSES = (0x76, 0x77)


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def le16(b, i):
    return b[i] | (b[i + 1] << 8)


def parse_calib(b):
    c = [le16(b, 0), s16(le16(b, 2)), s16(le16(b, 4)), le16(b, 6)]
    c += [s16(le16(b, i)) for i in range(8, 24, 2)]
    return tuple(c)


def compensate(adc_t, adc_p, c):
    """Bosch floating-point compensation. Returns (temp_c, pressure_pa or None)."""
    T1, T2, T3, P1, P2, P3, P4, P5, P6, P7, P8, P9 = c
    v1 = (adc_t / 16384.0 - T1 / 1024.0) * T2
    v2 = (adc_t / 131072.0 - T1 / 8192.0) * (adc_t / 131072.0 - T1 / 8192.0) * T3
    t_fine = v1 + v2
    temp = t_fine / 5120.0
    v1 = t_fine / 2.0 - 64000.0
    v2 = v1 * v1 * P6 / 32768.0
    v2 = v2 + v1 * P5 * 2.0
    v2 = v2 / 4.0 + P4 * 65536.0
    v1 = (P3 * v1 * v1 / 524288.0 + P2 * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * P1
    if v1 == 0.0:
        return temp, None
    p = 1048576.0 - adc_p
    p = (p - v2 / 4096.0) * 6250.0 / v1
    v1 = P9 * p * p / 2147483648.0
    v2 = p * P8 / 32768.0
    return temp, p + (v1 + v2 + P7) / 16.0


def altitude_m(pressure_pa, reference_pa):
    """[ASSUMPTION] ISA approximation, identical to cansat.core.fmath.altitude_above_reference
    (checked against it by esp32/tests). Valid in the troposphere only."""
    return 44330.0 * (1.0 - (pressure_pa / reference_pa) ** (1.0 / 5.255))


class BaroReading:
    def __init__(self, t_ms=0, status=P.ST_NOT_PRESENT, error=""):
        self.t_ms = t_ms
        self.pressure_pa = 0.0
        self.temp_c = 0.0
        self.valid = False
        self.comm_ok = False
        self.data_ready = False
        self.status = status
        self.error = error


class BMP280:
    kind = "baro"

    def __init__(self, i2c, addr):
        self.i2c = i2c
        self.addr = addr
        self.chip_id = None
        self.chip = None
        self.calib = None
        self.status = P.ST_NOT_PRESENT
        self.error = ""
        self._triggered = False

    def name(self):
        return "%s@0x%02X" % (self.chip or "baro", self.addr)

    def begin(self):
        self._triggered = False
        self.chip_id = self.i2c.readfrom_mem(self.addr, REG_ID, 1)[0]
        self.chip = SUPPORTED.get(self.chip_id)
        if self.chip is None:
            self.status = P.ST_UNKNOWN_CHIP
            self.error = "chip ID 0x%02X%s is not a supported BMP280/BME280" % (
                self.chip_id, " (" + KNOWN_UNSUPPORTED[self.chip_id] + ")" if self.chip_id in KNOWN_UNSUPPORTED else "")
            return False
        raw = self.i2c.readfrom_mem(self.addr, REG_CALIB, 24)
        c = parse_calib(raw)
        if c[0] == 0 or c[3] == 0 or raw == b"\xff" * 24:
            self.status = P.ST_INIT_FAILED
            self.error = "calibration block invalid (T1=%d P1=%d)" % (c[0], c[3])
            return False
        self.calib = c
        self._trigger()
        self.status = P.ST_NOT_READY
        self.error = ""
        return True

    def _trigger(self):
        self.i2c.writeto_mem(self.addr, REG_CTRL_MEAS, bytes([CTRL_FORCED_X1]))
        self._triggered = True

    def failed(self, t_ms, status, error):
        return BaroReading(t_ms, status, error)

    def read(self, t_ms):
        r = BaroReading(t_ms, P.ST_NOT_READY)
        if not self._triggered:
            self._trigger()
            r.comm_ok = True
            return r
        if self.i2c.readfrom_mem(self.addr, REG_STATUS, 1)[0] & 0x08:
            r.comm_ok = True  # still converting: not an error, just not ready
            return r
        d = self.i2c.readfrom_mem(self.addr, REG_DATA, 6)
        self._trigger()
        r.comm_ok = True
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        if adc_p == ADC_SKIPPED or adc_t == ADC_SKIPPED:
            r.error = "no measurement (0x80000)"
            return r
        r.data_ready = True
        temp, pa = compensate(adc_t, adc_p, self.calib)
        if pa is None:
            r.status, r.error = P.ST_IMPLAUSIBLE, "compensation divide-by-zero"
            return r
        r.pressure_pa, r.temp_c = pa, temp
        if not (P.BARO_P_MIN_PA <= pa <= P.BARO_P_MAX_PA and P.BARO_T_MIN_C <= temp <= P.BARO_T_MAX_C):
            r.status, r.error = P.ST_IMPLAUSIBLE, "%.1f Pa / %.2f C outside the sensor's range" % (pa, temp)
            return r
        r.valid = True
        r.status = P.ST_OK
        return r
