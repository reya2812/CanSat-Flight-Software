# esp32_hw_diag.py - CanSat hardware BRING-UP DIAGNOSTIC for ESP32 MicroPython.
#
# NOT flight software. Imports nothing from micropython/cansat. Run it by hand
# on the bench to check the physical circuit, then discard its results as
# "bench observation", not flight validation.
#
# What it does (each test is isolated: one failure never stops the others):
#   1. I2C bus on the user-reported pins; scan; print every address in hex.
#   2. Identify devices by their ID registers (never by address alone).
#   3. IMU (GY-91: MPU-family chip): identify via WHO_AM_I, one raw read.
#   4. BMP280(s) (GY-91 on-board + standalone): identify via chip ID, one
#      forced measurement each, flag possible duplicate addresses.
#   5. INA219: READ-ONLY logic-interface check (no load/battery on VIN+/VIN-).
#   6. SD card: DISABLED by default (SKIP) until the module's supply/voltage
#      compatibility is confirmed. When enabled: mount, list, unmount. No writes.
# HC-12, servos, buzzers, batteries and deployment hardware are NOT touched.
# The only pins configured are I2C SDA/SCL and (if SD is enabled) the SD SPI
# pins, which machine.SDCard drives itself. No PWM, no DAC, no other outputs.
#
# Register maps and conversion formulas are [ASSUMPTION]: recalled from the
# Bosch BMP280, InvenSense MPU-6050/6500/9250 and TI INA219 datasheets and NOT
# yet checked against those PDFs. Treat every printed value as unverified.
#
# Writes made to sensors (all documented, all minimal):
#   - MPU: PWR_MGMT_1 (0x6B) sleep bit cleared once, then the original value
#     restored at the end of the test.
#   - BMP280: ctrl_meas (0xF4) = 0x25 once per device (one forced measurement,
#     oversampling x1/x1). The chip returns to sleep by itself afterwards.
#     Diagnostic choice only - NOT a flight oversampling setting (undecided).
#   - INA219: none (read-only).
import os
import time

try:
    import machine
except ImportError:  # laptop: the test injects a fake `machine` module first
    machine = None

# ---------------------------------------------------------------------------
# Configuration. Pins are USER-REPORTED WIRING (2026-11-19), UNVERIFIED.
# They are NOT the flight configuration (micropython/cansat/config/
# hardware_config.py keeps every pin TBD, OD-054).
# ---------------------------------------------------------------------------
I2C_ID = 0
I2C_SDA = 21          # user-reported, unverified
I2C_SCL = 22          # user-reported, unverified
I2C_FREQ_HZ = 100000  # diagnostic choice: standard mode, the most tolerant speed
SD_SCK = 18           # user-reported, unverified
SD_MISO = 19          # user-reported, unverified
SD_MOSI = 23          # user-reported, unverified
SD_CS = 5             # user-reported, unverified
SD_SLOT = 2           # [ASSUMPTION] machine.SDCard slot 2 = SPI mode on the ESP32 port
SD_MOUNT_POINT = "/sd"
# Leave False until the SD module's supply and logic-level compatibility with
# 3.3 V is confirmed. While False the SD test prints SKIP and touches nothing.
SD_SUPPLY_CONFIRMED = False
# User-reported hardware: GY-91 (may contain a BMP280) + one standalone BMP280.
EXPECTED_BMP280_COUNT = 2

# ---------------------------------------------------------------------------
# Datasheet constants [ASSUMPTION, recalled - verify against the datasheets]
# ---------------------------------------------------------------------------
MPU_ADDRS = (0x68, 0x69)
MPU_REG_WHO_AM_I = 0x75
MPU_REG_PWR_MGMT_1 = 0x6B
MPU_REG_GYRO_CONFIG = 0x1B
MPU_REG_ACCEL_CONFIG = 0x1C
MPU_REG_ACCEL_XOUT_H = 0x3B  # 14 bytes: ax, ay, az, temp, gx, gy, gz (big-endian int16)
MPU_SLEEP_BIT = 0x40
MPU_WHO_AM_I = {0x68: "MPU-6050/6000", 0x70: "MPU-6500", 0x71: "MPU-9250", 0x73: "MPU-9255"}
AK8963_ADDR = 0x0C           # MPU-9250 magnetometer; only visible if the IMU's I2C bypass is on
AK8963_REG_WIA = 0x00
AK8963_WIA = 0x48

BMP_ADDRS = (0x76, 0x77)
BMP_REG_ID = 0xD0
BMP_CHIP_IDS = {0x58: "BMP280", 0x60: "BME280", 0x55: "BMP180", 0x56: "BMP280 (sample)",
                0x57: "BMP280 (sample)"}
BMP_REG_CALIB = 0x88         # 24 bytes: T1 u16, T2..T3 s16, P1 u16, P2..P9 s16 (little-endian)
BMP_REG_STATUS = 0xF3        # bit 3: measuring
BMP_REG_CTRL_MEAS = 0xF4
BMP_CTRL_FORCED_X1 = 0x25    # osrs_t=001, osrs_p=001, mode=01 (forced)
BMP_REG_DATA = 0xF7          # 6 bytes: press msb/lsb/xlsb, temp msb/lsb/xlsb (20-bit)
BMP_ADC_SKIPPED = 0x80000    # value reported when no measurement was made
BMP_PRESSURE_RANGE_PA = (30000.0, 110000.0)  # sensor's stated range
BMP_TEMP_RANGE_C = (-40.0, 85.0)

INA_ADDRS = tuple(range(0x40, 0x50))
INA_REG_CONFIG = 0x00
INA_REG_SHUNT = 0x01         # signed, LSB 10 uV
INA_REG_BUS = 0x02           # bits 15..3 value (LSB 4 mV), bit 1 CNVR, bit 0 OVF
INA_CONFIG_DEFAULT = 0x399F  # power-on value

PASS, FAIL, WARN, SKIP, INFO = "PASS", "FAIL", "WARN", "SKIP", "INFO"


# ---------------------------------------------------------------------------
# Small helpers (MicroPython-compatible: no f-strings needed, no signed= kw)
# ---------------------------------------------------------------------------
def sleep_ms(ms):
    f = getattr(time, "sleep_ms", None)
    if f:
        f(ms)
    else:
        time.sleep(ms / 1000.0)


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def be16(b, i):
    return (b[i] << 8) | b[i + 1]


def le16(b, i):
    return b[i] | (b[i + 1] << 8)


def hexlist(addrs):
    return " ".join("0x%02X" % a for a in addrs) if addrs else "(none)"


class Report:
    def __init__(self, out=print):
        self.rows = []
        self._out = out

    def add(self, status, name, detail):
        self.rows.append((status, name, detail))
        self._out("[%s] %s: %s" % (status, name, detail))

    def note(self, text):
        self._out("       " + text)

    def counts(self):
        c = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0, INFO: 0}
        for s, _, _ in self.rows:
            c[s] = c.get(s, 0) + 1
        return c


def guarded(report, name, fn, *args):
    """Run one test; any exception becomes FAIL for that test only."""
    try:
        return fn(report, *args)
    except Exception as e:  # noqa: BLE001 - isolation is the point
        report.add(FAIL, name, "unexpected error: %r" % (e,))
        return None


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------
def make_i2c():
    return machine.I2C(I2C_ID, scl=machine.Pin(I2C_SCL), sda=machine.Pin(I2C_SDA), freq=I2C_FREQ_HZ)


def test_i2c_scan(report):
    try:
        i2c = make_i2c()
    except Exception as e:
        report.add(FAIL, "I2C init", "SDA=GPIO%d SCL=GPIO%d: %r" % (I2C_SDA, I2C_SCL, e))
        return None, []
    addrs = sorted(i2c.scan())
    if not addrs:
        report.add(FAIL, "I2C scan", "no device answered. Check SDA/SCL wiring, 3.3 V supply, GND and pull-ups")
        return i2c, addrs
    if len(addrs) > 32:
        report.add(FAIL, "I2C scan", "%d addresses answered: bus looks shorted or missing pull-ups" % len(addrs))
        return i2c, addrs
    report.add(PASS, "I2C scan", "%d device(s): %s" % (len(addrs), hexlist(addrs)))
    return i2c, addrs


# ---------------------------------------------------------------------------
# IMU (GY-91 MPU-family)
# ---------------------------------------------------------------------------
def test_imu(report, i2c, addrs):
    found = [a for a in MPU_ADDRS if a in addrs]
    if not found:
        report.add(FAIL, "IMU", "no device at 0x68/0x69 (MPU-family addresses)")
        return
    for a in found:
        guarded(report, "IMU @0x%02X" % a, _imu_one, i2c, a)
    if AK8963_ADDR in addrs:
        guarded(report, "Magnetometer @0x0C", _ak8963, i2c)
    else:
        report.add(INFO, "Magnetometer", "not on the main bus (an MPU-9250's AK8963 is visible only with the "
                                         "IMU's I2C bypass enabled; not enabled here to avoid extra writes)")


def _imu_one(report, i2c, a):
    name = "IMU @0x%02X" % a
    who = i2c.readfrom_mem(a, MPU_REG_WHO_AM_I, 1)[0]
    chip = MPU_WHO_AM_I.get(who)
    # An unlisted identity does not mean the device is unusable: still try the
    # MPU-family register reads below, but the result can only be WARN.
    label = chip if chip else "UNKNOWN identity (WHO_AM_I=0x%02X)" % who
    pwr = i2c.readfrom_mem(a, MPU_REG_PWR_MGMT_1, 1)[0]
    woke = False
    try:
        if pwr & MPU_SLEEP_BIT:
            i2c.writeto_mem(a, MPU_REG_PWR_MGMT_1, bytes([pwr & ~MPU_SLEEP_BIT & 0xFF]))  # documented write
            woke = True
            sleep_ms(100)  # diagnostic wait for first samples
        afs = (i2c.readfrom_mem(a, MPU_REG_ACCEL_CONFIG, 1)[0] >> 3) & 0x03
        gfs = (i2c.readfrom_mem(a, MPU_REG_GYRO_CONFIG, 1)[0] >> 3) & 0x03
        b = i2c.readfrom_mem(a, MPU_REG_ACCEL_XOUT_H, 14)
    finally:
        if woke:
            i2c.writeto_mem(a, MPU_REG_PWR_MGMT_1, bytes([pwr]))  # restore as found
    raw = [s16(be16(b, i)) for i in range(0, 14, 2)]
    acc_lsb = 16384.0 / (1 << afs)   # +-2/4/8/16 g [ASSUMPTION]
    gyr_lsb = 131.0 / (1 << gfs)     # +-250/500/1000/2000 dps [ASSUMPTION]
    ax, ay, az = (raw[i] / acc_lsb for i in (0, 1, 2))
    gx, gy, gz = (raw[i] / gyr_lsb for i in (4, 5, 6))
    if all(v == 0 for v in raw) or all(v == -1 for v in raw):
        report.add(FAIL, name, "%s: data registers read all %s" % (label, "zero" if raw[0] == 0 else "0xFFFF"))
        return
    if chip:
        report.add(PASS, name, "%s (WHO_AM_I=0x%02X) read OK" % (chip, who))
    else:
        report.add(WARN, name, "UNKNOWN: WHO_AM_I=0x%02X is not in the known list (0x68 MPU-6050, 0x70 MPU-6500, "
                               "0x71 MPU-9250, 0x73 MPU-9255). Data below assumes the MPU-family register map" % who)
    report.note("accel g: %.3f %.3f %.3f  |a|=%.3f (about 1 g expected if stationary; not a pass criterion)"
                % (ax, ay, az, (ax * ax + ay * ay + az * az) ** 0.5))
    report.note("gyro dps: %.2f %.2f %.2f   ranges read from chip: +-%d g, +-%d dps   raw temp=%d"
                % (gx, gy, gz, 2 << afs, 250 << gfs, raw[3]))


def _ak8963(report, i2c):
    wia = i2c.readfrom_mem(AK8963_ADDR, AK8963_REG_WIA, 1)[0]
    if wia == AK8963_WIA:
        report.add(PASS, "Magnetometer @0x0C", "AK8963 identified (WIA=0x48); no data read")
    else:
        report.add(WARN, "Magnetometer @0x0C", "device at 0x0C, WIA=0x%02X is not the AK8963 value" % wia)


# ---------------------------------------------------------------------------
# BMP280 (GY-91 on-board and/or standalone)
# ---------------------------------------------------------------------------
def bmp280_compensate(adc_t, adc_p, c):
    """Bosch BMP280 floating-point compensation [ASSUMPTION: recalled from the datasheet].
    c = (T1, T2, T3, P1, ... P9). Returns (temp_c, pressure_pa or None)."""
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


def parse_bmp280_calib(b):
    c = [le16(b, 0), s16(le16(b, 2)), s16(le16(b, 4)), le16(b, 6)]
    c += [s16(le16(b, i)) for i in range(8, 24, 2)]
    return tuple(c)


def test_bmp280s(report, i2c, addrs):
    present = [a for a in BMP_ADDRS if a in addrs]
    found = []
    for a in present:
        if guarded(report, "BMP280 @0x%02X" % a, _bmp_one, i2c, a):
            found.append(a)
    if not present:
        report.add(FAIL, "BMP280", "no device at 0x76/0x77")
    _duplicate_check(report, found)


def _bmp_one(report, i2c, a):
    name = "BMP280 @0x%02X" % a
    cid = i2c.readfrom_mem(a, BMP_REG_ID, 1)[0]
    chip = BMP_CHIP_IDS.get(cid)
    if chip is None:
        report.add(WARN, name, "chip ID 0x%02X is not a known Bosch value; not measuring" % cid)
        return False
    if chip != "BMP280":
        report.add(WARN, name, "chip ID 0x%02X = %s, not BMP280; not measuring" % (cid, chip))
        return False
    calib = parse_bmp280_calib(i2c.readfrom_mem(a, BMP_REG_CALIB, 24))
    i2c.writeto_mem(a, BMP_REG_CTRL_MEAS, bytes([BMP_CTRL_FORCED_X1]))  # documented write
    for _ in range(20):  # up to ~100 ms
        sleep_ms(5)
        if not i2c.readfrom_mem(a, BMP_REG_STATUS, 1)[0] & 0x08:
            break
    else:
        report.add(FAIL, name, "BMP280 identified but the measurement never finished")
        return True
    d = i2c.readfrom_mem(a, BMP_REG_DATA, 6)
    adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
    if adc_p == BMP_ADC_SKIPPED or adc_t == BMP_ADC_SKIPPED:
        report.add(FAIL, name, "BMP280 identified but returned the 'no measurement' value 0x80000")
        return True
    temp, pa = bmp280_compensate(adc_t, adc_p, calib)
    if pa is None:
        report.add(FAIL, name, "calibration data invalid (P1 = 0)")
        return True
    ok = BMP_PRESSURE_RANGE_PA[0] <= pa <= BMP_PRESSURE_RANGE_PA[1] and BMP_TEMP_RANGE_C[0] <= temp <= BMP_TEMP_RANGE_C[1]
    report.add(PASS if ok else FAIL, name, "BMP280 (chip ID 0x58): %.1f Pa, %.2f C%s" %
               (pa, temp, "" if ok else "  OUTSIDE the sensor's stated range"))
    return True


def _duplicate_check(report, found):
    n = len(found)
    if n >= EXPECTED_BMP280_COUNT:
        report.add(INFO, "BMP280 mapping", "%d BMP280s at %s. Software cannot tell which is the GY-91's and "
                                          "which is the standalone; disconnect one to map them" % (n, hexlist(found)))
        report.note("Each address answered as ONE device. If a third device shared one of these addresses,")
        report.note("this script could not detect it.")
        return
    report.add(WARN, "BMP280 duplicates", "expected %d BMP280s (GY-91 + standalone), found %d at %s. "
               "Possible shared address: this diagnostic CANNOT tell two devices at one address apart"
               % (EXPECTED_BMP280_COUNT, n, hexlist(found)))
    report.note("Two devices at the SAME I2C address cannot be addressed independently on one bus: both")
    report.note("answer together and the data can be silently corrupted. A scan cannot show this, and the")
    report.note("reading above (if any) may come from either module or a mix of both.")
    report.note("Possible causes: both BMP280s strapped to the same address, or one not powered/connected.")
    report.note("Recommendation: test each BMP280 alone on the bus, or change one's SDO/address strap.")


# ---------------------------------------------------------------------------
# INA219 - logic interface only, READ-ONLY
# ---------------------------------------------------------------------------
def test_ina219(report, i2c, addrs):
    present = [a for a in INA_ADDRS if a in addrs]
    if not present:
        report.add(FAIL, "INA219", "no device at 0x40-0x4F")
        return
    for a in present:
        guarded(report, "INA219 @0x%02X" % a, _ina_one, i2c, a)


def _ina_one(report, i2c, a):
    name = "INA219 @0x%02X" % a
    cfg = be16(i2c.readfrom_mem(a, INA_REG_CONFIG, 2), 0)
    shunt = s16(be16(i2c.readfrom_mem(a, INA_REG_SHUNT, 2), 0))
    bus = be16(i2c.readfrom_mem(a, INA_REG_BUS, 2), 0)
    detail = "config=0x%04X shunt_raw=%d (%.2f mV) bus=%.3f V CNVR=%d OVF=%d" % (
        cfg, shunt, shunt * 0.01, (bus >> 3) * 0.004, (bus >> 1) & 1, bus & 1)
    if cfg == INA_CONFIG_DEFAULT:
        report.add(PASS, name, "responds; config register holds the INA219 power-on value. " + detail)
    else:
        report.add(WARN, name, "responds, but config 0x%04X is not the INA219 power-on value 0x399F "
                               "(reconfigured, or another kind of device). %s" % (cfg, detail))
    report.note("Logic-interface check only. With nothing on VIN+/VIN- the voltage readings are")
    report.note("meaningless (floating inputs). Current/power need a calibration value: not done here.")


# ---------------------------------------------------------------------------
# SD card - disabled until supply/voltage compatibility is confirmed. No writes.
# ---------------------------------------------------------------------------
def test_sd(report):
    if not SD_SUPPLY_CONFIRMED:
        report.add(SKIP, "SD card", "disabled: set SD_SUPPLY_CONFIRMED = True only after confirming the SD "
                                    "module's supply and 3.3 V logic compatibility")
        return
    if not hasattr(machine, "SDCard"):
        report.add(FAIL, "SD card", "this MicroPython build has no machine.SDCard; no SD driver exists in the "
                                    "repository (not installed, by request)")
        return
    sd = machine.SDCard(slot=SD_SLOT, sck=machine.Pin(SD_SCK), miso=machine.Pin(SD_MISO),
                        mosi=machine.Pin(SD_MOSI), cs=machine.Pin(SD_CS))
    mounted = False
    try:
        os.mount(sd, SD_MOUNT_POINT)
        mounted = True
        names = os.listdir(SD_MOUNT_POINT)  # read-only
        report.add(PASS, "SD card", "mounted at %s (SCK=%d MISO=%d MOSI=%d CS=%d); %d entr%s in root: %s" % (
            SD_MOUNT_POINT, SD_SCK, SD_MISO, SD_MOSI, SD_CS, len(names), "y" if len(names) == 1 else "ies",
            ", ".join(names[:10]) or "(empty)"))
    except Exception as e:
        report.add(FAIL, "SD card", "mount/list failed: %r (card inserted? FAT formatted? wiring/supply?)" % (e,))
    finally:
        if mounted:
            try:
                os.umount(SD_MOUNT_POINT)
            except Exception:
                pass
        try:
            sd.deinit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
def main(out=print):
    report = Report(out)
    out("== CanSat ESP32 hardware bring-up diagnostic (bench check; NOT flight software) ==")
    out("Pins are USER-REPORTED and UNVERIFIED. Register maps are [ASSUMPTION] (recalled datasheets).")
    out("Not tested: HC-12 (unavailable), servos, buzzers, batteries, deployment hardware.")
    if machine is None:
        report.add(FAIL, "Platform", "no `machine` module: run this on the ESP32 under MicroPython")
        return report
    result = guarded(report, "I2C", test_i2c_scan)
    i2c, addrs = result if result else (None, [])
    if i2c is None or not addrs:
        for n in ("IMU", "BMP280", "INA219"):
            report.add(SKIP, n, "I2C bus unavailable")
    else:
        guarded(report, "IMU", test_imu, i2c, addrs)
        guarded(report, "BMP280", test_bmp280s, i2c, addrs)
        guarded(report, "INA219", test_ina219, i2c, addrs)
        known = set(MPU_ADDRS) | set(BMP_ADDRS) | set(INA_ADDRS) | {AK8963_ADDR}
        other = [a for a in addrs if a not in known]
        if other:
            report.add(INFO, "Other I2C devices", "not identified by this script: " + hexlist(other))
    guarded(report, "SD card", test_sd)
    c = report.counts()
    out("== SUMMARY: PASS=%d FAIL=%d WARN=%d SKIP=%d INFO=%d  (bench observation, not flight validation) =="
        % (c[PASS], c[FAIL], c[WARN], c[SKIP], c[INFO]))
    return report


if __name__ == "__main__":
    main()
