# fault_injector.py - time-windowed fault injection for mock sensors. [SIMULATED]
# (port of lib/hal_mock/FaultInjector.h). A window is active when start <= t < end.
from cansat.core.num import f32

TARGET_BARO, TARGET_IMU, TARGET_POWER, TARGET_SWITCH1, TARGET_SWITCH2 = 0, 1, 2, 3, 4
_TARGET_NAMES = ("baro", "imu", "power", "switch1", "switch2")

(NOT_DETECTED, DROPOUT, STALE, NOISE, ZERO_READ, NAN_VALUE, OUT_OF_RANGE, STUCK_CLOSED, STUCK_OPEN,
 BOUNCE, COMM_FAILURE, NOT_READY, STUCK_OUTPUT) = range(13)
_KIND_NAMES = ("not_detected", "dropout", "stale", "noise", "zero_read", "nan", "out_of_range",
               "stuck_closed", "stuck_open", "bounce", "comm_failure", "not_ready", "stuck_output")


def target_name(t):
    return _TARGET_NAMES[t] if 0 <= t < len(_TARGET_NAMES) else "?"


def kind_name(k):
    return _KIND_NAMES[k] if 0 <= k < len(_KIND_NAMES) else "?"


class FaultWindow:
    def __init__(self, target, kind, start_ms, end_ms, magnitude=0.0):
        self.target = target
        self.kind = kind
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.magnitude = f32(magnitude)


class ActiveFaults:
    def __init__(self):
        self.not_detected = self.dropout = self.stale = self.zero = self.nan = False
        self.out_of_range = self.stuck_closed = self.stuck_open = self.bounce = False
        self.comm_failure = self.not_ready = self.stuck_output = False
        self.noise_amp = 0.0
        self.out_of_range_value = 0.0
        self.bounce_period_ms = 0
        self.bounce_start_ms = 0


def is_active(w, t):
    return w.start_ms <= t < w.end_ms


class FaultInjector:
    def __init__(self):
        self._windows = []

    def add(self, w):
        self._windows.append(w)

    def windows(self):
        return self._windows

    def query(self, target, t):
        a = ActiveFaults()
        for w in self._windows:
            if w.target != target or not is_active(w, t):
                continue
            k = w.kind
            if k == NOT_DETECTED:
                a.not_detected = True
            elif k == DROPOUT:
                a.dropout = True
            elif k == STALE:
                a.stale = True
            elif k == NOISE:
                a.noise_amp = f32(a.noise_amp + w.magnitude)
            elif k == ZERO_READ:
                a.zero = True
            elif k == NAN_VALUE:
                a.nan = True
            elif k == OUT_OF_RANGE:
                a.out_of_range = True
                a.out_of_range_value = w.magnitude
            elif k == STUCK_CLOSED:
                a.stuck_closed = True
            elif k == STUCK_OPEN:
                a.stuck_open = True
            elif k == BOUNCE:
                a.bounce = True
                a.bounce_period_ms = int(w.magnitude) if w.magnitude > 0.0 else 1
                a.bounce_start_ms = w.start_ms
            elif k == COMM_FAILURE:
                a.comm_failure = True
            elif k == NOT_READY:
                a.not_ready = True
            elif k == STUCK_OUTPUT:
                a.stuck_output = True
        return a
