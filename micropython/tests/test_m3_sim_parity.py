# Module 3 acceptance: the Python simulator (mocks + flight software) produces
# BYTE-IDENTICAL output to the C++ reference for all 17 scenarios:
#   - sensor-only CSV per scenario (17),
#   - flight-software CSV per scenario x policy (68),
#   - parity trace + its CSV per scenario x policy (68 + 68),
#   - the matrix printed by sim_runner.
# Needs the C++ outputs:  cd firmware && make sim && make matrix && make traces.
# SIMULATED, not hardware validation.
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE = os.path.join(os.path.dirname(ROOT), "firmware")
sys.path.insert(0, os.path.join(ROOT, "tools"))

from cansat.config import flight_params as FP  # noqa: E402
from cansat.mock.memory_log import MemoryLogSink  # noqa: E402
from cansat.sim import sim_math  # noqa: E402
from cansat.sim.fsw_hook import FlightSoftwareHook  # noqa: E402
from cansat.sim.runner import run  # noqa: E402
from cansat.sim.scenarios import every_synthetic_scenario  # noqa: E402
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params  # noqa: E402
from cansat.sim.trace import TraceHook, trace_header  # noqa: E402


def cpp_lines(*rel):
    path = os.path.join(FIRMWARE, "build", *rel)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().split("\n")[:-1]


class SimulatorParity(unittest.TestCase):
    def setUp(self):
        if cpp_lines("sim", "nominal.csv") is None or cpp_lines("trace", "nominal__P-A_StrictSwitchVeto.trace") is None:
            self.skipTest("C++ outputs missing: cd firmware && make sim && make matrix && make traces")

    def first_diff(self, a, b):
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "<missing>"
            y = b[i] if i < len(b) else "<missing>"
            if x != y:
                return i, x[:160], y[:160]
        return None

    def test_scenario_set_is_the_17(self):
        self.assertEqual(len(every_synthetic_scenario()), 17)

    def test_powf_comes_from_the_c_library(self):
        self.assertEqual(sim_math.POWF_SOURCE, "C library powf (ctypes)")

    def test_sensor_only_csv_identical(self):
        for sc in every_synthetic_scenario():
            with self.subTest(scenario=sc.name):
                out = MemoryLogSink()
                run(sc, out)
                self.assertIsNone(self.first_diff(out.lines, cpp_lines("sim", sc.name + ".csv")))

    def test_flight_software_csv_and_trace_identical(self):
        for sc in every_synthetic_scenario():
            for pol in CANDIDATE_POLICIES:
                name = sc.name + "__" + FP.policy_name(pol)
                with self.subTest(run=name):
                    csv, trace = MemoryLogSink(), MemoryLogSink()
                    trace.lines.extend(trace_header(sc.name, FP.policy_name(pol)).split("\n"))
                    inner = FlightSoftwareHook(synthetic_flight_params(pol))
                    inner.set_store_faults(sc.store_faults)
                    run(sc, csv, TraceHook(inner, trace, sc.store_faults))
                    self.assertIsNone(self.first_diff(trace.lines, cpp_lines("trace", name + ".trace")))
                    self.assertIsNone(self.first_diff(csv.lines, cpp_lines("trace", name + ".csv")))
                    self.assertIsNone(self.first_diff(csv.lines, cpp_lines("sim", "fsw", name + ".csv")))

    def test_matrix_output_identical(self):
        runner = os.path.join(FIRMWARE, "build", "sim_runner")
        if not os.path.exists(runner):
            self.skipTest("firmware/build/sim_runner not built")
        cpp = subprocess.run([runner, "matrix"], cwd=FIRMWARE, capture_output=True, text=True, check=True).stdout
        import sim_runner
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(sim_runner.main(["sim_runner.py", "matrix"]), 0)
        self.assertEqual(out.getvalue(), cpp)


if __name__ == "__main__":
    unittest.main()
