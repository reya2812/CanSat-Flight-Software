# fsw_hook.py - plugs the flight software into the runner. [SIMULATED]
# (port of firmware/sim/FswHook.cpp). Actuator logic is DISABLED: requests are
# drained and written to the log as "REQUEST:<name>(NOT_EXECUTED)". No actuator
# interface is referenced here (scan rule).
from cansat.config import flight_params as FP
from cansat.core import types as T
from cansat.core.flight_software import BootReport, FlightSoftware
from cansat.mock.persistent_store import MockPersistentStore
from cansat.sim.runner import SimHook
from cansat.sim.scenario import STORE_FAULT_CORRUPT_RECORD, STORE_FAULT_ERASE_RECORD, store_fault_name


class FswStats:
    def __init__(self):
        self.states_entered = []
        self.final_state = T.STATE_POWER_ON_SELF_CHECK
        self.final_faults = 0
        self.requests = 0
        self.rejected_transitions = 0
        self.suppressed_requests = 0
        self.resets_recovered = 0
        self.sensors_only_events = 0
        self.release_confirmed = 0
        self.last_release_basis = 0
        self.chute_not_confirmed_alarms = 0
        self.corrupt_restarts = 0
        self.store_faults_applied = 0
        self.final_chute = T.CHUTE_NOT_REQUESTED
        self.timeline = []


class FlightSoftwareHook(SimHook):
    def __init__(self, params):
        self._params = params
        self.store = MockPersistentStore()
        self.fsw = None  # read-only use by the trace exporter; None while rebooting
        self._pending = ""
        self.stats = FswStats()
        self._store_faults = []
        self._resets_seen = 0
        self._store_note = ""

    def set_store_faults(self, faults):
        self._store_faults = list(faults)

    def extra_header(self):
        return ",fsw_state,fsw_chute,fsw_faults,fsw_events,fsw_requests"

    def banner_line(self):
        ok, p = self._params.interlock.stuck_switch_policy.get()
        return ("# flight software in the loop (Phase 2 step 3). ACTUATOR LOGIC DISABLED: "
                "requests are logged as NOT_EXECUTED. SYNTHETIC params; stuck-switch policy=" +
                FP.policy_name(p if ok else FP.POLICY_UNSET))

    def empty_columns(self):
        return ",,,,,"

    def on_boot(self, baro_ok, imu_ok, power_ok, uptime_ms):
        self.fsw = FlightSoftware(self._params, self.store)
        self.fsw.boot(BootReport(baro_ok, imu_ok, power_ok), uptime_ms)
        rr = self.fsw.restore()
        if not self.stats.states_entered or not rr.resumed:
            self.stats.states_entered.append(self.fsw.state())
        self._pending = self._drain_events()
        if rr.corrupt:
            self.stats.corrupt_restarts += 1
        note, self._store_note = self._store_note, ""
        return (note + "FSW_BOOT:" + ("resume=" if rr.resumed else "start=") + T.state_name(self.fsw.state()) +
                ("/record_corrupt" if rr.corrupt else ""))

    def on_reset(self):
        self.fsw = None
        for f in self._store_faults:
            if f.reset_index != self._resets_seen:
                continue
            if f.kind == STORE_FAULT_CORRUPT_RECORD:
                self.store.corrupt()
            if f.kind == STORE_FAULT_ERASE_RECORD:
                self.store.erase()
            self.stats.store_faults_applied += 1
            self._store_note += "STORE_FAULT:" + store_fault_name(f.kind) + "/"
        self._resets_seen += 1

    def _drain_events(self):
        out = []
        st = self.stats
        for e in self.fsw.events():
            t = e.type
            if t == T.EV_STATE_CHANGED:
                to = e.detail & 0xFF
                tok = "->" + T.state_name(to)
                st.states_entered.append(to)
            elif t == T.EV_TRANSITION_REJECTED:
                tok = "TransitionRejected:%s->%s(by %s)" % (
                    T.state_name((e.detail >> 16) & 0xFF), T.state_name((e.detail >> 8) & 0xFF),
                    T.event_name(e.detail & 0xFF))
                st.rejected_transitions += 1
            elif t == T.EV_REQUEST_SUPPRESSED:
                st.suppressed_requests += 1
                tok = "RequestSuppressed:ReleaseParachute(already requested before reset)"
            elif t == T.EV_RESET_RECOVERED:
                st.resets_recovered += 1
                tok = "ResetRecovered:" + T.state_name(e.detail)
            elif t == T.EV_RELEASE_SENSORS_ONLY:
                st.sensors_only_events += 1
                tok = "ReleaseSensorsOnly(switch still reads mounted)"
            elif t == T.EV_RELEASE_CONFIRMED:
                st.release_confirmed += 1
                st.last_release_basis = e.detail
                tok = "ReleaseConfirmed:basis=%d" % e.detail
            elif t == T.EV_CHUTE_OPEN_DETECTED:
                tok = "ChuteOpenSensed"
            elif t == T.EV_CHUTE_OPEN_NOT_CONFIRMED:
                st.chute_not_confirmed_alarms += 1
                tok = "ChuteOpenNotConfirmed(ALARM: no opening sensed; state unchanged)"
            elif t == T.EV_TOUCHDOWN_DETECTED:
                tok = ("TouchdownDetected(mount reads CLOSED)" if e.detail & T.TOUCHDOWN_MOUNT_READS_CLOSED
                       else "TouchdownDetected")
            elif t in (T.EV_SENSOR_FAULT, T.EV_SENSOR_RECOVERED, T.EV_SELF_CHECK_FAIL):
                tok = "%s:0x%X" % (T.event_name(t), e.detail)
            else:
                tok = T.event_name(t)
            out.append(tok)
        return ";".join(out)

    def on_tick(self, frame, uptime_ms):
        if self.fsw is None:
            return self.empty_columns()
        fs = self.fsw
        fs.tick(frame, uptime_ms)
        events = self._pending
        self._pending = ""
        now_events = self._drain_events()
        if events and now_events:
            events += ";"
        events += now_events
        reqs = []
        r = fs.pop_request()
        while r is not None:
            self.stats.requests += 1
            reqs.append("REQUEST:" + T.request_name(r) + "(NOT_EXECUTED)")
            r = fs.pop_request()
        requests = ";".join(reqs)
        st = self.stats
        st.final_state, st.final_faults, st.final_chute = fs.state(), fs.fault_mask(), fs.chute_status()
        cols = ",%s,%s,0x%05X," % (T.state_name(fs.state()), T.chute_name(fs.chute_status()), fs.fault_mask())
        if events or requests:
            st.timeline.append("uptime=%7d  " % uptime_ms + events + (" | " + requests if requests else ""))
        return cols + events + "," + requests


def format_fsw_stats(s):
    r = "# ----- flight software (SIMULATED; actuator logic disabled) -----\n# states:"
    for st in s.states_entered:
        r += " " + T.state_name(st)
    r += ("\n# final=%s chute=%s panels=UNKNOWN(no sensor) faults=0x%05X requests(NOT executed)=%d "
          "suppressed=%d rejected_transitions=%d resets_recovered=%d sensors_only=%d "
          "release_confirmed=%d basis=%d chute_not_confirmed_alarms=%d store_faults=%d "
          "corrupt_restarts=%d\n" % (
              T.state_name(s.final_state), T.chute_name(s.final_chute), s.final_faults, s.requests,
              s.suppressed_requests, s.rejected_transitions, s.resets_recovered, s.sensors_only_events,
              s.release_confirmed, s.last_release_basis, s.chute_not_confirmed_alarms,
              s.store_faults_applied, s.corrupt_restarts))
    r += "# flight-software timeline:\n"
    for line in s.timeline:
        r += "#   " + line + "\n"
    return r
