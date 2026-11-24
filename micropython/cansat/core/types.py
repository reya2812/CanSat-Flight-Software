# types.py - common data types shared by all modules.  (port of lib/core/Types.h)
#
# Portable: no enum / dataclasses / typing (D-017). Enumerations are integer
# constants with the SAME numeric codes as the C++ reference, so parity traces
# compare numbers directly. Codes are appended, never renumbered.
#
# State / event / command separation (Phase 1 hard constraint):
#   FlightState      - where the mission is.
#   Event            - something detected (by sensors, logic or reset).
#   ActuatorRequest  - something the state machine would LIKE done.
#   ActuatorDecision - what ActuatorManager actually decided. Entering a
#                      deployment-related state never actuates anything by itself.

# ---------------- Flight states ([PDR] slide 19, numbered 01-08) ----------------
STATE_POWER_ON_SELF_CHECK = 1
STATE_READY_ON_DRONE = 2
STATE_ASCENT = 3
STATE_RELEASE_DETECTED = 4
STATE_PARACHUTE_DEPLOY = 5
STATE_PANEL_DEPLOY = 6
STATE_DESCENT = 7
STATE_LANDED = 8
FLIGHT_STATE_COUNT = 8

_STATE_NAMES = {
    1: "POWER_ON_SELF_CHECK", 2: "READY_ON_DRONE", 3: "ASCENT", 4: "RELEASE_DETECTED",
    5: "PARACHUTE_DEPLOY", 6: "PANEL_DEPLOY", 7: "DESCENT", 8: "LANDED",
}


def state_name(s):
    return _STATE_NAMES.get(s, "INVALID")


def is_valid_flight_state_code(code):
    return isinstance(code, int) and 1 <= code <= FLIGHT_STATE_COUNT


# ---------------- Sensor samples ----------------
# `valid` = the driver produced a trustworthy reading. Consumers must check
# `valid` and sample age; invalid samples are never silently used (SW-12).
# comm_ok    - the bus transaction(s) completed (I2C ACK, expected byte count).
# data_ready - the chip's own status says this is a NEW conversion.
# Floats are stored as Python floats; drivers and mocks round them with
# num.f32() where C++ parity matters.

class BaroSample:
    def __init__(self):
        self.t_ms = 0
        self.pressure_pa = 0.0
        self.temp_c = 0.0
        self.valid = False
        self.comm_ok = False
        self.data_ready = False


class ImuSample:
    def __init__(self):
        self.t_ms = 0
        self.ax_g = 0.0
        self.ay_g = 0.0
        self.az_g = 0.0
        self.gx_dps = 0.0
        self.gy_dps = 0.0
        self.gz_dps = 0.0
        self.valid = False
        self.saturated = False  # any accel axis at full scale; never report as a peak
        self.comm_ok = False
        self.data_ready = False


SELF_TEST_NOT_RUN = 0
SELF_TEST_PASSED = 1
SELF_TEST_FAILED = 2


class PowerSample:
    def __init__(self):
        self.t_ms = 0
        self.bus_v = 0.0       # [TBD] which rail (OD-014, OD-053)
        self.current_ma = 0.0  # [TBD] which rail
        self.valid = False
        self.comm_ok = False
        self.data_ready = False


SWITCH_COUNT = 2  # [UNVERIFIED] two limit switches; roles TBD (OD-015)


class SwitchSample:
    def __init__(self):
        self.t_ms = 0
        self.raw = [False, False]  # electrical level; polarity TBD (OD-051)
        self.valid = False


class SensorFrame:
    def __init__(self):
        self.baro = BaroSample()
        self.imu = ImuSample()
        self.power = PowerSample()
        self.switches = SwitchSample()


# ---------------- Events ----------------
EV_SELF_CHECK_PASS = 1
EV_SELF_CHECK_FAIL = 2
EV_ASCENT_DETECTED = 3
EV_RELEASE_CANDIDATE = 4
EV_RELEASE_CONFIRMED = 5
EV_RELEASE_UNCORROBORATED = 6
EV_RELEASE_SENSORS_ONLY = 7   # switch still "mounted" but sensors indicate release (OD-060)
EV_SWITCH_REVERTED = 8
EV_CHUTE_OPEN_DETECTED = 9
EV_PANELS_OUT_DETECTED = 10
EV_TOUCHDOWN_DETECTED = 11
EV_SENSOR_FAULT = 12
EV_RESET_RECOVERED = 13
EV_ACTUATOR_DECIDED = 14      # detail: bits 0-15 InterlockReason, 16-23 decision, 24-30 request, 31 phase
EV_STATE_CHANGED = 15         # detail = (from << 8) | to
EV_TRANSITION_REJECTED = 16   # detail = (from << 16) | (to << 8) | triggering event type
EV_REQUEST_EMITTED = 17       # detail = ActuatorRequest (a REQUEST only; nothing is actuated)
EV_REQUEST_SUPPRESSED = 18    # duplicate one-shot request blocked; detail = ActuatorRequest
EV_SENSOR_RECOVERED = 19      # detail = fault bit that cleared
EV_DESCENT_CONFIRMED = 20
EV_CHUTE_OPEN_NOT_CONFIRMED = 21  # alarm only, no transition
EV_REQUEST_WITHHELD = 22      # one-shot flag could not be persisted

_EVENT_NAMES = {
    1: "SelfCheckPass", 2: "SelfCheckFail", 3: "AscentDetected", 4: "ReleaseCandidate",
    5: "ReleaseConfirmed", 6: "ReleaseUncorroborated", 7: "ReleaseSensorsOnly",
    8: "SwitchReverted", 9: "ChuteOpenDetected", 10: "PanelsOutDetected",
    11: "TouchdownDetected", 12: "SensorFault", 13: "ResetRecovered", 14: "ActuatorDecided",
    15: "StateChanged", 16: "TransitionRejected", 17: "RequestEmitted",
    18: "RequestSuppressed", 19: "SensorRecovered", 20: "DescentConfirmed",
    21: "ChuteOpenNotConfirmed", 22: "RequestWithheld",
}


def event_name(t):
    return _EVENT_NAMES.get(t, "?")


# ReleaseConfirmed detail: which evidence confirmed release.
BASIS_SWITCH_AND_FREEFALL = 1
BASIS_SWITCH_AND_BARO = 2
BASIS_SWITCH_FREEFALL_BARO = 3
BASIS_SENSORS_ONLY_POLICY = 4  # accepted by StuckSwitchPolicy (OD-060)

TOUCHDOWN_MOUNT_READS_CLOSED = 1 << 0


class Event:
    def __init__(self, type_=EV_SENSOR_FAULT, t_ms=0, detail=0):
        self.type = type_
        self.t_ms = t_ms
        self.detail = detail


# ---------------- Parachute / panel status ----------------
CHUTE_NOT_REQUESTED = 0
CHUTE_REQUESTED_AWAITING_OPENING = 1
CHUTE_OPENING_SENSED = 2
CHUTE_OPENING_NOT_SENSED_TIMEOUT = 3
_CHUTE_NAMES = {0: "NOT_REQUESTED", 1: "REQUESTED_AWAITING_OPENING", 2: "OPENING_SENSED",
                3: "OPENING_NOT_SENSED"}


def chute_name(c):
    return _CHUTE_NAMES.get(c, "?")


PANEL_UNKNOWN_NO_SENSOR = 0  # panels have no sensor (OD-037)

# ---------------- Requests and decisions ----------------
REQ_RELEASE_PARACHUTE = 1
REQ_DEPLOY_PANELS = 2  # only meaningful if a solar servo exists (OD-037, H2)
REQ_BUZZER_ON = 3
REQ_BUZZER_OFF = 4
_REQ_NAMES = {1: "ReleaseParachute", 2: "DeployPanels", 3: "BuzzerOn", 4: "BuzzerOff"}


def request_name(r):
    return _REQ_NAMES.get(r, "?")


DEC_EXECUTED_SIMULATED = 1
DEC_BLOCKED_BUILD_DISABLED = 2
DEC_BLOCKED_NOT_ARMED = 3
DEC_BLOCKED_INTERLOCK_MOUNTED = 4
DEC_BLOCKED_ALREADY_DONE = 5
DEC_BLOCKED_BUSY = 6
DEC_BLOCKED_PARAMS_INCOMPLETE = 7
DEC_BLOCKED_WRONG_STATE = 8
DEC_BLOCKED_RELEASE_NOT_CONFIRMED = 9
DEC_BLOCKED_SEPARATION_DELAY = 10
DEC_BLOCKED_CONNECTION_UNAVAILABLE = 11
DEC_BLOCKED_CONNECTION_INVALID = 12
DEC_BLOCKED_CONNECTION_INDETERMINATE = 13
DEC_BLOCKED_CONNECTION_STALE = 14
DEC_BLOCKED_NOT_AUTHORIZED = 15
DEC_BLOCKED_STALE_AUTHORIZATION = 16
DEC_BLOCKED_UNSUPPORTED_REQUEST = 17
DEC_AUTHORIZED_PENDING_EXECUTION = 18
_DEC_NAMES = {
    1: "ExecutedSimulated", 2: "BlockedBuildDisabled", 3: "BlockedNotArmed",
    4: "BlockedInterlockMounted", 5: "BlockedAlreadyDone", 6: "BlockedBusy",
    7: "BlockedParamsIncomplete", 8: "BlockedWrongState", 9: "BlockedReleaseNotConfirmed",
    10: "BlockedSeparationDelay", 11: "BlockedConnectionUnavailable",
    12: "BlockedConnectionInvalid", 13: "BlockedConnectionIndeterminate",
    14: "BlockedConnectionStale", 15: "BlockedNotAuthorized", 16: "BlockedStaleAuthorization",
    17: "BlockedUnsupportedRequest", 18: "AuthorizedPendingExecution",
}


def decision_name(d):
    return _DEC_NAMES.get(d, "?")


# ---------------- Deployment-interlock inputs (OD-070; mock-only) ----------------
# HOW a connection assessment is formed is UNRESOLVED (OD-060, OD-068, A1-A5).
CONN_UNAVAILABLE = 0
CONN_INVALID = 1
CONN_INDETERMINATE = 2
CONN_CONNECTED = 3
CONN_SEPARATED = 4


class ConnectionAssessmentSample:
    def __init__(self, value=CONN_UNAVAILABLE, t_ms=0, provenance=0):
        self.value = value
        self.t_ms = t_ms
        self.provenance = provenance  # opaque tag; never interpreted by core code


ARM_UNKNOWN = 0
ARM_DISARMED = 1
ARM_ARMED = 2


class ArmingSample:
    def __init__(self, state=ARM_UNKNOWN, t_ms=0):
        self.state = state
        self.t_ms = t_ms


IL_PARAMS_INCOMPLETE = 1 << 0
IL_UNSUPPORTED_REQUEST = 1 << 1
IL_WRONG_STATE = 1 << 2
IL_RELEASE_NOT_CONFIRMED = 1 << 3
IL_ALREADY_DONE = 1 << 4
IL_SEPARATION_DELAY = 1 << 5
IL_ARM_UNKNOWN = 1 << 6
IL_NOT_ARMED = 1 << 7
IL_CONN_UNAVAILABLE = 1 << 8
IL_CONN_INVALID = 1 << 9
IL_CONN_INDETERMINATE = 1 << 10
IL_CONN_CONNECTED = 1 << 11
IL_CONN_STALE = 1 << 12
IL_CONN_FUTURE_TIMESTAMP = 1 << 13
IL_PHYSICAL_DRIVER_REFUSED = 1 << 14

# ---------------- Faults (bitmask) ----------------
FAULT_BARO_INVALID = 1 << 0
FAULT_IMU_INVALID = 1 << 1
FAULT_POWER_INVALID = 1 << 2
FAULT_SWITCH_INVALID = 1 << 3
FAULT_IMU_SATURATED = 1 << 4
FAULT_LOG_WRITE = 1 << 5
FAULT_PERSIST_WRITE = 1 << 6
FAULT_RECOVERY_RECORD_CORRUPT = 1 << 7
FAULT_SELF_CHECK = 1 << 8
FAULT_RELEASE_DEGRADED = 1 << 9
FAULT_PARAMS_INCOMPLETE = 1 << 10
FAULT_LOW_BATTERY = 1 << 11           # threshold [TBD]; not chosen by software
FAULT_CHUTE_OPEN_NOT_SENSED = 1 << 12
FAULT_REQUEST_QUEUE_FULL = 1 << 13
FAULT_IMU_SELF_TEST_NOT_RUN = 1 << 14
FAULT_IMU_SELF_TEST_FAILED = 1 << 15
FAULT_LANDING_UNCONFIRMABLE = 1 << 16
FAULT_REQUEST_WITHHELD = 1 << 17
FAULT_LANDED_MOUNT_CLOSED = 1 << 18
# The fault schema is exactly the C++ FaultBit set (bits 0-18). No port-only bit
# is defined: how an unhandled exception is reported is undecided (OD-072).

# ---------------- Reset-recovery record ----------------
ONESHOT_RELEASE_CONFIRMED = 1 << 0
ONESHOT_CHUTE_REQUESTED = 1 << 1
ONESHOT_CHUTE_DECIDED = 1 << 2


class RecoveryRecord:
    # Field widths follow the C++ struct (uint32 magic, uint16 version,
    # uint16 boot_count, uint8 last_state, uint8 one_shot_flags, uint32
    # t_release_ms, float ground_pressure_pa, uint32 crc). Serialisation and
    # CRC are ported with RecoveryManager (module 2).
    def __init__(self):
        self.magic = 0
        self.version = 0
        self.boot_count = 0
        self.last_state = 0
        self.one_shot_flags = 0
        self.t_release_ms = 0
        self.ground_pressure_pa = 0.0
        self.crc = 0
