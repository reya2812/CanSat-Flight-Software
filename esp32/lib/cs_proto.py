# cs_proto.py - CanSat ESP-NOW telemetry protocol v1: encode, decode, validate.
#
# Portable (MicroPython + CPython): uses only `struct` with explicit
# little-endian formats, so the byte layout is deterministic on both.
# Full specification: docs/10_esp32_espnow_bringup.md section 4.
# Status: [PROPOSED] schema v1 (OD-079). Supersedes nothing in docs/06 until approved.
#
# Frame = header | body | crc16
#   header  "<2sBBH"  magic b"CS", version, type, boot_id
#   body    per type (fixed length, checked exactly)
#   crc16   "<H"      CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over header+body
#
# Missing data: the field is sent as 0 and its bit in `valid` is clear.
# Receivers MUST check `valid` (and per-sensor status) before using a value.
import struct

MAGIC = b"CS"
VERSION = 1
TYPE_TELEMETRY = 1
TYPE_ACK = 2

ESPNOW_MAX_PAYLOAD = 250  # ESP-NOW v1 payload limit (MicroPython espnow.MAX_DATA_LEN)

_HDR = "<2sBBH"
_TLM = "<IIBBHHI5BIhIhi3h3hhHhiIHHb"
_ACK = "<IIIIHb"
_CRC = "<H"
HDR_LEN = struct.calcsize(_HDR)
TLM_LEN = HDR_LEN + struct.calcsize(_TLM) + 2
ACK_LEN = HDR_LEN + struct.calcsize(_ACK) + 2

NO_SEQ = 0xFFFFFFFF   # "nothing acknowledged yet"
RSSI_UNKNOWN = -128

# ---- flight states: 0 means the flight software is NOT running (bring-up mode);
# 1..8 are the FlightState codes of micropython/cansat/core/types.py.
STATE_NO_FSW = 0
STATE_NAMES = {0: "NO_FSW(bring-up)", 1: "POWER_ON_SELF_CHECK", 2: "READY_ON_DRONE", 3: "ASCENT",
               4: "RELEASE_DETECTED", 5: "PARACHUTE_DEPLOY", 6: "PANEL_DEPLOY", 7: "DESCENT", 8: "LANDED"}
MAX_STATE = 8

# ---- per-sensor status codes (one byte each: baro1, baro2, imu, power, sd) ----
ST_NOT_PRESENT = 0   # nothing answered at the expected address(es)
ST_INIT_FAILED = 1   # answered but initialisation failed (retried periodically)
ST_OK = 2            # last read succeeded and passed plausibility checks
ST_READ_ERROR = 3    # bus error / exception on the last read
ST_NOT_READY = 4     # no completed conversion yet
ST_IMPLAUSIBLE = 5   # read succeeded but the value is outside physical limits
ST_UNKNOWN_CHIP = 6  # identity register holds an unknown value; data not trusted
ST_DISABLED = 7      # deliberately not measured (gated by configuration)
ST_NAMES = ("NOT_PRESENT", "INIT_FAILED", "OK", "READ_ERROR", "NOT_READY", "IMPLAUSIBLE",
            "UNKNOWN_CHIP", "DISABLED")
SENSOR_SLOTS = ("baro1", "baro2", "imu", "power", "sd")

# ---- validity bits ----
V_BARO1 = 1 << 0      # p1, t1
V_BARO2 = 1 << 1      # p2, t2
V_ALT = 1 << 2        # alt (from baro1 and the reference pressure)
V_ACCEL = 1 << 3
V_GYRO = 1 << 4
V_IMU_TEMP = 1 << 5
V_BUS_V = 1 << 6      # INA219 bus voltage (only if the monitored circuit is declared connected)
V_CURRENT = 1 << 7    # INA219 shunt voltage + current (only if the shunt circuit is declared connected)
V_ACK_RSSI = 1 << 8
V_ALL = (1 << 9) - 1

# ---- status flags ----
F_FSW_RUNNING = 1 << 0       # state and fault come from the flight software
F_FSW_REFUSED = 1 << 1       # FSW was requested but its boot checks refused (see serial console)
F_BARO_DUP_SUSPECT = 1 << 2  # fewer barometers answered than expected: possible shared I2C address
F_IMU_SATURATED = 1 << 3     # an accelerometer axis is at full scale
F_ALT_REF_AUTO = 1 << 4      # altitude reference = first valid baro1 reading after boot
F_POWER_GATED = 1 << 5       # INA219 readings withheld: monitored circuit not declared connected
F_LINK_RECOVERING = 1 << 6   # flight side re-initialised the radio after a link-down
FLAG_NAMES = ("FSW_RUNNING", "FSW_REFUSED", "BARO_DUP_SUSPECT", "IMU_SATURATED", "ALT_REF_AUTO",
              "POWER_GATED", "LINK_RECOVERING")

# ---- flight-side link state ----
LINK_UNKNOWN = 0   # no acknowledgement received yet this boot
LINK_UP = 1
LINK_DEGRADED = 2  # recent acknowledgements missing
LINK_DOWN = 3      # no acknowledgement for LINK_DOWN_MS
LINK_NAMES = ("UNKNOWN", "UP", "DEGRADED", "DOWN")

# ---- physical plausibility limits used by the receiver ([ASSUMPTION] datasheet ranges, recalled) ----
BARO_P_MIN_PA, BARO_P_MAX_PA = 30000.0, 110000.0   # BMP280 stated operating range
BARO_T_MIN_C, BARO_T_MAX_C = -40.0, 85.0
IMU_T_MIN_C, IMU_T_MAX_C = -40.0, 85.0

# ---- rejection reasons (decode) ----
R_SHORT = "short"
R_MAGIC = "magic"
R_VERSION = "version"
R_TYPE = "type"
R_LENGTH = "length"
R_CRC = "crc"
R_FIELD = "field"
REJECT_REASONS = (R_SHORT, R_MAGIC, R_VERSION, R_TYPE, R_LENGTH, R_CRC, R_FIELD)


class ProtocolError(ValueError):
    def __init__(self, reason, detail=""):
        ValueError.__init__(self, reason + (": " + detail if detail else ""))
        self.reason = reason


def crc16_ccitt(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE. Check value: b'123456789' -> 0x29B1."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def is_finite(x):
    try:
        return (x - x) == 0.0
    except TypeError:
        return False


def _scaled(value, scale, lo, hi):
    """(int, ok). ok is False for None, non-finite or out-of-range values; the field is then 0."""
    if value is None or not is_finite(value):
        return 0, False
    n = int(round(value * scale))
    if n < lo or n > hi:
        return 0, False
    return n, True


I16 = (-32768, 32767)
I32 = (-2147483648, 2147483647)
U16 = (0, 65535)
U32 = (0, 0xFFFFFFFF)


class Telemetry:
    """One telemetry sample in physical units. None = not available."""

    def __init__(self):
        self.boot_id = 0
        self.seq = 0
        self.uptime_ms = 0
        self.state = STATE_NO_FSW
        self.link = LINK_UNKNOWN
        self.valid = 0
        self.flags = 0
        self.fault = 0
        self.status = [ST_NOT_PRESENT] * 5    # baro1, baro2, imu, power, sd
        self.p1_pa = None
        self.t1_c = None
        self.p2_pa = None
        self.t2_c = None
        self.alt_m = None
        self.accel_g = None    # (ax, ay, az)
        self.gyro_dps = None   # (gx, gy, gz)
        self.imu_temp_c = None
        self.bus_v = None
        self.shunt_mv = None
        self.current_ma = None
        self.acked_seq = NO_SEQ
        self.tx_fail = 0
        self.ack_miss = 0
        self.ack_rssi = None
        self.implausible = []  # filled by decode_telemetry(): names of fields dropped as implausible

    def has(self, bit):
        return (self.valid & bit) != 0


def encode_telemetry(t):
    """Telemetry -> bytes. A value that is missing or not representable is sent
    as 0 with its validity bit cleared (never clamped to a wrong number)."""
    valid = 0
    p1, ok1 = _scaled(t.p1_pa, 10, *U32)
    t1, ok1t = _scaled(t.t1_c, 100, *I16)
    if (t.valid & V_BARO1) and ok1 and ok1t:
        valid |= V_BARO1
    else:
        p1 = t1 = 0
    p2, ok2 = _scaled(t.p2_pa, 10, *U32)
    t2, ok2t = _scaled(t.t2_c, 100, *I16)
    if (t.valid & V_BARO2) and ok2 and ok2t:
        valid |= V_BARO2
    else:
        p2 = t2 = 0
    alt, oka = _scaled(t.alt_m, 100, *I32)
    if (t.valid & V_ALT) and oka:
        valid |= V_ALT
    else:
        alt = 0
    acc = [0, 0, 0]
    if (t.valid & V_ACCEL) and t.accel_g is not None:
        r = [_scaled(v, 1000, *I16) for v in t.accel_g]
        if all(ok for _, ok in r):
            acc = [n for n, _ in r]
            valid |= V_ACCEL
    gyr = [0, 0, 0]
    if (t.valid & V_GYRO) and t.gyro_dps is not None:
        r = [_scaled(v, 10, *I16) for v in t.gyro_dps]
        if all(ok for _, ok in r):
            gyr = [n for n, _ in r]
            valid |= V_GYRO
    it, okit = _scaled(t.imu_temp_c, 100, *I16)
    if (t.valid & V_IMU_TEMP) and okit:
        valid |= V_IMU_TEMP
    else:
        it = 0
    bus, okb = _scaled(t.bus_v, 1000, *U16)
    if (t.valid & V_BUS_V) and okb:
        valid |= V_BUS_V
    else:
        bus = 0
    sh, oks = _scaled(t.shunt_mv, 100, *I16)       # 10 uV units = INA219 shunt LSB
    cur, okc = _scaled(t.current_ma, 1000, *I32)   # uA
    if (t.valid & V_CURRENT) and oks and okc:
        valid |= V_CURRENT
    else:
        sh = cur = 0
    rssi = RSSI_UNKNOWN
    if (t.valid & V_ACK_RSSI) and t.ack_rssi is not None and -127 <= int(t.ack_rssi) <= 127:
        rssi = int(t.ack_rssi)
        valid |= V_ACK_RSSI
    st = [int(s) & 0xFF for s in t.status]
    if len(st) != 5:
        raise ValueError("status must have 5 entries (baro1, baro2, imu, power, sd)")
    hdr = struct.pack(_HDR, MAGIC, VERSION, TYPE_TELEMETRY, t.boot_id & 0xFFFF)
    body = struct.pack(_TLM, t.seq & 0xFFFFFFFF, t.uptime_ms & 0xFFFFFFFF, t.state & 0xFF, t.link & 0xFF,
                       valid, t.flags & 0xFFFF, t.fault & 0xFFFFFFFF, st[0], st[1], st[2], st[3], st[4],
                       p1, t1, p2, t2, alt, acc[0], acc[1], acc[2], gyr[0], gyr[1], gyr[2], it, bus, sh, cur,
                       t.acked_seq & 0xFFFFFFFF, min(t.tx_fail, 0xFFFF), min(t.ack_miss, 0xFFFF), rssi)
    frame = hdr + body
    return frame + struct.pack(_CRC, crc16_ccitt(frame))


class Ack:
    def __init__(self, boot_id=0, ack_seq=0, gs_uptime_ms=0, rx_ok=0, lost=0, rejected=0, rssi=None):
        self.boot_id = boot_id
        self.ack_seq = ack_seq
        self.gs_uptime_ms = gs_uptime_ms
        self.rx_ok = rx_ok
        self.lost = lost
        self.rejected = rejected
        self.rssi = rssi  # RSSI of the acknowledged telemetry frame as seen by the ground, or None


def encode_ack(a):
    rssi = RSSI_UNKNOWN if a.rssi is None or not (-127 <= int(a.rssi) <= 127) else int(a.rssi)
    frame = struct.pack(_HDR, MAGIC, VERSION, TYPE_ACK, a.boot_id & 0xFFFF) + struct.pack(
        _ACK, a.ack_seq & 0xFFFFFFFF, a.gs_uptime_ms & 0xFFFFFFFF, a.rx_ok & 0xFFFFFFFF,
        a.lost & 0xFFFFFFFF, min(a.rejected, 0xFFFF), rssi)
    return frame + struct.pack(_CRC, crc16_ccitt(frame))


def _check_frame(data):
    """Structural checks shared by every type. Returns (type, boot_id)."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ProtocolError(R_SHORT, "not bytes")
    data = bytes(data)
    if len(data) < HDR_LEN + 2:
        raise ProtocolError(R_SHORT, "%d bytes" % len(data))
    magic, ver, typ, boot_id = struct.unpack(_HDR, data[:HDR_LEN])
    if magic != MAGIC:
        raise ProtocolError(R_MAGIC)
    if ver != VERSION:
        raise ProtocolError(R_VERSION, "got %d, expected %d" % (ver, VERSION))
    expected = {TYPE_TELEMETRY: TLM_LEN, TYPE_ACK: ACK_LEN}.get(typ)
    if expected is None:
        raise ProtocolError(R_TYPE, "type %d" % typ)
    if len(data) != expected:
        raise ProtocolError(R_LENGTH, "%d bytes, expected %d" % (len(data), expected))
    (crc,) = struct.unpack(_CRC, data[-2:])
    if crc != crc16_ccitt(data[:-2]):
        raise ProtocolError(R_CRC)
    return typ, boot_id


def peek_type(data):
    """Type of a structurally valid frame; raises ProtocolError otherwise."""
    return _check_frame(data)[0]


def decode_telemetry(data):
    """bytes -> Telemetry. Raises ProtocolError for malformed frames.

    Structural problems (length, magic, version, CRC, unknown state or status
    code, validity bits outside the defined set) reject the whole frame.
    A physically implausible value whose validity bit is set does NOT reject
    the frame: its bit is cleared and its name is listed in t.implausible, so
    one bad sensor never hides the others.
    """
    typ, boot_id = _check_frame(data)
    if typ != TYPE_TELEMETRY:
        raise ProtocolError(R_TYPE, "not telemetry")
    f = struct.unpack(_TLM, bytes(data)[HDR_LEN:-2])
    t = Telemetry()
    t.boot_id = boot_id
    (t.seq, t.uptime_ms, t.state, t.link, t.valid, t.flags, t.fault) = f[0:7]
    t.status = list(f[7:12])
    p1, t1, p2, t2, alt = f[12:17]
    acc = f[17:20]
    gyr = f[20:23]
    it, bus, sh, cur = f[23:27]
    t.acked_seq, t.tx_fail, t.ack_miss, rssi = f[27:31]
    if t.state > MAX_STATE:
        raise ProtocolError(R_FIELD, "state code %d" % t.state)
    if t.link >= len(LINK_NAMES):
        raise ProtocolError(R_FIELD, "link code %d" % t.link)
    for s in t.status:
        if s >= len(ST_NAMES):
            raise ProtocolError(R_FIELD, "sensor status code %d" % s)
    if t.valid & ~V_ALL:
        raise ProtocolError(R_FIELD, "undefined validity bits 0x%04X" % t.valid)
    t.implausible = []
    v = t.valid
    if v & V_BARO1:
        t.p1_pa, t.t1_c = p1 / 10.0, t1 / 100.0
    if v & V_BARO2:
        t.p2_pa, t.t2_c = p2 / 10.0, t2 / 100.0
    if v & V_ALT:
        t.alt_m = alt / 100.0
    if v & V_ACCEL:
        t.accel_g = tuple(a / 1000.0 for a in acc)
    if v & V_GYRO:
        t.gyro_dps = tuple(g / 10.0 for g in gyr)
    if v & V_IMU_TEMP:
        t.imu_temp_c = it / 100.0
    if v & V_BUS_V:
        t.bus_v = bus / 1000.0
    if v & V_CURRENT:
        t.shunt_mv, t.current_ma = sh / 100.0, cur / 1000.0
    if v & V_ACK_RSSI:
        t.ack_rssi = rssi
    _plausibility(t)
    return t


def _plausibility(t):
    def bad(name, bit, *attrs):
        t.implausible.append(name)
        t.valid &= ~bit
        for a in attrs:
            setattr(t, a, None)

    for n, bit, pa, tc in (("baro1", V_BARO1, "p1_pa", "t1_c"), ("baro2", V_BARO2, "p2_pa", "t2_c")):
        if t.valid & bit:
            p, c = getattr(t, pa), getattr(t, tc)
            if not (BARO_P_MIN_PA <= p <= BARO_P_MAX_PA and BARO_T_MIN_C <= c <= BARO_T_MAX_C):
                bad(n, bit, pa, tc)
    if (t.valid & V_IMU_TEMP) and not (IMU_T_MIN_C <= t.imu_temp_c <= IMU_T_MAX_C):
        bad("imu_temp", V_IMU_TEMP, "imu_temp_c")
    if (t.valid & V_ACK_RSSI) and not (-127 <= t.ack_rssi <= 0):
        bad("ack_rssi", V_ACK_RSSI, "ack_rssi")


def decode_ack(data):
    typ, boot_id = _check_frame(data)
    if typ != TYPE_ACK:
        raise ProtocolError(R_TYPE, "not an ack")
    ack_seq, gs_up, rx_ok, lost, rejected, rssi = struct.unpack(_ACK, bytes(data)[HDR_LEN:-2])
    return Ack(boot_id, ack_seq, gs_up, rx_ok, lost, rejected, None if rssi == RSSI_UNKNOWN else rssi)


def state_name(code):
    return STATE_NAMES.get(code, "INVALID(%d)" % code)


def flag_names(flags):
    return [n for i, n in enumerate(FLAG_NAMES) if flags & (1 << i)]
