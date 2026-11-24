#!/usr/bin/env python3
"""parity.py - replay C++ parity traces into the Python flight software (D-017).

Laptop tool (CPython). Reads firmware/build/trace/*.trace (make traces), feeds
every boot, reset, store fault and sensor frame into cansat.core.FlightSoftware,
and compares the Python E (event) and S (state) lines with the C++ ones.

Comparison rule (approved tolerances, module 1 report): every E and S field is
compared EXACTLY (state, chute status, event type, event t_ms, detail, fault
mask, all 32 bits). Nothing is masked. Any mismatch is reported, never accepted.

  python3 tools/parity.py            # all traces, flight arithmetic (no FMA)
  python3 tools/parity.py --fma      # diagnosis: emulate the C++ build's fused multiply-add
SIMULATED, not hardware validation.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from cansat.config import flight_params as FP  # noqa: E402
from cansat.core import fmath  # noqa: E402
from cansat.core import types as T  # noqa: E402
from cansat.core.flight_software import BootReport, FlightSoftware  # noqa: E402
from cansat.core.num import f32  # noqa: E402
from cansat.mock.persistent_store import MockPersistentStore  # noqa: E402
from cansat.sim.synthetic_flight_params import synthetic_flight_params  # noqa: E402

DEFAULT_TRACE_DIR = os.path.join(os.path.dirname(ROOT), "firmware", "build", "trace")
STORE_FAULT_CORRUPT = 1  # firmware/sim/Scenario.h StoreFaultKind
STORE_FAULT_ERASE = 2


def _policy_from_name(name):
    for code in range(5):
        if FP.policy_name(code) == name:
            return code
    raise ValueError("unknown policy " + name)


def _b(s):
    return s == "1"


def parse_frame(c):
    f = T.SensorFrame()
    b, m, p, s = f.baro, f.imu, f.power, f.switches
    i = 3
    b.t_ms = int(c[i]); b.pressure_pa = f32(float(c[i + 1])); b.temp_c = f32(float(c[i + 2]))
    b.valid, b.comm_ok, b.data_ready = _b(c[i + 3]), _b(c[i + 4]), _b(c[i + 5])
    i += 6
    m.t_ms = int(c[i])
    m.ax_g, m.ay_g, m.az_g = f32(float(c[i + 1])), f32(float(c[i + 2])), f32(float(c[i + 3]))
    m.gx_dps, m.gy_dps, m.gz_dps = f32(float(c[i + 4])), f32(float(c[i + 5])), f32(float(c[i + 6]))
    m.valid, m.saturated, m.comm_ok, m.data_ready = _b(c[i + 7]), _b(c[i + 8]), _b(c[i + 9]), _b(c[i + 10])
    i += 11
    p.t_ms = int(c[i]); p.bus_v = f32(float(c[i + 1])); p.current_ma = f32(float(c[i + 2]))
    p.valid, p.comm_ok, p.data_ready = _b(c[i + 3]), _b(c[i + 4]), _b(c[i + 5])
    i += 6
    s.t_ms = int(c[i]); s.raw = [_b(c[i + 1]), _b(c[i + 2])]; s.valid = _b(c[i + 3])
    return f


def _outputs(fsw, boot, uptime):
    out = ["E,%d,%d,%d,%d,%d" % (boot, uptime, e.type, e.t_ms, e.detail) for e in fsw.events()]
    out.append("S,%d,%d,%d,%d,%d" % (boot, uptime, fsw.state(), fsw.chute_status(),
                                     fsw.fault_mask()))
    return out


class ReplayResult:
    def __init__(self, name):
        self.name = name
        self.expected = []
        self.produced = []
        self.frames = 0
        self.boots = 0
        self.dropped_events = 0
        self.py_requests_popped = 0  # drained each tick, exactly as firmware/sim/FswHook does

    def cpp_request_events(self):
        return sum(1 for l in self.expected if l.startswith("E,") and int(l.split(",")[3]) == T.EV_REQUEST_EMITTED)

    def final_state_line(self):
        s = [l for l in self.expected if l.startswith("S,")]
        return s[-1] if s else None

    def mismatches(self):
        n = max(len(self.expected), len(self.produced))
        out = []
        for k in range(n):
            e = self.expected[k] if k < len(self.expected) else "<missing>"
            g = self.produced[k] if k < len(self.produced) else "<missing>"
            if e != g:
                out.append((k, e, g))
        return out


def replay(path):
    res = ReplayResult(os.path.basename(path)[:-len(".trace")])
    policy = None
    store = MockPersistentStore()
    fsw = None
    with open(path) as fh:
        lines = fh.read().split("\n")
    for line in lines:
        if not line:
            continue
        if line.startswith("# policy: "):
            policy = _policy_from_name(line[len("# policy: "):].strip())
            continue
        if line[0] == "#":
            continue
        c = line.split(",")
        tag = c[0]
        if tag in ("E", "S"):
            res.expected.append(line)
        elif tag == "B":
            if policy is None:
                raise ValueError(path + ": no policy header")
            boot, uptime = int(c[1]), int(c[2])
            if fsw is not None:
                res.dropped_events += fsw.dropped_events()
            fsw = FlightSoftware(synthetic_flight_params(policy), store)
            fsw.boot(BootReport(_b(c[3]), _b(c[4]), _b(c[5]), int(c[6])), uptime)
            res.produced.extend(_outputs(fsw, boot, uptime))
            res.boots += 1
        elif tag == "R":
            if fsw is not None:
                res.dropped_events += fsw.dropped_events()
            fsw = None
            for k in c[2].split("+"):
                if int(k) == STORE_FAULT_CORRUPT:
                    store.corrupt()
                elif int(k) == STORE_FAULT_ERASE:
                    store.erase()
        elif tag == "F":
            boot, uptime = int(c[1]), int(c[2])
            fsw.tick(parse_frame(c), uptime)
            res.produced.extend(_outputs(fsw, boot, uptime))
            while fsw.pop_request() is not None:  # requests are logged only, never executed
                res.py_requests_popped += 1
            res.frames += 1
        else:
            raise ValueError("unknown trace line: " + line[:40])
    if fsw is not None:
        res.dropped_events += fsw.dropped_events()
    return res


def trace_files(trace_dir):
    if not os.path.isdir(trace_dir):
        return []
    return sorted(os.path.join(trace_dir, n) for n in os.listdir(trace_dir) if n.endswith(".trace"))


def run_all(trace_dir, use_fma=False):
    """use_fma: False = flight arithmetic, True = C++ FMA emulation, None = leave as set."""
    old = fmath.ACCEL_MAG
    if use_fma is not None:
        fmath.ACCEL_MAG = fmath.accel_mag_fma if use_fma else fmath.accel_mag
    try:
        return [replay(p) for p in trace_files(trace_dir)]
    finally:
        fmath.ACCEL_MAG = old


def main(argv):
    use_fma = "--fma" in argv
    args = [a for a in argv[1:] if a != "--fma"]
    trace_dir = args[0] if args else DEFAULT_TRACE_DIR
    results = run_all(trace_dir, use_fma)
    if not results:
        print("no traces in %s (run: cd firmware && make traces)" % trace_dir)
        return 2
    print("# SIMULATED - not hardware validation. Parity vs C++ traces; accel |a|: %s"
          % ("FMA emulation (diagnosis)" if use_fma else "separate rounding (flight arithmetic)"))
    bad = 0
    for r in results:
        mm = r.mismatches()
        status = "MATCH" if not mm else "DIFF(%d)" % len(mm)
        if mm:
            bad += 1
        if r.py_requests_popped != r.cpp_request_events():
            bad += 0 if mm else 1
            status = "REQ-DIFF"
        print("%-62s %-9s frames=%-5d lines=%-5d requests C++=%d Py=%d"
              % (r.name, status, r.frames, len(r.expected), r.cpp_request_events(), r.py_requests_popped))
        for k, e, g in mm[:3]:
            print("    line %d\n      C++: %s\n      Py : %s" % (k, e, g))
    print("parity: %d/%d traces match exactly" % (len(results) - bad, len(results)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
