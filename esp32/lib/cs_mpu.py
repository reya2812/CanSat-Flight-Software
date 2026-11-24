# cs_mpu.py - InvenSense MPU-family IMU driver (GY-91 / GY-521 boards), accel + gyro + temp.
#
# Portable: I2C object injected. Register map and scale factors are
# [ASSUMPTION], recalled from the MPU-6050 / MPU-6500 / MPU-9250 register maps
# and NOT yet checked against the PDFs.
#
# Identity comes ONLY from WHO_AM_I (0x75). An unlisted value is reported as
# UNKNOWN_CHIP with its raw hex and begin() fails: data from an unidentified
# chip is never marked valid. (bringup/esp32_hw_diag.py still attempts one raw
# read of an unknown chip for diagnosis.)
#
# Writes to the chip (documented, minimal):
#   PWR_MGMT_1 (0x6B): clears the SLEEP bit if it is set (required for any data;
#   the chip powers up asleep). Clock source, ranges, filters and sample rate
#   are NOT changed: full scale is read back from the chip and used for scaling.
#   The magnetometer (AK8963 on MPU-9250) is not enabled.
import cs_proto as P

REG_WHO_AM_I = 0x75
REG_PWR_MGMT_1 = 0x6B
REG_GYRO_CONFIG = 0x1B
REG_ACCEL_CONFIG = 0x1C
REG_INT_STATUS = 0x3A     # bit 0 DATA_RDY_INT; followed by ACCEL_XOUT_H at 0x3B
SLEEP_BIT = 0x40
ADDRESSES = (0x68, 0x69)
WHO_AM_I = {0x68: "MPU-6050", 0x70: "MPU-6500", 0x71: "MPU-9250", 0x73: "MPU-9255"}
# temperature: deg C = raw / sensitivity + offset  [ASSUMPTION, recalled]
TEMP_COEFF = {0x68: (340.0, 36.53), 0x70: (333.87, 21.0), 0x71: (333.87, 21.0), 0x73: (333.87, 21.0)}


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


class ImuReading:
    def __init__(self, t_ms=0, status=P.ST_NOT_PRESENT, error=""):
        self.t_ms = t_ms
        self.ax_g = self.ay_g = self.az_g = 0.0
        self.gx_dps = self.gy_dps = self.gz_dps = 0.0
        self.temp_c = 0.0
        self.temp_valid = False
        self.saturated = False
        self.valid = False
        self.comm_ok = False
        self.data_ready = False
        self.status = status
        self.error = error


class MpuImu:
    kind = "imu"

    def __init__(self, i2c, addr):
        self.i2c = i2c
        self.addr = addr
        self.who = None
        self.chip = None
        self.accel_fs_g = None
        self.gyro_fs_dps = None
        self.woke = False
        self.status = P.ST_NOT_PRESENT
        self.error = ""

    def name(self):
        return "%s@0x%02X" % (self.chip or "imu", self.addr)

    def begin(self):
        self.who = self.i2c.readfrom_mem(self.addr, REG_WHO_AM_I, 1)[0]
        self.chip = WHO_AM_I.get(self.who)
        if self.chip is None:
            self.status = P.ST_UNKNOWN_CHIP
            self.error = ("UNKNOWN identity: WHO_AM_I=0x%02X (known: 0x68 MPU-6050, 0x70 MPU-6500, "
                          "0x71 MPU-9250, 0x73 MPU-9255)" % self.who)
            return False
        pwr = self.i2c.readfrom_mem(self.addr, REG_PWR_MGMT_1, 1)[0]
        if pwr & SLEEP_BIT:
            self.i2c.writeto_mem(self.addr, REG_PWR_MGMT_1, bytes([pwr & ~SLEEP_BIT & 0xFF]))
            self.woke = True
        afs = (self.i2c.readfrom_mem(self.addr, REG_ACCEL_CONFIG, 1)[0] >> 3) & 0x03
        gfs = (self.i2c.readfrom_mem(self.addr, REG_GYRO_CONFIG, 1)[0] >> 3) & 0x03
        self.accel_fs_g = 2 << afs        # 2/4/8/16 g
        self.gyro_fs_dps = 250 << gfs     # 250/500/1000/2000 dps
        self._acc_lsb = 16384.0 / (1 << afs)
        self._gyr_lsb = 131.0 / (1 << gfs)
        self.status = P.ST_NOT_READY
        self.error = ""
        return True

    def failed(self, t_ms, status, error):
        return ImuReading(t_ms, status, error)

    def read(self, t_ms):
        b = self.i2c.readfrom_mem(self.addr, REG_INT_STATUS, 15)
        r = ImuReading(t_ms, P.ST_OK)
        r.comm_ok = True
        # DATA_RDY_INT [ASSUMPTION]: set by the chip when a new sample is in the
        # output registers. Whether it is set while the interrupt is not enabled
        # is a bench check (docs/10 checklist H-IMU-3).
        r.data_ready = bool(b[0] & 0x01)
        raw = [s16((b[1 + i] << 8) | b[2 + i]) for i in range(0, 14, 2)]
        if all(v == 0 for v in raw) or all(v == -1 for v in raw):
            r.status = P.ST_IMPLAUSIBLE
            r.error = "data registers all %s (chip asleep/reset or bus fault)" % ("0" if raw[0] == 0 else "0xFFFF")
            return r
        r.ax_g, r.ay_g, r.az_g = (raw[i] / self._acc_lsb for i in (0, 1, 2))
        r.gx_dps, r.gy_dps, r.gz_dps = (raw[i] / self._gyr_lsb for i in (4, 5, 6))
        r.saturated = any(raw[i] in (32767, -32768) for i in (0, 1, 2))
        sens, off = TEMP_COEFF[self.who]
        r.temp_c = raw[3] / sens + off
        r.temp_valid = P.IMU_T_MIN_C <= r.temp_c <= P.IMU_T_MAX_C
        r.valid = True
        return r
