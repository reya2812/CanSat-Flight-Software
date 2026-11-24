# Module 1: Param (no defaults) and FlightParams completeness, mirrored from C++.
import math
import unittest

from cansat.core.param import Param, ParamUnset, KIND_U32, KIND_BOOL, KIND_FLOAT, KIND_ENUM
from cansat.config import flight_params as FP
from tests import cpp_ref

# SYNTHETIC test values only (never firmware defaults).
SYNTHETIC_VALUE = {KIND_U32: 1, KIND_BOOL: True, KIND_FLOAT: 1.0, KIND_ENUM: 1}


class ParamBehaviour(unittest.TestCase):
    def test_starts_unset_with_no_fallback(self):
        for k in (KIND_U32, KIND_BOOL, KIND_FLOAT, KIND_ENUM):
            p = Param(k)
            self.assertFalse(p.is_set())
            self.assertEqual(p.get(), (False, None))

    def test_set_get_clear(self):
        p = Param(KIND_U32)
        p.set(250)
        self.assertEqual(p.get(), (True, 250))
        p.clear()
        self.assertEqual(p.get(), (False, None))

    def test_u32_range_enforced(self):
        p = Param(KIND_U32)
        p.set(0)
        p.set(0xFFFFFFFF)
        for bad in (-1, 1 << 32, 1.5, True, "1", None):
            with self.assertRaises(ValueError):
                p.set(bad)

    def test_bool_float_enum_kinds(self):
        b = Param(KIND_BOOL)
        b.set(False)
        self.assertEqual(b.get(), (True, False))
        with self.assertRaises(ValueError):
            b.set(0)
        f = Param(KIND_FLOAT)
        f.set(2)
        self.assertEqual(f.get(), (True, 2.0))
        for bad in (math.nan, math.inf, True, "1"):
            with self.assertRaises(ValueError):
                f.set(bad)
        e = Param(KIND_ENUM)
        e.set(0)
        with self.assertRaises(ValueError):
            e.set(256)

    def test_require_raises_when_unset(self):
        p = Param(KIND_U32)
        with self.assertRaises(ParamUnset):
            p.require()
        p.set(7)
        self.assertEqual(p.require(), 7)

    def test_float_stored_as_float32(self):
        f = Param(KIND_FLOAT)
        f.set(0.3)
        self.assertEqual(f.require(), 0.30000001192092896)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            Param("double")


def fill(obj):
    for name, v in vars(obj).items():
        if isinstance(v, Param):
            v.set(SYNTHETIC_VALUE[v.kind])


def param_names(obj):
    return [n for n, v in vars(obj).items() if isinstance(v, Param)]


class IncompleteParamsAreHandledEverywhere(unittest.TestCase):
    """Every consumer must cope with unset Params without raising (item 7)."""

    def test_each_missing_param_never_raises_and_never_requests(self):
        from cansat.core.flight_software import BootReport, FlightSoftware
        from cansat.mock.persistent_store import MockPersistentStore
        from tests.helpers_m2 import frame, seeded_store
        from cansat.core import types as T
        from cansat.sim.synthetic_flight_params import synthetic_flight_params
        names = []
        for part in ("release", "interlock", "transitions", "validation"):
            for n in param_names(getattr(FP.FlightParams(), part)):
                names.append((part, n))
        names.append((None, None))  # and a fully empty set
        for part, n in names:
            with self.subTest(param=n):
                if part is None:
                    prm = FP.FlightParams()
                else:
                    prm = synthetic_flight_params(FP.POLICY_VOTE_2_OF_3)
                    getattr(getattr(prm, part), n).clear()
                st = seeded_store(T.STATE_PARACHUTE_DEPLOY, T.ONESHOT_RELEASE_CONFIRMED)
                fs = FlightSoftware(prm, st)
                fs.boot(BootReport(True, True, True), 0)
                reqs = 0
                for t in range(50, 3000, 50):
                    fs.tick(frame(t, sw_open=True), t)
                    while fs.pop_request() is not None:
                        reqs += 1
                if not prm.is_complete():
                    self.assertEqual(reqs, 0)
                    self.assertTrue(fs.fault_mask() & T.FAULT_PARAMS_INCOMPLETE)


class FlightParamsParity(unittest.TestCase):
    def setUp(self):
        self.h = cpp_ref.read("include/config/FlightParams.h")

    def test_same_members_as_cpp(self):
        for cpp, obj in (("ValidationParams", FP.ValidationParams()), ("ReleaseParams", FP.ReleaseParams()),
                         ("InterlockParams", FP.InterlockParams()), ("TransitionParams", FP.TransitionParams()),
                         ("DeploymentInterlockParams", FP.DeploymentInterlockParams())):
            self.assertEqual(sorted(param_names(obj)), sorted(cpp_ref.param_members(self.h, cpp)), cpp)

    def test_new_params_are_incomplete(self):
        self.assertFalse(FP.FlightParams().is_complete())
        self.assertFalse(FP.DeploymentInterlockParams().is_complete())

    def test_every_required_member_is_required(self):
        optional = {("InterlockParams", "fallback_delay_ms")}  # required only for DelayedFallback
        for cls in (FP.ValidationParams, FP.ReleaseParams, FP.InterlockParams, FP.TransitionParams,
                    FP.DeploymentInterlockParams):
            full = cls()
            fill(full)
            self.assertTrue(full.is_complete(), cls.__name__)
            for name in param_names(full):
                obj = cls()
                fill(obj)
                getattr(obj, name).clear()
                expect = (cls.__name__, name) in optional
                self.assertEqual(obj.is_complete(), expect, "%s.%s" % (cls.__name__, name))

    def test_unset_enum_codes_never_complete(self):
        r = FP.ReleaseParams()
        fill(r)
        r.switch_vote.set(FP.SWITCH_VOTE_UNSET)
        self.assertFalse(r.is_complete())
        for field in ("stuck_switch_policy", "persist_failure_policy"):
            i = FP.InterlockParams()
            fill(i)
            getattr(i, field).set(0)
            self.assertFalse(i.is_complete(), field)

    def test_delayed_fallback_requires_fallback_delay(self):
        i = FP.InterlockParams()
        fill(i)
        i.fallback_delay_ms.clear()
        i.stuck_switch_policy.set(FP.POLICY_DELAYED_FALLBACK)
        self.assertFalse(i.is_complete())
        i.fallback_delay_ms.set(1)
        self.assertTrue(i.is_complete())

    def test_deployment_interlock_params_not_in_flight_params(self):
        f = FP.FlightParams()
        for part in (f.release, f.interlock, f.transitions, f.validation):
            fill(part)
        self.assertTrue(f.is_complete())
        self.assertFalse(hasattr(f, "deployment"))


if __name__ == "__main__":
    unittest.main()
