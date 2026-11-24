# synthetic_flight_params.py - SYNTHETIC parameter sets for simulation/tests ONLY.
# (port of firmware/sim/scenarios/SyntheticFlightParams.cpp, same values)
#
# !!! EVERY VALUE IN THIS FILE IS SYNTHETIC !!!
# Chosen only so the SYNTHETIC scenarios exercise each code path. Not derived
# from test data and NOT candidate flight values (OD-057, OD-060).
from cansat.config import flight_params as FP

SYNTHETIC_DEBOUNCE_MS = 100
SYNTHETIC_SWITCH_OPEN_IS_HIGH = True  # matches the SYNTHETIC mock wiring (closed = LOW)
SYNTHETIC_FREEFALL_MAX_G = 0.3
SYNTHETIC_FREEFALL_MIN_MS = 150
SYNTHETIC_BARO_MIN_DROP_M = 1.0
SYNTHETIC_BARO_WINDOW_MS = 500
SYNTHETIC_CONFIRM_WINDOW_MS = 1000
SYNTHETIC_STALE_MS = 200
SYNTHETIC_MIN_SEPARATION_MS = 300
SYNTHETIC_FALLBACK_DELAY_MS = 300
SYNTHETIC_SELFCHECK_SAMPLES = 10
SYNTHETIC_SELFCHECK_REQUIRE_POWER = False
SYNTHETIC_ASCENT_GAIN_M = 20.0
SYNTHETIC_ASCENT_CONFIRM_MS = 500
SYNTHETIC_CHUTE_OPEN_G = 3.0
SYNTHETIC_CHUTE_TIMEOUT_MS = 3000
SYNTHETIC_DESCENT_CONFIRM_MS = 1000
SYNTHETIC_LANDED_MAX_ALT_ABOVE_GROUND_M = 5.0
SYNTHETIC_IMU_STUCK_IDENTICAL_SAMPLES = 5
# The store never fails in the scenarios, so this has no effect there; unit tests
# exercise BOTH persist-failure policies explicitly (OD-067 undecided).
SYNTHETIC_SCENARIO_PERSIST_POLICY = FP.PERSIST_REQUEST_ANYWAY
SYNTHETIC_LANDED_WINDOW_MS = 3000
SYNTHETIC_LANDED_MAX_ALT_CHANGE_M = 2.0
SYNTHETIC_LANDED_ACCEL_TOL_G = 0.3

CANDIDATE_POLICIES = (FP.POLICY_STRICT_SWITCH_VETO, FP.POLICY_SENSOR_OVERRIDE,
                      FP.POLICY_VOTE_2_OF_3, FP.POLICY_DELAYED_FALLBACK)


def synthetic_flight_params(policy):
    p = FP.FlightParams()
    r, i, t = p.release, p.interlock, p.transitions
    r.switch_debounce_ms.set(SYNTHETIC_DEBOUNCE_MS)
    r.switch1_open_is_high.set(SYNTHETIC_SWITCH_OPEN_IS_HIGH)
    r.switch2_open_is_high.set(SYNTHETIC_SWITCH_OPEN_IS_HIGH)
    r.switch_vote.set(FP.SWITCH_VOTE_ANY)
    r.freefall_accel_max_g.set(SYNTHETIC_FREEFALL_MAX_G)
    r.freefall_min_ms.set(SYNTHETIC_FREEFALL_MIN_MS)
    r.baro_min_drop_m.set(SYNTHETIC_BARO_MIN_DROP_M)
    r.baro_window_ms.set(SYNTHETIC_BARO_WINDOW_MS)
    r.confirm_window_ms.set(SYNTHETIC_CONFIRM_WINDOW_MS)
    r.sample_stale_ms.set(SYNTHETIC_STALE_MS)
    i.min_separation_ms.set(SYNTHETIC_MIN_SEPARATION_MS)
    i.stuck_switch_policy.set(policy)
    i.fallback_delay_ms.set(SYNTHETIC_FALLBACK_DELAY_MS)
    t.selfcheck_samples.set(SYNTHETIC_SELFCHECK_SAMPLES)
    t.selfcheck_require_power.set(SYNTHETIC_SELFCHECK_REQUIRE_POWER)
    t.ascent_min_gain_m.set(SYNTHETIC_ASCENT_GAIN_M)
    t.ascent_confirm_ms.set(SYNTHETIC_ASCENT_CONFIRM_MS)
    t.chute_open_accel_min_g.set(SYNTHETIC_CHUTE_OPEN_G)
    t.chute_open_timeout_ms.set(SYNTHETIC_CHUTE_TIMEOUT_MS)
    t.descent_confirm_ms.set(SYNTHETIC_DESCENT_CONFIRM_MS)
    t.landed_max_alt_above_ground_m.set(SYNTHETIC_LANDED_MAX_ALT_ABOVE_GROUND_M)
    p.validation.imu_stuck_identical_samples.set(SYNTHETIC_IMU_STUCK_IDENTICAL_SAMPLES)
    i.persist_failure_policy.set(SYNTHETIC_SCENARIO_PERSIST_POLICY)
    t.landed_window_ms.set(SYNTHETIC_LANDED_WINDOW_MS)
    t.landed_max_alt_change_m.set(SYNTHETIC_LANDED_MAX_ALT_CHANGE_M)
    t.landed_accel_tol_g.set(SYNTHETIC_LANDED_ACCEL_TOL_G)
    return p
