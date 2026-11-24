# Every C++ TEST_CASE in firmware/test has a same-named Python test (D-017:
# the C++ suites must be fully ported before firmware/ is archived).
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CPP_TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "firmware", "test")
PAIRS = {"test_step1_config_types": "test_cpp_step1_config_types", "test_step2_sim": "test_m3_mocks_sim",
         "test_step3_fsm": "test_cpp_step3_fsm", "test_step3_review": "test_cpp_step3_review",
         "test_interlock": "test_m3_interlock", "test_recovery_faults": "test_m3_recovery_faults"}
# C++ compile-time property Python cannot express; ported as a test pinning the limitation.
RENAMED = {"state_event_command_are_distinct_types": "LIMITATION_state_event_command_are_not_distinct_types"}


class CppPortCoverage(unittest.TestCase):
    def test_every_cpp_test_case_has_a_python_counterpart(self):
        if not os.path.isdir(CPP_TEST_DIR):
            self.skipTest("firmware/test not present")
        cpp_files = sorted(f[:-4] for f in os.listdir(CPP_TEST_DIR) if f.startswith("test_") and f.endswith(".cpp"))
        self.assertEqual(sorted(PAIRS), cpp_files, "a C++ test file has no Python counterpart")
        total = 0
        for cpp, py in PAIRS.items():
            with open(os.path.join(CPP_TEST_DIR, cpp + ".cpp")) as f:
                names = re.findall(r"^TEST_CASE\((\w+)\)", f.read(), re.M)
            with open(os.path.join(HERE, py + ".py")) as f:
                have = set(re.findall(r"def test_(\w+)\(", f.read()))
            for n in names:
                self.assertIn(RENAMED.get(n, n), have, "%s.%s not ported" % (cpp, n))
            total += len(names)
        self.assertEqual(total, 157)


if __name__ == "__main__":
    unittest.main()
