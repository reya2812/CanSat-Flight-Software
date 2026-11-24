# actuator_manager.py - the ONLY caller of ActuatorDriver.apply() (OD-070). [PROPOSED]
# (port of lib/core/ActuatorManager.h/.cpp)
#
# MOCK-ONLY. Physical actuation is disabled (build_flags, OD-059, D-017) and,
# independently, at run time: a driver whose is_physical() is not False is
# refused and never called.
# Two-phase protocol, so evidence is checked twice:
#   authorize(request) -> runs the interlock; on success returns a single-use
#                         Authorization (nothing executed).
#   execute(token)     -> re-reads arming and connection, runs the interlock
#                         AGAIN, only then calls the driver.
# A token is valid only within the boot that issued it.
# Known gap (OD-070): the "executed" record is RAM-only (see C++ header).
from cansat.config import build_flags
from cansat.core import types as T
from cansat.core.deployment_interlock import DeploymentInterlock, InterlockInputs, InterlockResult

if build_flags.PHYSICAL_ACTUATORS_ENABLED is not False:  # C++: static_assert
    raise ImportError("ActuatorManager is mock-only (OD-059): PHYSICAL_ACTUATORS_ENABLED must be False")


class FlightStatusView:
    def __init__(self, state=T.STATE_POWER_ON_SELF_CHECK, one_shot_flags=0, release_timer_start_ms=0):
        self.state = state
        self.one_shot_flags = one_shot_flags
        self.release_timer_start_ms = release_timer_start_ms


class Authorization:
    def __init__(self):
        self.valid = False
        self.request = T.REQ_RELEASE_PARACHUTE
        self.t_ms = 0
        self.boot_count = 0
        self.serial = 0


def pack_actuator_decision(phase, request, decision, reasons):
    return ((reasons & 0xFFFF) | (decision << 16) | ((request & 0x7F) << 24) |
            (0x80000000 if phase else 0))


class ActuatorManager:
    def __init__(self, flight, il, connection, arming, driver, events, boot_count):
        self._interlock = DeploymentInterlock(flight, il)
        self._connection = connection
        self._arming = arming
        self._driver = driver
        self._events = events
        self._boot_count = boot_count
        self._next_serial = 1
        self._outstanding = 0  # 0 = no live authorization
        self._executed = False
        self._executed_count = 0
        self._last = InterlockResult()

    def executed_count(self):
        return self._executed_count

    def executed_this_boot(self):
        return self._executed

    def last_result(self):
        return self._last

    def _report(self, phase, request, d, reasons, now):
        self._events.on_event(T.Event(T.EV_ACTUATOR_DECIDED, now, pack_actuator_decision(phase, request, d, reasons)))

    def _check(self, request, fs, now):
        i = InterlockInputs()
        i.request = request
        i.now_ms = now
        i.state = fs.state
        i.one_shot_flags = fs.one_shot_flags
        i.release_timer_start_ms = fs.release_timer_start_ms
        i.executed_this_boot = self._executed
        i.arming = self._arming.read(now)          # fresh read every evaluation
        i.connection = self._connection.assess(now)  # fresh read every evaluation
        r = self._interlock.evaluate(i)
        if self._driver.is_physical() is not False:
            # Physical actuation is disabled (OD-059): refuse regardless of the interlock.
            r.reasons |= T.IL_PHYSICAL_DRIVER_REFUSED
            r.permitted = False
            r.decision = T.DEC_BLOCKED_BUILD_DISABLED
        self._last = r
        return r

    def authorize(self, request, fs, now):
        a = Authorization()
        r = self._check(request, fs, now)
        self._report(0, request, r.decision, r.reasons, now)
        if not r.permitted:
            return a
        a.valid = True
        a.request = request
        a.t_ms = now
        a.boot_count = self._boot_count
        a.serial = self._next_serial
        self._next_serial += 1
        self._outstanding = a.serial  # a newer authorization supersedes an older one
        return a

    def execute(self, auth, fs, now):
        reasons = 0
        if not auth.valid:
            d = T.DEC_BLOCKED_NOT_AUTHORIZED
        elif auth.boot_count != self._boot_count:
            d = T.DEC_BLOCKED_STALE_AUTHORIZATION
        elif auth.serial != self._outstanding:
            d = T.DEC_BLOCKED_ALREADY_DONE if self._executed else T.DEC_BLOCKED_NOT_AUTHORIZED
        else:
            self._outstanding = 0  # single use, whatever the outcome
            r = self._check(auth.request, fs, now)
            reasons = r.reasons
            if not r.permitted:
                d = r.decision
            else:
                self._executed = True  # record the one-shot BEFORE acting on it
                self._executed_count += 1
                self._driver.apply(auth.request)  # mock driver only (is_physical checked in _check)
                d = T.DEC_EXECUTED_SIMULATED
        self._report(1, auth.request, d, reasons, now)
        return d

    def handle(self, request, fs, now):
        a = self.authorize(request, fs, now)
        if not a.valid:
            return self._last.decision
        return self.execute(a, fs, now)
