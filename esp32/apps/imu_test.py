# imu_test.py - bench tool: find the IMU (MPU-6050/6500/9250 family, e.g. on
# the GY-91) and print live accel / gyro / temperature readings. IMU only.
#
#     python3 -m mpremote connect <FLIGHT_PORT> run esp32/apps/imu_test.py     (Ctrl-C to stop)
#
# Standalone: imports nothing from the project, so it works with `mpremote run`.
# I2C on SDA=GPIO21, SCL=GPIO22, 100 kHz (esp32/config/flight_config.py).
#
# The one write to the chip: PWR_MGMT_1 (0x6B), clearing only the SLEEP bit,
# because the chip powers up asleep and gives no data otherwise. It is the same
# write cs_mpu.begin() makes. Ranges, filters and clock are left as they are;
# the full-scale settings are read back and used for scaling. Register map and
# scale factors are [ASSUMPTION], recalled, not checked against the datasheet.
import time

SDA = 21
SCL = 22
FREQ = 100000
ADDRESSES = (0x68, 0x69)
WHO = {0x68: "MPU-6050", 0x70: "MPU-6500", 0x71: "MPU-9250", 0x73: "MPU-9255"}
TEMP = {0x68: (340.0, 36.53), 0x70: (333.87, 21.0), 0x71: (333.87, 21.0), 0x73: (333.87, 21.0)}
PERIOD_MS = 200
DURATION_S = 30


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def main(machine=None, out=print):
    if machine is None:
        try:
            import machine
        except ImportError:
            out("run this on the ESP32 (no machine module here)")
            return None
    i2c = machine.I2C(0, scl=machine.Pin(SCL), sda=machine.Pin(SDA), freq=FREQ)
    out("== IMU test: %r ==" % (i2c,))
    found = i2c.scan()
    out("I2C scan: %s" % (" ".join("0x%02X" % a for a in found) or "nothing answered"))
    addr = None
    for a in ADDRESSES:
        if a in found:
            addr = a
            break
    if addr is None:
        out("RESULT: no IMU at 0x68 or 0x69. Nothing more to test.")
        return None
    who = i2c.readfrom_mem(addr, 0x75, 1)[0]
    chip = WHO.get(who)
    out("IMU at 0x%02X, WHO_AM_I = 0x%02X -> %s" % (addr, who, chip or "UNKNOWN chip"))
    if chip is None:
        out("RESULT: unknown chip; not reading data from it.")
        return None
    pwr = i2c.readfrom_mem(addr, 0x6B, 1)[0]
    if pwr & 0x40:
        i2c.writeto_mem(addr, 0x6B, bytes([pwr & ~0x40 & 0xFF]))
        out("chip was asleep (PWR_MGMT_1=0x%02X): cleared the SLEEP bit" % pwr)
        time.sleep_ms(100)
    afs = (i2c.readfrom_mem(addr, 0x1C, 1)[0] >> 3) & 3
    gfs = (i2c.readfrom_mem(addr, 0x1B, 1)[0] >> 3) & 3
    acc_lsb = 16384.0 / (1 << afs)
    gyr_lsb = 131.0 / (1 << gfs)
    sens, off = TEMP[who]
    out("ranges read from chip: accel +/-%d g, gyro +/-%d dps" % (2 << afs, 250 << gfs))
    out("   ax     ay     az  (g)  |   gx      gy      gz  (dps) |  temp C  |  |a| g")
    t0 = time.ticks_ms()
    n = errors = 0
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < DURATION_S * 1000:
            try:
                b = i2c.readfrom_mem(addr, 0x3B, 14)
            except OSError as e:
                errors += 1
                out("read error: %r" % (e,))
                time.sleep_ms(PERIOD_MS)
                continue
            raw = [s16((b[i] << 8) | b[i + 1]) for i in range(0, 14, 2)]
            ax, ay, az = (raw[i] / acc_lsb for i in (0, 1, 2))
            gx, gy, gz = (raw[i] / gyr_lsb for i in (4, 5, 6))
            mag = (ax * ax + ay * ay + az * az) ** 0.5
            note = "  <- all zero: chip asleep or bus fault" if all(v == 0 for v in raw) else ""
            out("%6.2f %6.2f %6.2f      | %7.1f %7.1f %7.1f       | %6.1f   | %5.2f%s"
                % (ax, ay, az, gx, gy, gz, raw[3] / sens + off, mag, note))
            n += 1
            time.sleep_ms(PERIOD_MS)
    except KeyboardInterrupt:
        pass
    out("stopped: %d readings, %d read errors" % (n, errors))
    out("At rest |a| should be about 1.00 g and gyro near 0 (a few dps offset is normal).")
    return n


if __name__ == "__main__":
    main()
