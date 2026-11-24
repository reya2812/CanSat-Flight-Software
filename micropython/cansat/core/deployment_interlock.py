# deployment_interlock.py - downstream deployment interlock (OD-070). [PROPOSED]
# (port of lib/core/DeploymentInterlock.h/.cpp)
#
# Re-evaluates, when a request would be acted on, whether ReleaseParachute may
# proceed. Never sees sensor samples; never trusts the detector's latch. Its
# only connection input is an ABSTRACT assessment whose method is unresolved
# (OD-060, OD-068; A1-A5 all open).
# Rule: permit only if EVERY gate passes; each failing gate adds a reason bit;
# the decision reports the first failing gate, in this order:
#   params complete -> supported request -> state PARACHUTE_DEPLOY -> release
#   confirmed -> not already executed -> separation delay elapsed -> armed ->
#   assessment Separated, fresh and not future-dated.
# The interlock decides; it never actuates.
from cansat.core import types as T


class InterlockInputs:
    def __init__(self):
        self.request = T.REQ_RELEASE_PARACHUTE
        self.now_ms = 0
        self.state = T.STATE_POWER_ON_SELF_CHECK
        self.one_shot_flags = 0
        self.release_timer_start_ms = 0
        self.executed_this_boot = False
        self.arming = T.ArmingSample()
        self.connection = T.ConnectionAssessmentSample()


class InterlockResult:
    def __init__(self, permitted=False, decision=T.DEC_BLOCKED_PARAMS_INCOMPLETE, reasons=0):
        self.permitted = permitted
        self.decision = decision
        self.reasons = reasons


class DeploymentInterlock:
    def __init__(self, flight, il):
        self._complete = flight.is_complete() and il.is_complete()
        self._min_sep = 0
        self._max_age = 0
        if self._complete:
            self._min_sep = flight.interlock.min_separation_ms.require()
            self._max_age = il.connection_max_age_ms.require()

    def configured(self):
        return self._complete

    def evaluate(self, i):
        st = {"why": 0, "first": T.DEC_EXECUTED_SIMULATED}

        def fail(bit, d):
            if st["why"] == 0:
                st["first"] = d
            st["why"] |= bit

        c = self._complete
        if not c:
            fail(T.IL_PARAMS_INCOMPLETE, T.DEC_BLOCKED_PARAMS_INCOMPLETE)
        if i.request != T.REQ_RELEASE_PARACHUTE:  # no rule for other actuators (OD-037, OD-052)
            fail(T.IL_UNSUPPORTED_REQUEST, T.DEC_BLOCKED_UNSUPPORTED_REQUEST)
        if i.state != T.STATE_PARACHUTE_DEPLOY:
            fail(T.IL_WRONG_STATE, T.DEC_BLOCKED_WRONG_STATE)
        if not (i.one_shot_flags & T.ONESHOT_RELEASE_CONFIRMED):
            fail(T.IL_RELEASE_NOT_CONFIRMED, T.DEC_BLOCKED_RELEASE_NOT_CONFIRMED)
        if i.executed_this_boot:
            fail(T.IL_ALREADY_DONE, T.DEC_BLOCKED_ALREADY_DONE)
        if c and (i.now_ms < i.release_timer_start_ms or i.now_ms - i.release_timer_start_ms < self._min_sep):
            fail(T.IL_SEPARATION_DELAY, T.DEC_BLOCKED_SEPARATION_DELAY)

        a = i.arming.state
        if a == T.ARM_DISARMED:
            fail(T.IL_NOT_ARMED, T.DEC_BLOCKED_NOT_ARMED)
        elif a != T.ARM_ARMED:  # Unknown or any other code
            fail(T.IL_ARM_UNKNOWN, T.DEC_BLOCKED_NOT_ARMED)

        cv = i.connection.value
        if cv == T.CONN_CONNECTED:
            fail(T.IL_CONN_CONNECTED, T.DEC_BLOCKED_INTERLOCK_MOUNTED)
        elif cv == T.CONN_INDETERMINATE:
            fail(T.IL_CONN_INDETERMINATE, T.DEC_BLOCKED_CONNECTION_INDETERMINATE)
        elif cv == T.CONN_INVALID:
            fail(T.IL_CONN_INVALID, T.DEC_BLOCKED_CONNECTION_INVALID)
        elif cv != T.CONN_SEPARATED:  # Unavailable or any other code
            fail(T.IL_CONN_UNAVAILABLE, T.DEC_BLOCKED_CONNECTION_UNAVAILABLE)
        if cv != T.CONN_UNAVAILABLE:  # time consistency for any assessment claiming a value
            if i.connection.t_ms > i.now_ms:
                fail(T.IL_CONN_FUTURE_TIMESTAMP, T.DEC_BLOCKED_CONNECTION_STALE)
            elif c and i.now_ms - i.connection.t_ms > self._max_age:
                fail(T.IL_CONN_STALE, T.DEC_BLOCKED_CONNECTION_STALE)
            elif not c:
                fail(T.IL_CONN_STALE, T.DEC_BLOCKED_CONNECTION_STALE)  # no approved age limit exists

        why = st["why"]
        return InterlockResult(why == 0, T.DEC_AUTHORIZED_PENDING_EXECUTION if why == 0 else st["first"], why)
