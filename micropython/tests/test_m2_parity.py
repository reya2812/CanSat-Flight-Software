# Module 2 acceptance: replay every C++ parity trace (17 scenarios x 4 policies)
# into the Python flight software; every event and state line must match exactly.
# Needs the traces:  cd firmware && make traces.  SIMULATED, not hardware validation.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import parity  # noqa: E402

EXPECTED_TRACES = 17 * 4


class TraceParity(unittest.TestCase):
    def setUp(self):
        if not parity.trace_files(parity.DEFAULT_TRACE_DIR):
            self.skipTest("no C++ traces: run `cd firmware && make traces` first")

    def check(self, use_fma):
        results = parity.run_all(parity.DEFAULT_TRACE_DIR, use_fma)
        self.assertEqual(len(results), EXPECTED_TRACES)
        for r in results:
            with self.subTest(trace=r.name):
                self.assertGreater(r.frames, 0)
                self.assertEqual(r.dropped_events, 0)
                mm = r.mismatches()
                self.assertEqual(mm, [], "first mismatch: %r" % (mm[:1],))
                self.assertEqual(r.py_requests_popped, r.cpp_request_events())

    def test_request_counts_match_cpp_matrix(self):
        # Independent check against the C++ matrix "requests" column (sim_runner matrix).
        import subprocess
        runner = os.path.join(os.path.dirname(ROOT), "firmware", "build", "sim_runner")
        if not os.path.exists(runner):
            self.skipTest("firmware/build/sim_runner not built")
        out = subprocess.run([runner, "matrix"], cwd=os.path.join(os.path.dirname(ROOT), "firmware"),
                             capture_output=True, text=True, check=True).stdout
        want = {}
        for line in out.split("\n"):
            c = line.split()
            if len(c) == 7 and not line.startswith(("#", "scenario")):
                want[c[0] + "__" + c[1]] = (c[2], c[3], int(c[4]))
        self.assertEqual(len(want), EXPECTED_TRACES)
        from cansat.core import types as T
        for r in parity.run_all(parity.DEFAULT_TRACE_DIR):
            with self.subTest(trace=r.name):
                st = r.produced[[i for i, l in enumerate(r.produced) if l.startswith("S,")][-1]].split(",")
                self.assertEqual((T.state_name(int(st[3])), T.chute_name(int(st[4])), r.py_requests_popped),
                                 want[r.name])

    def test_float_margin_report_runs(self):
        import float_margins
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(float_margins.main(["float_margins.py"]), 0)
        self.assertIn("drop >= baro_min_drop_m", out.getvalue())

    def test_flight_arithmetic_matches_every_trace(self):
        self.check(use_fma=False)

    def test_fma_emulation_matches_every_trace(self):
        self.check(use_fma=True)


if __name__ == "__main__":
    unittest.main()
