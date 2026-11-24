# actuators.py - mocks for the deployment interlock and actuator manager. [SIMULATED]
# (port of lib/hal_mock/MockActuators.h). Nothing here drives hardware;
# MockActuatorDriver.is_physical() is always False and only records requests.
from cansat.core import types as T
from cansat.hal.interfaces import ActuatorDriver, ArmingSource, ConnectionAssessmentSource


class MockActuatorDriver(ActuatorDriver):
    def __init__(self):
        self.applied = []

    def apply(self, request):
        self.applied.append(request)

    def is_physical(self):
        return False


class ScriptedConnectionSource(ConnectionAssessmentSource):
    """Returns a scripted assessment. `next` entries are consumed one per assess()
    call (then `current` is returned). Stamps t_ms with the caller's time unless
    fixed_time is True."""

    def __init__(self):
        self.current = T.ConnectionAssessmentSample()
        self.next = []
        self.fixed_time = False
        self.calls = 0

    def assess(self, now_ms):
        self.calls += 1
        s = self.current
        if self.next:
            s = self.next.pop(0)
            self.current = s
        out = T.ConnectionAssessmentSample(s.value, s.t_ms, s.provenance)
        if not self.fixed_time:
            out.t_ms = now_ms
        return out


class MockArmingSource(ArmingSource):
    def __init__(self):
        self.current = T.ArmingSample()
        self.next = []
        self.calls = 0

    def read(self, now_ms):
        self.calls += 1
        s = self.current
        if self.next:
            s = self.next.pop(0)
            self.current = s
        return T.ArmingSample(s.state, now_ms)
