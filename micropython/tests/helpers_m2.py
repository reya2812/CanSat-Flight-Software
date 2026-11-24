# helpers_m2.py - SYNTHETIC frame builders for module 2 unit tests. [SIMULATED]
from cansat.core import types as T
from cansat.core.event_detector import EventDetector
from cansat.core.flight_software import BootReport, FlightSoftware
from cansat.core.num import f32
from cansat.core.recovery_manager import RECOVERY_MAGIC, RECOVERY_VERSION, recovery_crc
from cansat.core.sensor_validator import ValidatedFrame
from cansat.mock.persistent_store import MockPersistentStore
from cansat.sim.synthetic_flight_params import synthetic_flight_params
from cansat.config import flight_params as FP

SYNTHETIC_GROUND_PA = 101325.0
SYNTHETIC_TICK_MS = 50


def frame(t, pressure=SYNTHETIC_GROUND_PA, acc=(0.01, 0.02, 1.0), sw_open=False, gyro=(0.1, 0.2, 0.3)):
    """A valid, fresh frame. Switch raw level True = open (SYNTHETIC wiring, open_is_high)."""
    f = T.SensorFrame()
    b, m, p, s = f.baro, f.imu, f.power, f.switches
    b.t_ms = m.t_ms = p.t_ms = s.t_ms = t
    b.pressure_pa, b.temp_c = f32(pressure), f32(20.0)
    m.ax_g, m.ay_g, m.az_g = (f32(a + 1e-4 * (t % 7)) for a in acc)  # varies: never "stuck"
    m.gx_dps, m.gy_dps, m.gz_dps = (f32(g) for g in gyro)
    p.bus_v, p.current_ma = f32(3.9), f32(150.0)
    for smp in (b, m, p):
        smp.valid = smp.comm_ok = smp.data_ready = True
    s.raw = [sw_open, sw_open]
    s.valid = True
    return f


def vframe(t, **kw):
    v = ValidatedFrame(t, frame(t, **kw))
    v.baro_ok = v.imu_ok = v.power_ok = v.switches_ok = True
    return v


class Sink:
    def __init__(self):
        self.events = []

    def on_event(self, e):
        self.events.append(e)

    def types(self):
        return [e.type for e in self.events]


def params(policy=FP.POLICY_STRICT_SWITCH_VETO):
    return synthetic_flight_params(policy)


def detector(policy=FP.POLICY_STRICT_SWITCH_VETO):
    s = Sink()
    return EventDetector(params(policy), s), s


def seeded_store(state, flags=0, ground=SYNTHETIC_GROUND_PA, boot_count=1):
    """A store holding a VALID record, as an earlier boot would have written it."""
    st = MockPersistentStore()
    r = T.RecoveryRecord()
    r.magic, r.version, r.boot_count = RECOVERY_MAGIC, RECOVERY_VERSION, boot_count
    r.last_state, r.one_shot_flags, r.ground_pressure_pa = state, flags, f32(ground)
    r.crc = recovery_crc(r)
    st.save(r)
    return st


def boot(store, policy=FP.POLICY_STRICT_SWITCH_VETO, now=0, report=None):
    fs = FlightSoftware(params(policy), store)
    fs.boot(report or BootReport(True, True, True), now)
    return fs


def run(fs, t0, t1, **kw):
    """Tick from t0 to t1 inclusive; return all events and requests popped."""
    events, reqs = [], []
    t = t0
    while t <= t1:
        fs.tick(frame(t, **kw), t)
        events.extend(fs.events())
        r = fs.pop_request()
        while r is not None:
            reqs.append((t, r))
            r = fs.pop_request()
        t += SYNTHETIC_TICK_MS
    return events, reqs
