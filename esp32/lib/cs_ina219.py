# cs_ina219.py - TI INA219 driver, READ-ONLY.
#
# Never writes to the chip (no configuration, no calibration register).
# Current is computed from the shunt-voltage register directly:
#     I = V_shunt / R_shunt          (shunt LSB 10 uV regardless of PGA [ASSUMPTION])
# and ONLY when the configuration declares the shunt circuit connected. Bus
# voltage is reported ONLY when the monitored rail is declared connected.
# Otherwise both are marked invalid: floating inputs read meaningless values.
# Register map [ASSUMPTION], recalled from the TI INA219 datasheet.
#
# The INA219 has no identity register. "Identified" here means: something
# ACKs at the configured address and its config register holds the INA219
# power-on value 0x399F. A different value is reported, not trusted blindly.
import cs_proto as P

REG_CONFIG = 0x00
REG_SHUNT = 0x01   # signed, LSB 10 uV
REG_BUS = 0x02     # bits 15..3 value (LSB 4 mV), bit 1 CNVR, bit 0 OVF
CONFIG_POWER_ON = 0x399F
PGA_RANGE_MV = (40.0, 80.0, 160.0, 320.0)   # config bits 12..11


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def be16(b):
    return (b[0] << 8) | b[1]


class PowerReading:
    def __init__(self, t_ms=0, status=P.ST_NOT_PRESENT, error=""):
        self.t_ms = t_ms
        self.bus_v = 0.0
        self.bus_valid = False
        self.shunt_mv = 0.0
        self.current_ma = 0.0
        self.current_valid = False
        self.power_mw = None
        self.overflow = False
        self.raw_bus_v = None      # always the decoded register, for diagnosis only
        self.raw_shunt_mv = None
        self.valid = False         # FSW PowerSample.valid: bus AND current valid
        self.comm_ok = False
        self.data_ready = False
        self.status = status
        self.error = error


class INA219:
    kind = "power"

    def __init__(self, i2c, addr, shunt_ohms, bus_connected=False, shunt_connected=False):
        self.i2c = i2c
        self.addr = addr
        self.shunt_ohms = shunt_ohms
        self.bus_connected = bus_connected is True
        self.shunt_connected = shunt_connected is True
        self.config = None
        self.config_is_default = None
        self.status = P.ST_NOT_PRESENT
        self.error = ""

    def name(self):
        return "INA219@0x%02X" % self.addr

    def begin(self):
        self.config = be16(self.i2c.readfrom_mem(self.addr, REG_CONFIG, 2))
        self.config_is_default = self.config == CONFIG_POWER_ON
        self.error = "" if self.config_is_default else (
            "config 0x%04X is not the INA219 power-on value 0x399F (reconfigured, or not an INA219)" % self.config)
        if self.shunt_connected and not (self.shunt_ohms and self.shunt_ohms > 0):
            self.status = P.ST_INIT_FAILED
            self.error = "shunt declared connected but INA219_SHUNT_OHMS is not a positive number"
            return False
        self.status = P.ST_NOT_READY
        return True

    def gated(self):
        return not (self.bus_connected or self.shunt_connected)

    def failed(self, t_ms, status, error):
        return PowerReading(t_ms, status, error)

    def read(self, t_ms):
        shunt = s16(be16(self.i2c.readfrom_mem(self.addr, REG_SHUNT, 2)))
        bus = be16(self.i2c.readfrom_mem(self.addr, REG_BUS, 2))
        r = PowerReading(t_ms, P.ST_OK)
        r.comm_ok = True
        r.data_ready = bool(bus & 0x02)  # CNVR; stays set in continuous mode [ASSUMPTION]: not proof of freshness
        r.overflow = bool(bus & 0x01)
        r.raw_bus_v = (bus >> 3) * 0.004
        r.raw_shunt_mv = shunt * 0.01
        if self.gated():
            r.status = P.ST_DISABLED
            r.error = "monitored circuit not declared connected (INA219_BUS_CONNECTED/INA219_SHUNT_CONNECTED)"
            return r
        problems = []
        if self.bus_connected:
            if r.overflow:
                problems.append("OVF flag set")
            else:
                r.bus_v, r.bus_valid = r.raw_bus_v, True
        if self.shunt_connected:
            pga = PGA_RANGE_MV[(self.config >> 11) & 0x03] if self.config is not None else 40.0
            if abs(r.raw_shunt_mv) >= pga:
                problems.append("shunt %.2f mV at/over the PGA range +-%.0f mV" % (r.raw_shunt_mv, pga))
            else:
                r.shunt_mv = r.raw_shunt_mv
                r.current_ma = r.shunt_mv / self.shunt_ohms
                r.current_valid = True
        if r.bus_valid and r.current_valid:
            r.power_mw = r.bus_v * r.current_ma
        r.valid = r.bus_valid and r.current_valid
        if problems:
            r.status, r.error = P.ST_IMPLAUSIBLE, "; ".join(problems)
        return r
