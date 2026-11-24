# trace.py - parity trace exporter (port of firmware/sim/TraceExporter.cpp, format v1).
# [SIMULATED] Wraps FlightSoftwareHook without changing it. See the C++ header
# for the line format. Output must be byte-identical to the C++ traces.
from cansat.core import types as T
from cansat.sim.runner import SimHook

TRACE_FORMAT_VERSION = 1


def _b(v):
    return "1" if v else "0"


def g9(x):
    """C printf %.9g of a float32 value (Python uses the same correctly rounded algorithm)."""
    return "%.9g" % x


class TraceHook(SimHook):
    def __init__(self, inner, trace, store_faults):
        self._inner = inner
        self._trace = trace
        self._store_faults = list(store_faults)
        self._boot = 0
        self._resets = 0
        self.write_failures = 0

    def _line(self, s):
        if not self._trace.append(s):
            self.write_failures += 1

    def extra_header(self):
        return self._inner.extra_header()

    def banner_line(self):
        return self._inner.banner_line()

    def empty_columns(self):
        return self._inner.empty_columns()

    def _events(self, uptime):
        f = self._inner.fsw
        if f is None:
            return
        for e in f.events():
            self._line("E,%d,%d,%d,%d,%d" % (self._boot, uptime, e.type, e.t_ms, e.detail))

    def _state(self, uptime):
        f = self._inner.fsw
        if f is None:
            return
        self._line("S,%d,%d,%d,%d,%d" % (self._boot, uptime, f.state(), f.chute_status(), f.fault_mask()))

    def on_boot(self, baro_ok, imu_ok, power_ok, uptime_ms):
        self._boot += 1
        self._line("B,%d,%d,%s,%s,%s,%d" % (self._boot, uptime_ms, _b(baro_ok), _b(imu_ok), _b(power_ok),
                                            T.SELF_TEST_NOT_RUN))
        r = self._inner.on_boot(baro_ok, imu_ok, power_ok, uptime_ms)
        self._events(uptime_ms)
        self._state(uptime_ms)
        return r

    def on_reset(self):
        kinds = "+".join(str(f.kind) for f in self._store_faults if f.reset_index == self._resets)
        self._line("R,%d,%s" % (self._resets, kinds or "0"))
        self._resets += 1
        self._inner.on_reset()

    def on_tick(self, fr, uptime_ms):
        b, m, p, s = fr.baro, fr.imu, fr.power, fr.switches
        self._line(",".join((
            "F", str(self._boot), str(uptime_ms),
            str(b.t_ms), g9(b.pressure_pa), g9(b.temp_c), _b(b.valid), _b(b.comm_ok), _b(b.data_ready),
            str(m.t_ms), g9(m.ax_g), g9(m.ay_g), g9(m.az_g), g9(m.gx_dps), g9(m.gy_dps), g9(m.gz_dps),
            _b(m.valid), _b(m.saturated), _b(m.comm_ok), _b(m.data_ready),
            str(p.t_ms), g9(p.bus_v), g9(p.current_ma), _b(p.valid), _b(p.comm_ok), _b(p.data_ready),
            str(s.t_ms), _b(s.raw[0]), _b(s.raw[1]), _b(s.valid))))
        r = self._inner.on_tick(fr, uptime_ms)
        self._events(uptime_ms)
        self._state(uptime_ms)
        return r


def trace_header(scenario, policy):
    return ("# SIMULATED - not hardware validation. SYNTHETIC data and parameters.\n"
            "# cansat parity trace v%d\n# scenario: %s\n# policy: %s" % (TRACE_FORMAT_VERSION, scenario, policy))
