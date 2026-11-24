# scenario.py - a scripted, fully SYNTHETIC flight scenario. [SIMULATED]
# (port of firmware/sim/Scenario.h). Every number is SYNTHETIC: chosen only to
# exercise software paths, never a flight threshold, timing or measurement.
from cansat.core.num import f32
from cansat.mock.sensors import SensorNoise

STORE_FAULT_CORRUPT_RECORD = 1
STORE_FAULT_ERASE_RECORD = 2


def store_fault_name(k):
    return "corrupt_record" if k == STORE_FAULT_CORRUPT_RECORD else "erase_record"


class Segment:
    def __init__(self, label, duration_ms=0, mounted=False, set_vz=False, vz_mps=0.0, az_mps2=0.0,
                 accel_g=(0.0, 0.0, 1.0), gyro_dps=(0.0, 0.0, 0.0), end_at_ground=False):
        self.label = label
        self.duration_ms = duration_ms   # ignored when end_at_ground is True
        self.end_at_ground = end_at_ground
        self.set_vz = set_vz
        self.vz_mps = f32(vz_mps)
        self.az_mps2 = f32(az_mps2)
        self.accel_g = [f32(a) for a in accel_g]
        self.gyro_dps = [f32(g) for g in gyro_dps]
        self.mounted = mounted


class Marker:
    def __init__(self, t_ms, text):
        self.t_ms = t_ms
        self.text = text


class StoreFaultAtReset:
    def __init__(self, reset_index, kind):
        self.reset_index = reset_index  # 0 = first entry of resets_at_ms
        self.kind = kind


class Scenario:
    def __init__(self, name="", description=""):
        self.name = name
        self.description = description
        self.seed = 1
        self.tick_ms = 0
        self.reboot_ms = 0
        self.tail_ms = 0
        self.ground_pressure_pa = 0.0
        self.temp_c = 0.0
        self.bus_v = 0.0
        self.current_ma = 0.0
        self.noise = SensorNoise()
        self.switch_closed_level_high = [False, False]
        self.segments = []
        self.faults = []
        self.resets_at_ms = []
        self.store_faults = []  # only honoured by the flight-software hook
        self.markers = []
