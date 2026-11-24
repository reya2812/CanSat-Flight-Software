# flight_software.py - composition of the flight logic for one boot.
# (port of lib/core/FlightSoftware.h/.cpp)
#
#   SensorFrame -> SensorValidator -> EventDetector -> events -> FlightStateManager
#                                                              -> ActuatorRequest queue
# The request queue is exposed for logging only; nothing actuates (D-017).
# A reset is modelled by discarding this object and constructing a new one
# with the same PersistentStore (RAM lost, persisted record kept).
from cansat.core import types as T
from cansat.core.event_detector import EventDetector
from cansat.core.flight_state_manager import FlightStateManager
from cansat.core.recovery_manager import RecoveryManager, RestoreResult
from cansat.core.sensor_validator import SensorValidator
from cansat.hal.interfaces import EventSink

MAX_EVENTS_PER_TICK = 32


class BootReport:
    """Sensor initialisation results (bus response, chip identity, config read-back
    on hardware). [TBD] No physical driver exists yet (OD-066)."""

    def __init__(self, baro_ok=False, imu_ok=False, power_ok=False, imu_self_test=T.SELF_TEST_NOT_RUN):
        self.baro_ok = baro_ok
        self.imu_ok = imu_ok
        self.power_ok = power_ok
        self.imu_self_test = imu_self_test


class _Recorder(EventSink):
    def __init__(self, fs, forward):
        self._fs = fs
        self._forward = forward  # detector events are forwarded to the state machine

    def on_event(self, e):
        self._fs._record(e)
        if self._forward:
            self._fs._fsm.on_event(e)


class FlightSoftware:
    def __init__(self, params, store):
        self._params = params
        self._recovery = RecoveryManager(store)
        self._detector_sink = _Recorder(self, True)
        self._fsm_sink = _Recorder(self, False)
        self._validator = SensorValidator(params)
        self._detector = EventDetector(params, self._detector_sink)
        self._fsm = FlightStateManager(params, self._recovery, self._fsm_sink)
        self._restore = RestoreResult()
        self._boot_faults = 0
        self._events = []
        self._dropped_events = 0

    def _record(self, e):
        if len(self._events) < MAX_EVENTS_PER_TICK:
            self._events.append(e)
        else:
            self._dropped_events += 1

    # ---- accessors ----
    def state(self):
        return self._fsm.state()

    def fault_mask(self):
        return (self._validator.fault_mask() | self._fsm.fault_mask() | self._detector.fault_mask() |
                self._boot_faults)

    def restore(self):
        return self._restore

    def pop_request(self):
        return self._fsm.pop_request()

    def requests_emitted(self):
        return self._fsm.requests_emitted()

    def chute_status(self):
        return self._fsm.chute_status()

    def fsm(self):
        return self._fsm

    def detector(self):
        return self._detector

    def events(self):
        """Events produced during the last boot()/tick() (detector + state machine), in order."""
        return self._events

    def dropped_events(self):
        return self._dropped_events

    # ---- lifecycle ----
    def boot(self, report, now_ms):
        self._events = []
        self._restore = self._recovery.restore_on_boot()
        if self._restore.has_ground:
            self._detector.restore_ground_reference(self._restore.ground_pressure_pa)
            self._recovery.set_ground_pressure(self._restore.ground_pressure_pa)
        self._fsm.start(self._restore, now_ms)

        if not report.baro_ok:
            self._boot_faults |= T.FAULT_BARO_INVALID
        if not report.imu_ok:
            self._boot_faults |= T.FAULT_IMU_INVALID
        if not report.power_ok:
            self._boot_faults |= T.FAULT_POWER_INVALID
        # MPU6050 self-test (OD-066): FAILED blocks self-check; NOT RUN is reported
        # but does not block (no driver can run it yet). Provisional.
        if report.imu_self_test == T.SELF_TEST_NOT_RUN:
            self._boot_faults |= T.FAULT_IMU_SELF_TEST_NOT_RUN
        if report.imu_self_test == T.SELF_TEST_FAILED:
            self._boot_faults |= T.FAULT_IMU_SELF_TEST_FAILED
        if not report.baro_ok or not report.imu_ok or report.imu_self_test == T.SELF_TEST_FAILED:
            self._boot_faults |= T.FAULT_SELF_CHECK
            self._detector_sink.on_event(T.Event(T.EV_SELF_CHECK_FAIL, now_ms, self._boot_faults))
        if not self._params.is_complete():
            self._boot_faults |= T.FAULT_PARAMS_INCOMPLETE

    def tick(self, frame, now_ms):
        self._events = []
        v = self._validator.validate(frame, now_ms)
        nf = self._validator.newly_faulted()
        nr = self._validator.newly_recovered()
        bit = 1
        while bit <= 0x80000000:
            if nf & bit:
                self._record(T.Event(T.EV_SENSOR_FAULT, now_ms, bit))
            if nr & bit:
                self._record(T.Event(T.EV_SENSOR_RECOVERED, now_ms, bit))
            bit <<= 1
        # A sensor that failed begin() stays failed until the next boot.
        init_blocked = (self._boot_faults & T.FAULT_SELF_CHECK) != 0
        if not (init_blocked and self._fsm.state() == T.STATE_POWER_ON_SELF_CHECK):
            self._detector.update(v, self._fsm.state(), self._fsm.chute_requested())
        if self._detector.has_ground_reference():
            self._recovery.set_ground_pressure(self._detector.ground_pressure_pa())
        self._fsm.tick(now_ms)
