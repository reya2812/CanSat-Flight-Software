# Module 1 parity: every numeric code in the port equals the C++ reference.
import unittest

from cansat.core import types as T
from cansat.config import flight_params as FP
from tests import cpp_ref


def camel_to_upper(name):
    out = ""
    for i, ch in enumerate(name):
        if ch.isupper() and i and (not name[i - 1].isupper() or (i + 1 < len(name) and name[i + 1].islower())):
            out += "_"
        out += ch.upper()
    return out


class EnumParity(unittest.TestCase):
    def setUp(self):
        self.types_h = cpp_ref.read("lib/core/Types.h")
        self.params_h = cpp_ref.read("include/config/FlightParams.h")

    def check(self, text, enum_name, prefix, strip_k=None, rename=None):
        ref = cpp_ref.enum_values(text, enum_name)
        self.assertTrue(ref, enum_name)
        for cpp_name, value in ref.items():
            n = cpp_name
            if strip_k and n.startswith(strip_k):
                n = n[len(strip_k):]
            py = (rename or {}).get(cpp_name, prefix + camel_to_upper(n))
            self.assertTrue(hasattr(T, py) or hasattr(FP, py), "%s.%s -> %s missing" % (enum_name, cpp_name, py))
            got = getattr(T, py) if hasattr(T, py) else getattr(FP, py)
            self.assertEqual(got, value, "%s.%s" % (enum_name, cpp_name))
        return ref

    def test_flight_state(self):
        ref = self.check(self.types_h, "FlightState", "STATE_")
        self.assertEqual(len(ref), T.FLIGHT_STATE_COUNT)

    def test_event_type(self):
        self.check(self.types_h, "EventType", "EV_")

    def test_release_basis_and_touchdown(self):
        self.check(self.types_h, "ReleaseBasis", "BASIS_", strip_k="kBasis")
        self.check(self.types_h, "TouchdownDetail", "TOUCHDOWN_", strip_k="kTouchdown")

    def test_chute_status(self):
        self.check(self.types_h, "ChuteStatus", "CHUTE_")

    def test_requests_and_decisions(self):
        self.check(self.types_h, "ActuatorRequest", "REQ_")
        self.check(self.types_h, "ActuatorDecision", "DEC_")

    def test_interlock_types(self):
        self.check(self.types_h, "ConnectionAssessment", "CONN_")
        self.check(self.types_h, "ArmState", "ARM_")
        self.check(self.types_h, "InterlockReason", "IL_", strip_k="kIl")
        self.check(self.types_h, "SelfTestResult", "SELF_TEST_")

    def test_fault_bits(self):
        ref = self.check(self.types_h, "FaultBit", "FAULT_", strip_k="kFault")
        # The port defines no fault bit that C++ lacks (OD-072 undecided).
        py = {n: getattr(T, n) for n in dir(T) if n.startswith("FAULT_")}
        self.assertEqual(sorted(py.values()), sorted(ref.values()))

    def test_one_shot_flags(self):
        self.check(self.types_h, "OneShotFlag", "ONESHOT_", strip_k="kOneShot")

    def test_param_enums(self):
        self.check(self.params_h, "SwitchVote", "SWITCH_VOTE_", rename={"Sw1Only": "SWITCH_VOTE_SW1_ONLY"})
        self.check(self.params_h, "StuckSwitchPolicy", "POLICY_",
                   rename={"Vote2of3": "POLICY_VOTE_2_OF_3"})
        self.check(self.params_h, "PersistFailurePolicy", "PERSIST_")

    def test_names_match_cpp_to_string(self):
        for s, name in ((1, "POWER_ON_SELF_CHECK"), (5, "PARACHUTE_DEPLOY"), (8, "LANDED")):
            self.assertEqual(T.state_name(s), name)
        self.assertEqual(T.state_name(0), "INVALID")
        self.assertEqual(T.chute_name(T.CHUTE_OPENING_NOT_SENSED_TIMEOUT), "OPENING_NOT_SENSED")
        self.assertEqual(FP.policy_name(FP.POLICY_DELAYED_FALLBACK), "P-G_DelayedFallback")
        self.assertEqual(T.event_name(T.EV_REQUEST_WITHHELD), "RequestWithheld")
        self.assertEqual(T.decision_name(T.DEC_AUTHORIZED_PENDING_EXECUTION), "AuthorizedPendingExecution")

    def test_state_code_validity(self):
        self.assertFalse(T.is_valid_flight_state_code(0))
        self.assertTrue(T.is_valid_flight_state_code(1))
        self.assertTrue(T.is_valid_flight_state_code(8))
        self.assertFalse(T.is_valid_flight_state_code(9))

    def test_sample_defaults_are_not_established(self):
        for s in (T.BaroSample(), T.ImuSample(), T.PowerSample()):
            self.assertFalse(s.valid)
            self.assertFalse(s.comm_ok)
            self.assertFalse(s.data_ready)
            self.assertEqual(s.t_ms, 0)
        sw = T.SwitchSample()
        self.assertEqual(sw.raw, [False, False])
        self.assertFalse(sw.valid)
        self.assertFalse(T.ImuSample().saturated)

    def test_sample_frames_do_not_share_lists(self):
        a, b = T.SwitchSample(), T.SwitchSample()
        a.raw[0] = True
        self.assertFalse(b.raw[0])


if __name__ == "__main__":
    unittest.main()
