# fakes.py - laptop test doubles for esp32/ (CPython). They prove LOGIC only,
# never anything about the real ESP32, wiring, sensors or radio.
import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ESP32 = os.path.dirname(HERE)
REPO = os.path.dirname(ESP32)
for p in (os.path.join(ESP32, "lib"), os.path.join(ESP32, "config"), os.path.join(ESP32, "tools"),
          os.path.join(REPO, "micropython")):
    if p not in sys.path:
        sys.path.insert(0, p)

FLIGHT_MAC = bytes.fromhex("240ac4000001")
GROUND_MAC = bytes.fromhex("240ac4000002")
OTHER_MAC = bytes.fromhex("240ac40000ff")


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------
class FakeI2C:
    """{addr: {reg: byte}}; devices with "_word16" hold 16-bit big-endian registers (INA219)."""

    def __init__(self, devices, fail_regs=(), scan_raises=None):
        self.devices = devices
        self.fail_regs = set(fail_regs)
        self.scan_raises = scan_raises
        self.writes = []
        self.reads = 0

    def scan(self):
        if self.scan_raises:
            raise self.scan_raises
        return sorted(self.devices)

    def _dev(self, addr, reg):
        if addr not in self.devices or (addr, reg) in self.fail_regs or (addr, None) in self.fail_regs:
            raise OSError(19)
        return self.devices[addr]

    def readfrom_mem(self, addr, reg, n):
        d = self._dev(addr, reg)
        self.reads += 1
        if d.get("_word16"):
            v = d.get(reg, 0)
            return bytes([(v >> 8) & 0xFF, v & 0xFF])[:n]
        return bytes(d.get(reg + i, 0) & 0xFF for i in range(n))

    def writeto_mem(self, addr, reg, data):
        d = self._dev(addr, reg)
        self.writes.append((addr, reg, bytes(data)))
        if d.get("_readonly"):
            return
        for i, b in enumerate(data):
            d[reg + i] = b


# Bosch BMP280 datasheet worked example [ASSUMPTION: recalled; same values as bringup tests]
EXAMPLE_CALIB = (27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)
EXAMPLE_ADC_T, EXAMPLE_ADC_P = 519888, 415148   # -> 25.08 C, ~100653.27 Pa


def bmp280_regs(chip_id=0x58, adc_t=EXAMPLE_ADC_T, adc_p=EXAMPLE_ADC_P, calib=EXAMPLE_CALIB):
    r = {0xD0: chip_id, 0xF3: 0x00}
    for i, b in enumerate(struct.pack("<HhhHhhhhhhhh", *calib)):
        r[0x88 + i] = b
    set_bmp_adc(r, adc_t, adc_p)
    return r


def set_bmp_adc(r, adc_t, adc_p):
    for reg, v in ((0xF7, adc_p), (0xFA, adc_t)):
        r[reg], r[reg + 1], r[reg + 2] = (v >> 12) & 0xFF, (v >> 4) & 0xFF, (v << 4) & 0xF0


def mpu_regs(who=0x71, accel=(0, 0, 16384), temp=0, gyro=(131, -262, 0), asleep=True, afs=0, gfs=0, drdy=1):
    r = {0x75: who, 0x6B: 0x40 if asleep else 0x00, 0x1C: afs << 3, 0x1B: gfs << 3}
    set_mpu_raw(r, accel, temp, gyro, drdy)
    return r


def set_mpu_raw(r, accel, temp, gyro, drdy=1):
    r[0x3A] = drdy
    vals = list(accel) + [temp] + list(gyro)
    for i, v in enumerate(vals):
        b = struct.pack(">h", v)
        r[0x3B + 2 * i], r[0x3C + 2 * i] = b[0], b[1]


def ina_regs(config=0x399F, shunt_raw=1234, bus_raw=None, bus_v=3.7, cnvr=1, ovf=0):
    if bus_raw is None:
        bus_raw = (int(round(bus_v / 0.004)) << 3) | (cnvr << 1) | ovf
    return {"_word16": True, "_readonly": True, 0x00: config, 0x01: shunt_raw & 0xFFFF, 0x02: bus_raw}


def full_bus():
    return {0x68: mpu_regs(), 0x76: bmp280_regs(), 0x77: bmp280_regs(), 0x40: ina_regs()}


def flight_cfg(**over):
    import flight_config
    c = types.SimpleNamespace(**{k: getattr(flight_config, k) for k in dir(flight_config) if k.isupper()})
    for k, v in over.items():
        setattr(c, k, v)
    return c


# ---------------------------------------------------------------------------
# Radio
# ---------------------------------------------------------------------------
class FakeAir:
    """Shared medium between two FakeRadio endpoints, with fault injection."""

    def __init__(self):
        self.endpoints = {}
        self.drop = lambda src, dst, data: False       # return True to drop
        self.mangle = lambda src, dst, data: data       # return modified bytes
        self.duplicate = lambda src, dst, data: False   # return True to deliver twice
        self.blackout = False
        self.log = []

    def deliver(self, src, dst, data):
        self.log.append((src, dst, data))
        if self.blackout or self.drop(src, dst, data) or dst not in self.endpoints:
            return
        data = self.mangle(src, dst, data)
        ep = self.endpoints[dst]
        ep.inbox.append((src, bytes(data)))
        if self.duplicate(src, dst, data):
            ep.inbox.append((src, bytes(data)))


class FakeRadio:
    def __init__(self, air, mac, rssi=-55):
        self.air = air
        self.mac = mac
        self.inbox = []
        self.sent = []
        self.recovers = 0
        self.send_raises = None
        self.send_returns = True
        self.recv_raises = None
        self.rssi_value = rssi
        air.endpoints[mac] = self

    def send(self, mac, data):
        if self.send_raises:
            raise self.send_raises
        self.sent.append((mac, bytes(data)))
        if self.send_returns:
            self.air.deliver(self.mac, mac, data)
        return self.send_returns

    def recv(self):
        if self.recv_raises:
            raise self.recv_raises
        return self.inbox.pop(0) if self.inbox else None

    def rssi(self, mac):
        return self.rssi_value

    def recover(self):
        self.recovers += 1


def radio_pair():
    air = FakeAir()
    return air, FakeRadio(air, FLIGHT_MAC), FakeRadio(air, GROUND_MAC)


# ---------------------------------------------------------------------------
# machine / os for SD
# ---------------------------------------------------------------------------
class FakeFS:
    """In-memory FAT-like filesystem behind os.mount; supports injected faults."""

    def __init__(self, card_present=True):
        self.card_present = card_present
        self.files = {"/sd/DCIM": b""}
        self.mounted = set()
        self.calls = []
        self.fail = {}          # op -> exception
        self.corrupt_read = False

    # os API
    def mount(self, dev, path):
        self.calls.append(("mount", path))
        if "mount" in self.fail:
            raise self.fail["mount"]
        if not self.card_present:
            raise OSError(19)
        self.mounted.add(path)

    def umount(self, path):
        self.calls.append(("umount", path))
        self.mounted.discard(path)

    def statvfs(self, path):
        return (32768, 32768, 1000, 900, 900, 0, 0, 0, 0, 255)

    def remove(self, path):
        self.calls.append(("remove", path))
        if "remove" in self.fail:
            raise self.fail["remove"]
        del self.files[path]

    def stat(self, path):
        if path not in self.files:
            raise OSError(2)
        return (0x8000, 0, 0, 0, 0, 0, len(self.files[path]), 0, 0, 0)

    # open() replacement
    def open(self, path, mode="r"):
        fs = self
        if not any(path.startswith(m + "/") for m in self.mounted):
            raise OSError(2)
        self.calls.append(("open", path, mode))

        class F:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def write(self, s):
                if "write" in fs.fail:
                    raise fs.fail["write"]
                fs.files[path] = s.encode()
                return len(s)

            def read(self):
                if "read" in fs.fail:
                    raise fs.fail["read"]
                data = fs.files[path].decode()
                return data[:-3] + "XX\n" if fs.corrupt_read else data
        if "w" not in mode and path not in self.files:
            raise OSError(2)
        return F()


def fake_machine(i2c=None, sdcard=True, sdcard_raises=None):
    m = types.ModuleType("machine")

    class Pin:
        OUT = "OUT_SHOULD_NEVER_BE_USED"

        def __init__(self, n, *a, **k):
            if a or k:
                raise AssertionError("pin mode/value configured: %r %r" % (a, k))
            self.n = n
    m.Pin = Pin
    m.I2C = lambda *a, **k: i2c
    m.freq = lambda: 240000000
    if sdcard:
        class SDCard:
            made = []

            def __init__(self, **k):
                if sdcard_raises:
                    raise sdcard_raises
                SDCard.made.append(k)
                self.deinited = False

            def deinit(self):
                self.deinited = True
        m.SDCard = SDCard
    return m


class TickClock:
    def __init__(self, t=1000):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, ms):
        self.t += ms
        return self.t
