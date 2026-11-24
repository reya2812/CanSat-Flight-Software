# flight_params.py - flight thresholds, timings and safety policies.
# (port of include/config/FlightParams.h)
#
# [TBD] Every value here is undecided (OD-057, OD-060). None has a default.
# Values must come from test data plus team approval. Tests and simulation may
# set them only with constants named SYNTHETIC_*, which live under tests/ or
# sim/ and are never copied into firmware defaults.
#
# WEAKER THAN C++: C++ refuses to compile a hardware build unless
# CANSAT_FLIGHT_PARAMS_APPROVED is defined. Here boot_checks refuses to start
# on hardware while build_flags.FLIGHT_PARAMS_APPROVED is False.
from cansat.core.param import Param, KIND_U32, KIND_BOOL, KIND_FLOAT, KIND_ENUM

# How the two limit switches combine into "mount open". [TBD] OD-015.
SWITCH_VOTE_UNSET = 0
SWITCH_VOTE_ANY = 1       # either switch open
SWITCH_VOTE_ALL = 2       # both switches open
SWITCH_VOTE_SW1_ONLY = 3  # second switch has another role

# Stuck-switch policy candidates (docs/OPEN_DECISIONS.md section H).
# [TBD] OD-060 - CRITICAL, undecided. No default; Unset is never valid.
POLICY_UNSET = 0
POLICY_STRICT_SWITCH_VETO = 1  # P-A
POLICY_SENSOR_OVERRIDE = 2     # P-B
POLICY_VOTE_2_OF_3 = 3         # P-C
POLICY_DELAYED_FALLBACK = 4    # P-G
_POLICY_NAMES = {0: "Unset", 1: "P-A_StrictSwitchVeto", 2: "P-B_SensorOverride",
                 3: "P-C_Vote2of3", 4: "P-G_DelayedFallback"}


def policy_name(p):
    return _POLICY_NAMES.get(p, "?")


# What to do when the parachute-request one-shot flag cannot be persisted
# (OD-067, undecided - no default).
PERSIST_UNSET = 0
PERSIST_REQUEST_ANYWAY = 1           # queue once; a reset may then lead to a SECOND request
PERSIST_WITHHOLD_UNTIL_PERSISTED = 2  # retry each tick; no request while storage fails
_PERSIST_NAMES = {0: "Unset", 1: "RequestAnyway", 2: "WithholdUntilPersisted"}


def persist_policy_name(p):
    return _PERSIST_NAMES.get(p, "?")


def _enum_set_and_not_unset(param):
    ok, v = param.get()
    return ok and v != 0


class ValidationParams:
    """Sensor-health parameters for the validator. All [TBD] (OD-066)."""

    def __init__(self):
        # Consecutive IMU samples with all six raw values identical that mark the
        # output as stuck. Relies on real sensor noise ([ASSUMPTION], needs bench data).
        self.imu_stuck_identical_samples = Param(KIND_U32)

    def is_complete(self):
        return self.imu_stuck_identical_samples.is_set()


class ReleaseParams:
    """Release-detection parameters (docs/PHASE1_PROPOSAL.md section 3.2). All [TBD]."""

    def __init__(self):
        self.switch_debounce_ms = Param(KIND_U32)     # T_DB_SW
        self.switch1_open_is_high = Param(KIND_BOOL)  # SW_POLARITY[0] (wiring, OD-051)
        self.switch2_open_is_high = Param(KIND_BOOL)  # SW_POLARITY[1] (wiring, OD-051)
        self.switch_vote = Param(KIND_ENUM)           # SW_VOTE
        self.freefall_accel_max_g = Param(KIND_FLOAT)  # A_FF
        self.freefall_min_ms = Param(KIND_U32)        # T_FF
        self.baro_min_drop_m = Param(KIND_FLOAT)      # DH_MIN
        self.baro_window_ms = Param(KIND_U32)         # W_B
        self.confirm_window_ms = Param(KIND_U32)      # T_CONFIRM
        self.sample_stale_ms = Param(KIND_U32)        # T_STALE

    def is_complete(self):
        return (self.switch_debounce_ms.is_set() and self.switch1_open_is_high.is_set() and
                self.switch2_open_is_high.is_set() and _enum_set_and_not_unset(self.switch_vote) and
                self.freefall_accel_max_g.is_set() and self.freefall_min_ms.is_set() and
                self.baro_min_drop_m.is_set() and self.baro_window_ms.is_set() and
                self.confirm_window_ms.is_set() and self.sample_stale_ms.is_set())


class InterlockParams:
    """Parachute-request interlock parameters. All [TBD]."""

    def __init__(self):
        self.min_separation_ms = Param(KIND_U32)       # T_SEP_MIN [PDR] slide 10; value TBD (H4)
        self.stuck_switch_policy = Param(KIND_ENUM)    # OD-060
        self.fallback_delay_ms = Param(KIND_U32)       # T_FALLBACK; only for DelayedFallback
        self.persist_failure_policy = Param(KIND_ENUM)  # OD-067

    def is_complete(self):
        if not self.min_separation_ms.is_set() or not _enum_set_and_not_unset(self.stuck_switch_policy):
            return False
        if not _enum_set_and_not_unset(self.persist_failure_policy):
            return False
        p = self.stuck_switch_policy.require()  # set: checked just above
        if p == POLICY_DELAYED_FALLBACK and not self.fallback_delay_ms.is_set():
            return False
        return True


class TransitionParams:
    """Non-release state-transition parameters. All [TBD] (MEETING_BRIEF G1)."""

    def __init__(self):
        self.selfcheck_samples = Param(KIND_U32)
        self.selfcheck_require_power = Param(KIND_BOOL)
        self.ascent_min_gain_m = Param(KIND_FLOAT)
        self.ascent_confirm_ms = Param(KIND_U32)
        self.chute_open_accel_min_g = Param(KIND_FLOAT)
        self.chute_open_timeout_ms = Param(KIND_U32)   # ALARM ONLY; never a transition
        self.descent_confirm_ms = Param(KIND_U32)
        self.landed_window_ms = Param(KIND_U32)
        self.landed_max_alt_change_m = Param(KIND_FLOAT)
        self.landed_accel_tol_g = Param(KIND_FLOAT)
        self.landed_max_alt_above_ground_m = Param(KIND_FLOAT)

    def is_complete(self):
        return (self.selfcheck_samples.is_set() and self.selfcheck_require_power.is_set() and
                self.ascent_min_gain_m.is_set() and self.ascent_confirm_ms.is_set() and
                self.chute_open_accel_min_g.is_set() and self.chute_open_timeout_ms.is_set() and
                self.descent_confirm_ms.is_set() and self.landed_window_ms.is_set() and
                self.landed_max_alt_change_m.is_set() and self.landed_accel_tol_g.is_set() and
                self.landed_max_alt_above_ground_m.is_set())


class DeploymentInterlockParams:
    """Downstream deployment-interlock parameters (OD-070). All [TBD].

    Deliberately NOT part of FlightParams.is_complete(), as in C++.
    """

    def __init__(self):
        self.connection_max_age_ms = Param(KIND_U32)

    def is_complete(self):
        return self.connection_max_age_ms.is_set()


class FlightParams:
    def __init__(self):
        self.release = ReleaseParams()
        self.interlock = InterlockParams()
        self.transitions = TransitionParams()
        self.validation = ValidationParams()

    def is_complete(self):
        return (self.release.is_complete() and self.interlock.is_complete() and
                self.transitions.is_complete() and self.validation.is_complete())
