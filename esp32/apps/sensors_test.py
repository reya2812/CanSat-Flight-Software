# sensors_test.py - bench tool: live readings from the GY-91 (IMU + its onboard
# BMP280 pressure sensor) and the INA219, side by side.
#
#     python3 -m mpremote connect <FLIGHT_PORT> run esp32/apps/sensors_test.py     (Ctrl-C to stop)
#
# Standalone: imports nothing from the project, so it works with `mpremote run`.
# I2C on SDA=GPIO21, SCL=GPIO22, 100 kHz (esp32/config/flight_config.py).
# Each sensor is optional: a missing or failing one is reported and the others
# keep running.
#
# Writes to chips (minimal, the same ones the cs_* drivers make):
#   IMU  PWR_MGMT_1 (0x6B): clear the SLEEP bit only, once, if set.
#   BMP280 ctrl_meas (0xF4) = 0x25 per reading: x1 oversampling, forced mode
#          (bring-up choice, not an approved flight setting). 0xF5 is never written.
#   INA219: never written (read-only).
# Register maps, scale factors and the BMP280 compensation are [ASSUMPTION],
# recalled from the datasheets, not checked against the PDFs.
import time

SDA = 21
SCL = 22
FREQ = 100000
PERIOD_MS = 250
DURATION_S = 30

IMU_ADDRS = (0x68, 0x69)
IMU_WHO = {0x68: "MPU-6050", 0x70: "MPU-6500", 0x71: "MPU-9250", 0x73: "MPU-9255"}
IMU_TEMP = {0x68: (340.0, 36.53), 0x70: (333.87, 21.0), 0x71: (333.87, 21.0), 0x73: (333.87, 21.0)}
BARO_ADDRS = (0x76, 0x77)
BARO_IDS = {0x58: "BMP280", 0x60: "BME280"}
INA_ADDRS = (0x40, 0x41, 0x44, 0x45)
SHUNT_OHMS = 0.1          # [docs/03] confirm the "R100" marking on the board


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def first(found, addrs):
    for a in addrs:
        if a in found:
            return a
    return None


class Imu:
    def __init__(self, i2c, addr, out):
        self.i2c, self.addr = i2c, addr
        who = i2c.readfrom_mem(addr, 0x75, 1)[0]
        self.chip = IMU_WHO.get(who)
        if self.chip is None:
            raise ValueError("IMU at 0x%02X: unknown WHO_AM_I 0x%02X, not reading it" % (addr, who))
        self.sens, self.off = IMU_TEMP[who]
        pwr = i2c.readfrom_mem(addr, 0x6B, 1)[0]
        if pwr & 0x40:
            i2c.writeto_mem(addr, 0x6B, bytes([pwr & ~0x40 & 0xFF]))
            time.sleep_ms(100)
            out("IMU was asleep: cleared the SLEEP bit")
        afs = (i2c.readfrom_mem(addr, 0x1C, 1)[0] >> 3) & 3
        gfs = (i2c.readfrom_mem(addr, 0x1B, 1)[0] >> 3) & 3
        self.acc_lsb = 16384.0 / (1 << afs)
        self.gyr_lsb = 131.0 / (1 << gfs)
        out("IMU   : %s at 0x%02X (WHO_AM_I 0x%02X), accel +/-%d g, gyro +/-%d dps"
            % (self.chip, addr, who, 2 << afs, 250 << gfs))

    def read(self):
        b = self.i2c.readfrom_mem(self.addr, 0x3B, 14)
        raw = [s16((b[i] << 8) | b[i + 1]) for i in range(0, 14, 2)]
        a = [raw[i] / self.acc_lsb for i in (0, 1, 2)]
        g = [raw[i] / self.gyr_lsb for i in (4, 5, 6)]
        return a, g, raw[3] / self.sens + self.off


class Baro:
    def __init__(self, i2c, addr, out):
        self.i2c, self.addr = i2c, addr
        cid = i2c.readfrom_mem(addr, 0xD0, 1)[0]
        self.chip = BARO_IDS.get(cid)
        if self.chip is None:
            raise ValueError("baro at 0x%02X: chip ID 0x%02X is not a BMP280/BME280, not reading it" % (addr, cid))
        b = i2c.readfrom_mem(addr, 0x88, 24)
        le = [b[i] | (b[i + 1] << 8) for i in range(0, 24, 2)]
        c = [le[0], s16(le[1]), s16(le[2]), le[3]] + [s16(v) for v in le[4:]]
        if c[0] == 0 or c[3] == 0:
            raise ValueError("baro at 0x%02X: calibration block invalid" % addr)
        self.c = c
        out("BARO  : %s at 0x%02X (chip ID 0x%02X)" % (self.chip, addr, cid))

    def read(self):
        """One forced-mode measurement. Returns (pressure_pa, temp_c)."""
        self.i2c.writeto_mem(self.addr, 0xF4, bytes([0x25]))
        t0 = time.ticks_ms()
        while self.i2c.readfrom_mem(self.addr, 0xF3, 1)[0] & 0x08:
            if time.ticks_diff(time.ticks_ms(), t0) > 50:
                raise OSError("baro conversion did not finish")
            time.sleep_ms(2)
        d = self.i2c.readfrom_mem(self.addr, 0xF7, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        if adc_p == 0x80000 or adc_t == 0x80000:
            raise OSError("baro: no measurement (0x80000)")
        return compensate(adc_t, adc_p, self.c)


def compensate(adc_t, adc_p, c):
    """Bosch floating-point compensation (same as cs_bmp280.compensate)."""
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
        raise OSError("baro compensation divide-by-zero")
    p = 1048576.0 - adc_p
    p = (p - v2 / 4096.0) * 6250.0 / v1
    v1 = P9 * p * p / 2147483648.0
    v2 = p * P8 / 32768.0
    return p + (v1 + v2 + P7) / 16.0, temp


class Ina:
    def __init__(self, i2c, addr, out):
        self.i2c, self.addr = i2c, addr
        cfg = self.reg(0x00)
        out("POWER : INA219 at 0x%02X, config 0x%04X %s (read-only)"
            % (addr, cfg, "(power-on default)" if cfg == 0x399F else "(NOT the default 0x399F)"))

    def reg(self, r):
        b = self.i2c.readfrom_mem(self.addr, r, 2)
        return (b[0] << 8) | b[1]

    def read(self):
        shunt_mv = s16(self.reg(0x01)) * 0.01
        bus = self.reg(0x02)
        return (bus >> 3) * 0.004, shunt_mv / SHUNT_OHMS, bool(bus & 1)


def setup(cls, i2c, addr, label, out):
    if addr is None:
        out("%-6s: not found on the bus" % label)
        return None
    try:
        return cls(i2c, addr, out)
    except (OSError, ValueError) as e:
        out("%-6s: %s" % (label, e))
        return None


def main(machine=None, out=print):
    if machine is None:
        try:
            import machine
        except ImportError:
            out("run this on the ESP32 (no machine module here)")
            return None
    i2c = machine.I2C(0, scl=machine.Pin(SCL), sda=machine.Pin(SDA), freq=FREQ)
    out("== sensors test: %r ==" % (i2c,))
    found = i2c.scan()
    out("I2C scan: %s" % (" ".join("0x%02X" % a for a in found) or "nothing answered"))
    imu = setup(Imu, i2c, first(found, IMU_ADDRS), "IMU", out)
    baro = setup(Baro, i2c, first(found, BARO_ADDRS), "BARO", out)
    ina = setup(Ina, i2c, first(found, INA_ADDRS), "POWER", out)
    sensors = (("imu", imu), ("baro", baro), ("ina", ina))
    if not any(s for _, s in sensors):
        out("RESULT: no supported sensor found. Nothing more to test.")
        return None
    out("")
    out("  ax    ay    az  g |   gx     gy     gz  dps | IMU C |  P hPa    baro C |  bus V    mA")
    t0 = time.ticks_ms()
    n = 0
    errors = {"imu": 0, "baro": 0, "ina": 0}
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < DURATION_S * 1000:
            cols = []
            for name, s in sensors:
                if s is None:
                    cols.append({"imu": "%-44s" % " (no IMU)", "baro": "%-17s" % " (no baro)",
                                 "ina": " (no INA219)"}[name])
                    continue
                try:
                    v = s.read()
                except OSError as e:
                    errors[name] += 1
                    cols.append(" %s error: %r" % (name, e))
                    continue
                if name == "imu":
                    (ax, ay, az), (gx, gy, gz), tc = v
                    cols.append("%5.2f %5.2f %5.2f   | %6.1f %6.1f %6.1f     | %5.1f " % (ax, ay, az, gx, gy, gz, tc))
                elif name == "baro":
                    pa, tc = v
                    cols.append(" %8.2f  %6.2f  " % (pa / 100.0, tc))
                else:
                    bus_v, ma, ovf = v
                    cols.append(" %6.3f %7.1f%s" % (bus_v, ma, " OVF" if ovf else ""))
            out("|".join(cols))
            n += 1
            time.sleep_ms(PERIOD_MS)
    except KeyboardInterrupt:
        pass
    out("stopped: %d rows; read errors imu=%d baro=%d ina=%d" % (n, errors["imu"], errors["baro"], errors["ina"]))
    out("INA219 values only mean something when VIN+/VIN- are wired into a circuit.")
    return n


if __name__ == "__main__":
    main()
