#!/usr/bin/env python3
"""sim_runner.py - command-line simulation runner (laptop only). [SIMULATED]
(port of firmware/sim/sim_main.cpp; same commands and output)

  python3 tools/sim_runner.py list
  python3 tools/sim_runner.py run <scenario> [--out file.csv]   sensors only
  python3 tools/sim_runner.py run-all [--dir dir]               sensors only, every scenario
  python3 tools/sim_runner.py run-fsw <scenario> <A|B|C|G>      flight software in the loop
  python3 tools/sim_runner.py matrix                            every scenario x every OD-060 policy
  python3 tools/sim_runner.py trace <scenario> <A|B|C|G>        parity trace
  python3 tools/sim_runner.py trace-all

Writes under micropython/build/. Actuator logic is disabled: requests are only
logged as NOT_EXECUTED. Every result is SIMULATED, not hardware validation.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from cansat.config import flight_params as FP  # noqa: E402
from cansat.core import types as T  # noqa: E402
from cansat.sim.file_log import FileLogSink  # noqa: E402
from cansat.sim.fsw_hook import FlightSoftwareHook, format_fsw_stats  # noqa: E402
from cansat.sim.runner import format_summary, run  # noqa: E402
from cansat.sim.scenarios import every_synthetic_scenario, find_synthetic_scenario  # noqa: E402
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params  # noqa: E402
from cansat.sim.trace import TraceHook, trace_header  # noqa: E402

BUILD = os.path.join(ROOT, "build")
POLICY_LETTERS = {"A": FP.POLICY_STRICT_SWITCH_VETO, "B": FP.POLICY_SENSOR_OVERRIDE,
                  "C": FP.POLICY_VOTE_2_OF_3, "G": FP.POLICY_DELAYED_FALLBACK}


def usage():
    print("usage: sim_runner list | run <scenario> [--out file] | run-all [--dir dir] |\n"
          "                  run-fsw <scenario> <A|B|C|G> | matrix |\n"
          "                  trace <scenario> <A|B|C|G> | trace-all")
    return 2


def run_one(sc, path, quiet=False):
    sink = FileLogSink(path)
    if not sink.ok():
        print("cannot open " + path)
        return 1
    s = run(sc, sink)
    sink.close()
    if not quiet:
        sys.stdout.write(format_summary(s))
        print("# full CSV log: " + path + "\n")
    return 0 if s.log_write_failures == 0 else 1


def run_fsw(sc, pol, verbose):
    d = os.path.join(BUILD, "sim", "fsw")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, sc.name + "__" + FP.policy_name(pol) + ".csv")
    sink = FileLogSink(path)
    hook = FlightSoftwareHook(synthetic_flight_params(pol))
    hook.set_store_faults(sc.store_faults)
    s = run(sc, sink, hook)
    sink.close()
    if verbose:
        sys.stdout.write(format_summary(s))
        sys.stdout.write(format_fsw_stats(hook.stats))
        print("# full CSV log: " + path + "\n")
    return (0 if s.log_write_failures == 0 else 1), hook.stats


def run_trace(sc, pol, quiet=False):
    d = os.path.join(BUILD, "trace")
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, sc.name + "__" + FP.policy_name(pol))
    trace, csv = FileLogSink(base + ".trace"), FileLogSink(base + ".csv")
    trace.append(trace_header(sc.name, FP.policy_name(pol)))
    inner = FlightSoftwareHook(synthetic_flight_params(pol))
    inner.set_store_faults(sc.store_faults)
    hook = TraceHook(inner, trace, sc.store_faults)
    s = run(sc, csv, hook)
    trace.close()
    csv.close()
    if not quiet:
        print(base + ".trace")
    return 0 if (s.log_write_failures == 0 and hook.write_failures == 0) else 1


def main(argv):
    if len(argv) < 2:
        return usage()
    cmd = argv[1]
    if cmd == "list":
        for sc in every_synthetic_scenario():
            print("%-30s %s" % (sc.name, sc.description))
        return 0
    if cmd == "run" and len(argv) >= 3:
        sc = find_synthetic_scenario(argv[2])
        if sc is None:
            print("unknown scenario: %s (try: sim_runner list)" % argv[2])
            return 2
        out = os.path.join(BUILD, "sim", sc.name + ".csv")
        if len(argv) >= 5 and argv[3] == "--out":
            out = argv[4]
        else:
            os.makedirs(os.path.join(BUILD, "sim"), exist_ok=True)
        return run_one(sc, out)
    if cmd == "run-all":
        d = argv[3] if len(argv) >= 4 and argv[2] == "--dir" else os.path.join(BUILD, "sim")
        os.makedirs(d, exist_ok=True)
        rc = 0
        for sc in every_synthetic_scenario():
            rc |= run_one(sc, os.path.join(d, sc.name + ".csv"))
        return rc
    if cmd in ("run-fsw", "trace") and len(argv) >= 4:
        sc = find_synthetic_scenario(argv[2])
        pol = POLICY_LETTERS.get(argv[3])
        if sc is None or pol is None:
            return usage()
        return run_fsw(sc, pol, True)[0] if cmd == "run-fsw" else run_trace(sc, pol)
    if cmd == "trace-all":
        rc = 0
        for sc in every_synthetic_scenario():
            for pol in CANDIDATE_POLICIES:
                rc |= run_trace(sc, pol)
        return rc
    if cmd == "matrix":
        print("# SIMULATED - not hardware validation. SYNTHETIC scenarios and parameters.")
        print("# Actuator logic disabled: 'requests' are logged only, never executed.")
        print("# Scenarios marked HAZARD document current behaviour (OD-069); not approved behaviour.")
        print("%-30s %-22s %-18s %-27s %8s %12s %6s" % ("scenario", "policy", "final_state", "chute_status",
                                                         "requests", "sensors_only", "basis"))
        rc = 0
        for sc in every_synthetic_scenario():
            for pol in CANDIDATE_POLICIES:
                r, st = run_fsw(sc, pol, False)
                rc |= r
                print("%-30s %-22s %-18s %-27s %8d %12d %6d" % (
                    sc.name, FP.policy_name(pol), T.state_name(st.final_state), T.chute_name(st.final_chute),
                    st.requests, st.sensors_only_events, st.last_release_basis))
        print("# logs: build/sim/fsw/<scenario>__<policy>.csv")
        return rc
    return usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
