# ina219_test.py - bench tool: find the INA219 current/voltage monitor and print
# live bus voltage, shunt voltage and current. INA219 only.
#
#     python3 -m mpremote connect <FLIGHT_PORT> run esp32/apps/ina219_test.py     (Ctrl-C to stop)
#
# Standalone: imports nothing from the project, so it works with `mpremote run`.
# I2C on SDA=GPIO21, SCL=GPIO22, 100 kHz (esp32/config/flight_config.py).
#
# READ-ONLY: never writes to the chip (no configuration, no calibration
# register). Current is computed from the shunt-voltage register:
#     I = V_shunt / R_shunt   (shunt LSB 10 uV, bus LSB 4 mV  [ASSUMPTION], recalled)
# The readings only mean something when VIN+/VIN- are wired into a circuit:
# with nothing connected the inputs float and show meaningless values.
import time

SDA = 21
SCL = 22
FREQ = 100000
ADDRESSES = (0x40, 0x41, 0x44, 0x45)
SHUNT_OHMS = 0.1          # [docs/03] confirm the "R100" marking on the board
CONFIG_POWER_ON = 0x399F
PGA_MV = (40.0, 80.0, 160.0, 320.0)
PERIOD_MS = 250
DURATION_S = 30


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def reg(i2c, addr, r):
    b = i2c.readfrom_mem(addr, r, 2)
    return (b[0] << 8) | b[1]


def main(machine=None, out=print):
    if machine is None:
        try:
            import machine
        except ImportError:
            out("run this on the ESP32 (no machine module here)")
            return None
    i2c = machine.I2C(0, scl=machine.Pin(SCL), sda=machine.Pin(SDA), freq=FREQ)
    out("== INA219 test (read-only): %r ==" % (i2c,))
    found = i2c.scan()
    out("I2C scan: %s" % (" ".join("0x%02X" % a for a in found) or "nothing answered"))
    addr = None
    for a in ADDRESSES:
        if a in found:
            addr = a
            break
    if addr is None:
        out("RESULT: no INA219 at 0x40/0x41/0x44/0x45. Nothing more to test.")
        return None
    cfg = reg(i2c, addr, 0x00)
    pga = PGA_MV[(cfg >> 11) & 3]
    out("device at 0x%02X, config = 0x%04X %s" % (addr, cfg, "(INA219 power-on default)" if cfg == CONFIG_POWER_ON
                                                  else "(NOT the INA219 default 0x399F: reconfigured or not an INA219)"))
    out("shunt range +/-%.0f mV -> max +/-%.0f mA with %.2f ohm shunt" % (pga, pga / SHUNT_OHMS, SHUNT_OHMS))
    out("  bus V  | shunt mV | current mA | power mW | flags")
    t0 = time.ticks_ms()
    n = errors = 0
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < DURATION_S * 1000:
            try:
                shunt_mv = s16(reg(i2c, addr, 0x01)) * 0.01
                bus = reg(i2c, addr, 0x02)
            except OSError as e:
                errors += 1
                out("read error: %r" % (e,))
                time.sleep_ms(PERIOD_MS)
                continue
            bus_v = (bus >> 3) * 0.004
            ma = shunt_mv / SHUNT_OHMS
            flags = []
            if bus & 1:
                flags.append("OVERFLOW")
            if abs(shunt_mv) >= pga:
                flags.append("shunt at range limit")
            out("%7.3f  | %8.2f | %10.1f | %8.1f | %s" % (bus_v, shunt_mv, ma, bus_v * ma, " ".join(flags) or "-"))
            n += 1
            time.sleep_ms(PERIOD_MS)
    except KeyboardInterrupt:
        pass
    out("stopped: %d readings, %d read errors" % (n, errors))
    out("Bus V = voltage at VIN- (to GND). Current = flow from VIN+ to VIN- through the shunt.")
    out("With nothing wired to VIN+/VIN-, these values are meaningless (floating inputs).")
    return n


if __name__ == "__main__":
    main()
