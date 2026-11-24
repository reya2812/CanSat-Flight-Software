# flight_state_manager.py - the flight state machine ([PDR] slide 19).
# (port of lib/core/FlightStateManager.h/.cpp; the permitted-transition table is there)
#
# Consumes Events only. Never reads sensors, never touches hardware. It may
# EMIT ActuatorRequests into a queue; nothing consumes that queue for actuation
# (no actuator output code exists, D-017).
#
#   1 -SelfCheckPass-> 2 -AscentDetected-> 3 -ReleaseCandidate-> 4 -ReleaseConfirmed-> 5
#   3 -ReleaseConfirmed-> 4 then 5 (two legal steps)
#   5 -ChuteOpenDetected (sensed, after request)-> 6 -DescentConfirmed-> 7 -TouchdownDetected-> 8
#   Abnormal, flagged (OD-065, provisional): 5 -> 8 and 6 -> 8 on TouchdownDetected.
# Timeouts NEVER cause a transition (chute_open_timeout_ms raises an alarm only).
from cansat.core import types as T
from cansat.core.num import u32_sub, u8
from cansat.config import flight_params as FP

QUEUE_CAP = 4


def is_permitted(frm, to):
    if not T.is_valid_flight_state_code(frm) or not T.is_valid_flight_state_code(to):
        return False
    if to == frm + 1:
        return True
    return to == T.STATE_LANDED and (frm == T.STATE_PARACHUTE_DEPLOY or frm == T.STATE_PANEL_DEPLOY)


class FlightStateManager:
    def __init__(self, params, recovery, out):
        self._rec = recovery
        self._out = out
        self._complete = params.is_complete()
        self._min_sep = 0
        self._chute_timeout = 0
        self._persist_policy = FP.PERSIST_UNSET
        if self._complete:
            self._min_sep = params.interlock.min_separation_ms.require()
            self._persist_policy = params.interlock.persist_failure_policy.require()
            self._chute_timeout = params.transitions.chute_open_timeout_ms.require()
        self._state = T.STATE_POWER_ON_SELF_CHECK
        self._flags = 0
        self._faults = 0
        self._release_ms = 0
        self._request_ms = 0
        self._opening_sensed = False
        self._not_sensed_alarm = False
        self._withheld_reported = False
        self._queue = []
        self._requests_emitted = 0

    # ---- accessors ----
    def state(self):
        return self._state

    def one_shot_flags(self):
        return self._flags

    def chute_requested(self):
        return (self._flags & T.ONESHOT_CHUTE_REQUESTED) != 0

    def chute_status(self):
        if not self.chute_requested():
            return T.CHUTE_NOT_REQUESTED
        if self._opening_sensed:
            return T.CHUTE_OPENING_SENSED
        if self._not_sensed_alarm:
            return T.CHUTE_OPENING_NOT_SENSED_TIMEOUT
        return T.CHUTE_REQUESTED_AWAITING_OPENING

    def panel_status(self):
        return T.PANEL_UNKNOWN_NO_SENSOR

    def fault_mask(self):
        return self._faults

    def release_timer_start_ms(self):
        return self._release_ms

    def requests_emitted(self):
        return self._requests_emitted

    def pop_request(self):
        """Next queued ActuatorRequest code, or None."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    # ---- internals ----
    def _emit(self, t, now, detail):
        self._out.on_event(T.Event(t, now, detail))

    def _persist(self):
        ok = self._rec.persist(self._state, self._flags)
        if not ok:
            self._faults |= T.FAULT_PERSIST_WRITE
        return ok

    def start(self, r, now_ms):
        self._state = r.state
        self._flags = r.one_shot_flags
        self._release_ms = now_ms  # separation timer restarts after a reset (conservative)
        self._request_ms = now_ms
        if r.corrupt:
            self._faults |= T.FAULT_RECOVERY_RECORD_CORRUPT
        self._opening_sensed = self.chute_requested() and self._state >= T.STATE_PANEL_DEPLOY
        if r.resumed:
            self._emit(T.EV_RESET_RECOVERED, now_ms, self._state)
        if r.resumed and self.chute_requested():
            self._emit(T.EV_REQUEST_SUPPRESSED, now_ms, T.REQ_RELEASE_PARACHUTE)

    def _reject(self, to, now, cause):
        self._emit(T.EV_TRANSITION_REJECTED, now, (self._state << 16) | (to << 8) | cause)

    def _transition(self, to, now, cause):
        if not is_permitted(self._state, to):
            self._reject(to, now, cause)
            return False
        frm = self._state
        self._state = to
        self._persist()
        self._emit(T.EV_STATE_CHANGED, now, (frm << 8) | to)
        return True

    def on_event(self, e):
        now = e.t_ms
        t = e.type
        if t == T.EV_SELF_CHECK_PASS:
            self._transition(T.STATE_READY_ON_DRONE, now, t)
        elif t == T.EV_ASCENT_DETECTED:
            self._transition(T.STATE_ASCENT, now, t)
        elif t == T.EV_RELEASE_CANDIDATE:
            if self._state != T.STATE_RELEASE_DETECTED:  # already separated: nothing to do
                self._transition(T.STATE_RELEASE_DETECTED, now, t)
        elif t == T.EV_RELEASE_CONFIRMED:
            if self._flags & T.ONESHOT_RELEASE_CONFIRMED:
                return  # duplicate: release is latched once
            if self._state == T.STATE_ASCENT and not self._transition(T.STATE_RELEASE_DETECTED, now, t):
                return
            if not self._transition(T.STATE_PARACHUTE_DEPLOY, now, t):
                return
            self._release_ms = now
            self._flags |= T.ONESHOT_RELEASE_CONFIRMED
            self._persist()
        elif t == T.EV_CHUTE_OPEN_DETECTED:
            if self._state != T.STATE_PARACHUTE_DEPLOY or not self.chute_requested():
                self._reject(T.STATE_PANEL_DEPLOY, now, t)
                return
            self._opening_sensed = True
            self._transition(T.STATE_PANEL_DEPLOY, now, t)
        elif t == T.EV_DESCENT_CONFIRMED:
            self._transition(T.STATE_DESCENT, now, t)
        elif t == T.EV_TOUCHDOWN_DETECTED:
            self._transition(T.STATE_LANDED, now, t)
        elif t in (T.EV_RELEASE_SENSORS_ONLY, T.EV_RELEASE_UNCORROBORATED, T.EV_SWITCH_REVERTED):
            self._faults |= T.FAULT_RELEASE_DEGRADED
        elif t == T.EV_SELF_CHECK_FAIL:
            self._faults |= T.FAULT_SELF_CHECK | (e.detail & T.FAULT_PARAMS_INCOMPLETE)
        # other events are informational

    def _maybe_request_chute(self, now):
        if not (self._flags & T.ONESHOT_RELEASE_CONFIRMED) or self.chute_requested():
            return
        if u32_sub(now, self._release_ms) < self._min_sep:
            return
        # Persist the one-shot flag BEFORE queueing so a reset cannot cause a
        # second request. Behaviour when persisting fails: OD-067 (no default).
        self._flags |= T.ONESHOT_CHUTE_REQUESTED
        if not self._persist() and self._persist_policy == FP.PERSIST_WITHHOLD_UNTIL_PERSISTED:
            self._flags = u8(self._flags & ~T.ONESHOT_CHUTE_REQUESTED)  # retry next tick
            self._faults |= T.FAULT_REQUEST_WITHHELD
            if not self._withheld_reported:
                self._withheld_reported = True
                self._emit(T.EV_REQUEST_WITHHELD, now, T.REQ_RELEASE_PARACHUTE)
            return
        self._request_ms = now
        if len(self._queue) < QUEUE_CAP:
            self._queue.append(T.REQ_RELEASE_PARACHUTE)
        else:
            self._faults |= T.FAULT_REQUEST_QUEUE_FULL
        self._requests_emitted += 1
        self._emit(T.EV_REQUEST_EMITTED, now, T.REQ_RELEASE_PARACHUTE)

    def tick(self, now):
        """Request timing and alarms only - never a transition."""
        if not self._complete or self._state != T.STATE_PARACHUTE_DEPLOY:
            return
        self._maybe_request_chute(now)
        if (self.chute_requested() and not self._opening_sensed and not self._not_sensed_alarm and
                u32_sub(now, self._request_ms) >= self._chute_timeout):
            self._not_sensed_alarm = True
            self._faults |= T.FAULT_CHUTE_OPEN_NOT_SENSED
            self._emit(T.EV_CHUTE_OPEN_NOT_CONFIRMED, now, 0)
