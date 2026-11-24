# scenarios.py - scripted flights for software testing only. [SIMULATED]
# (port of firmware/sim/scenarios/SyntheticScenarios.cpp; same 13 + 4 scenarios, same values)
#
# !!! EVERY NUMBER IN THIS FILE IS SYNTHETIC !!!
# Picked to exercise code paths (loosely like the PDR's 100 m drop). NOT flight
# thresholds, timings, sensor characteristics or measurements. Never copy them
# into firmware configuration; scan_guards.py enforces the SYNTHETIC_ prefix rule.
from cansat.core.num import f32
from cansat.mock import fault_injector as FI
from cansat.mock.fault_injector import FaultWindow
from cansat.mock.sensors import SensorNoise
from cansat.sim.flight_profile import FlightProfile
from cansat.sim.scenario import (Marker, Scenario, Segment, StoreFaultAtReset,
                                 STORE_FAULT_CORRUPT_RECORD, STORE_FAULT_ERASE_RECORD)

# ---- Simulation settings (SYNTHETIC) ----
SYNTHETIC_TICK_MS = 50
SYNTHETIC_REBOOT_MS = 400
SYNTHETIC_TAIL_MS = 2000
SYNTHETIC_GROUND_PRESSURE_PA = 101325.0
SYNTHETIC_TEMP_C = 25.0
SYNTHETIC_BUS_V = 3.90
SYNTHETIC_CURRENT_MA = 150.0
SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH = False  # wiring is TBD (OD-051)
# ---- Noise (SYNTHETIC) ----
SYNTHETIC_NOISE_PRESSURE_PA = 3.0
SYNTHETIC_NOISE_TEMP_C = 0.05
SYNTHETIC_NOISE_ACCEL_G = 0.02
SYNTHETIC_NOISE_GYRO_DPS = 0.5
SYNTHETIC_NOISE_BUS_V = 0.01
SYNTHETIC_NOISE_CURRENT_MA = 2.0
# ---- Trajectory (SYNTHETIC) ----
SYNTHETIC_GROUND_MS = 3000
SYNTHETIC_ASCENT_MS = 20000
SYNTHETIC_ASCENT_VZ = 5.0
SYNTHETIC_HOLD_MS = 3000
SYNTHETIC_FREEFALL_MS = 1500
SYNTHETIC_FREEFALL_AZ = -9.0
SYNTHETIC_FREEFALL_ACCEL_G = 0.08
SYNTHETIC_CHUTE_OPEN_MS = 200
SYNTHETIC_CHUTE_OPEN_AZ = 50.0
SYNTHETIC_CHUTE_SHOCK_G = 20.0  # > 16 g on purpose: demonstrates clipping
SYNTHETIC_DESCENT_VZ = -3.0
SYNTHETIC_SWING_DPS = 5.0
SYNTHETIC_IMPACT_MS = 100
SYNTHETIC_IMPACT_G = 6.0
SYNTHETIC_LANDED_MS = 5000
SYNTHETIC_DRONE_FAST_DESCENT_MS = 8000
SYNTHETIC_DRONE_FAST_DESCENT_VZ = -6.0
SYNTHETIC_DRONE_DROP_MS = 2000
SYNTHETIC_DRONE_RECOVER_G = 1.9
# ---- Fault parameters (SYNTHETIC) ----
SYNTHETIC_BARO_DROPOUT_DELAY_MS = 5000
SYNTHETIC_BARO_DROPOUT_MS = 3000
SYNTHETIC_STALE_LEAD_MS = 500
SYNTHETIC_STALE_MS = 2000
SYNTHETIC_EXTRA_NOISE_PA = 40.0
SYNTHETIC_EXTRA_NOISE_G = 0.3
SYNTHETIC_INVALID_MS = 1000
SYNTHETIC_OUT_OF_RANGE_MA = 99999.0
SYNTHETIC_BOUNCE_PERIOD1_MS = 30.0
SYNTHETIC_BOUNCE_PERIOD2_MS = 70.0
SYNTHETIC_BOUNCE_WINDOW_MS = 400
SYNTHETIC_RESET_DELAY_1_MS = 500
SYNTHETIC_RESET_DELAY_2_MS = 4000
SYNTHETIC_NOT_DETECTED_MS = 500
SYNTHETIC_RESET_IN_ASCENT_MS = 10000
SYNTHETIC_RESET_BEFORE_REQUEST_MS = 200
SYNTHETIC_INVALID_DELAY_MS = 2000
SYNTHETIC_SEED = 12345
SYNTHETIC_CHUTE_SHOCK_X_G = 0.5
SYNTHETIC_CHUTE_SHOCK_Y_G = -0.4
SYNTHETIC_IMPACT_X_G = 0.8
SYNTHETIC_IMPACT_Y_G = 0.3
FOREVER = 0xFFFFFFFF  # window end meaning "until the end of the run"

# Segment indices of the nominal profile.
K_GROUND, K_ASCENT, K_HOLD, K_FREE_FALL, K_CHUTE_OPEN, K_DESCENT, K_IMPACT, K_LANDED = range(8)


def seg(label, dur, mounted, vz, az, ax, ay, azg):
    return Segment(label, dur, mounted, True, vz, az, (ax, ay, azg))


def seg_continue(label, dur, mounted, az, ax, ay, azg):
    s = seg(label, dur, mounted, 0.0, az, ax, ay, azg)
    s.set_vz = False  # carry vertical speed over from the previous segment
    return s


def base(name, description):
    sc = Scenario(name, description)
    sc.seed = SYNTHETIC_SEED
    sc.tick_ms = SYNTHETIC_TICK_MS
    sc.reboot_ms = SYNTHETIC_REBOOT_MS
    sc.tail_ms = SYNTHETIC_TAIL_MS
    sc.ground_pressure_pa = f32(SYNTHETIC_GROUND_PRESSURE_PA)
    sc.temp_c = f32(SYNTHETIC_TEMP_C)
    sc.bus_v = f32(SYNTHETIC_BUS_V)
    sc.current_ma = f32(SYNTHETIC_CURRENT_MA)
    sc.noise = SensorNoise(SYNTHETIC_NOISE_PRESSURE_PA, SYNTHETIC_NOISE_TEMP_C, SYNTHETIC_NOISE_ACCEL_G,
                           SYNTHETIC_NOISE_GYRO_DPS, SYNTHETIC_NOISE_BUS_V, SYNTHETIC_NOISE_CURRENT_MA)
    sc.switch_closed_level_high = [SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH, SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH]
    return sc


def start_of(sc, i):
    return FlightProfile(sc).segment_start_ms(i)


def nominal(name, description):
    sc = base(name, description)
    sc.segments.append(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("ascent", SYNTHETIC_ASCENT_MS, True, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1))
    sc.segments.append(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("free_fall", SYNTHETIC_FREEFALL_MS, False, 0, SYNTHETIC_FREEFALL_AZ, 0, 0,
                           SYNTHETIC_FREEFALL_ACCEL_G))
    sc.segments.append(seg_continue("chute_opening", SYNTHETIC_CHUTE_OPEN_MS, False, SYNTHETIC_CHUTE_OPEN_AZ,
                                    SYNTHETIC_CHUTE_SHOCK_X_G, SYNTHETIC_CHUTE_SHOCK_Y_G, SYNTHETIC_CHUTE_SHOCK_G))
    descent = Segment("descent", 0, False, True, SYNTHETIC_DESCENT_VZ, 0, (0, 0, 1),
                      (SYNTHETIC_SWING_DPS, -SYNTHETIC_SWING_DPS, 0), end_at_ground=True)
    sc.segments.append(descent)
    sc.segments.append(seg("landing_impact", SYNTHETIC_IMPACT_MS, False, 0, 0, SYNTHETIC_IMPACT_X_G,
                           SYNTHETIC_IMPACT_Y_G, SYNTHETIC_IMPACT_G))
    sc.segments.append(seg("landed", SYNTHETIC_LANDED_MS, False, 0, 0, 0, 0, 1))
    p = FlightProfile(sc)
    sc.markers.append(Marker(p.segment_start_ms(K_ASCENT), "scripted drone takeoff"))
    sc.markers.append(Marker(p.segment_start_ms(K_FREE_FALL), "scripted release (drone pin opens)"))
    sc.markers.append(Marker(p.segment_start_ms(K_CHUTE_OPEN),
                             "parachute deployment request point (script annotation only: no FSM / nothing actuated)"))
    sc.markers.append(Marker(p.segment_start_ms(K_IMPACT), "scripted touchdown"))
    return sc


def _w(target, kind, start, end, mag=0.0):
    return FaultWindow(target, kind, start, end, mag)


def all_synthetic_scenarios():
    """The Step 2/3 scenario set (13)."""
    v = [nominal("nominal", "Mounted, ascent, hold, release, free fall, chute opening (clips at 16 g), "
                            "descent, landing. No faults.")]

    sc = nominal("baro_dropout", "Barometer returns invalid samples during descent.")
    t0 = start_of(sc, K_DESCENT) + SYNTHETIC_BARO_DROPOUT_DELAY_MS
    sc.faults.append(_w(FI.TARGET_BARO, FI.DROPOUT, t0, t0 + SYNTHETIC_BARO_DROPOUT_MS))
    v.append(sc)

    sc = nominal("stale_imu", "IMU repeats its last sample (frozen ~1 g) across the release window.")
    t0 = start_of(sc, K_FREE_FALL) - SYNTHETIC_STALE_LEAD_MS
    sc.faults.append(_w(FI.TARGET_IMU, FI.STALE, t0, t0 + SYNTHETIC_STALE_MS))
    v.append(sc)

    sc = nominal("noisy", "Extra noise on barometer and accelerometer for the whole flight.")
    sc.faults.append(_w(FI.TARGET_BARO, FI.NOISE, 0, FOREVER, SYNTHETIC_EXTRA_NOISE_PA))
    sc.faults.append(_w(FI.TARGET_IMU, FI.NOISE, 0, FOREVER, SYNTHETIC_EXTRA_NOISE_G))
    v.append(sc)

    sc = nominal("invalid_values", "NaN pressure during ascent, out-of-range current, all-zero IMU read in "
                                   "descent. All reported VALID by the mock: the validation layer must catch them.")
    ta = start_of(sc, K_ASCENT) + SYNTHETIC_INVALID_DELAY_MS
    td = start_of(sc, K_DESCENT) + SYNTHETIC_INVALID_DELAY_MS
    sc.faults.append(_w(FI.TARGET_BARO, FI.NAN_VALUE, ta, ta + SYNTHETIC_INVALID_MS))
    sc.faults.append(_w(FI.TARGET_POWER, FI.OUT_OF_RANGE, ta, ta + SYNTHETIC_INVALID_MS, SYNTHETIC_OUT_OF_RANGE_MA))
    sc.faults.append(_w(FI.TARGET_IMU, FI.ZERO_READ, td, td + SYNTHETIC_INVALID_MS))
    v.append(sc)

    sc = nominal("stuck_switch_released", "OD-060 S4: both mount switches stuck CLOSED although the CanSat is "
                                          "really released (free fall + baro descent present).")
    sc.faults.append(_w(FI.TARGET_SWITCH1, FI.STUCK_CLOSED, 0, FOREVER))
    sc.faults.append(_w(FI.TARGET_SWITCH2, FI.STUCK_CLOSED, 0, FOREVER))
    v.append(sc)

    sc = base("mounted_imu_zero", "OD-060 S4b: CanSat really still MOUNTED; drone descends fast while the IMU "
                                  "returns all-zero reads (looks like free fall).")
    sc.segments.append(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("ascent", SYNTHETIC_ASCENT_MS, True, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1))
    sc.segments.append(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("drone_fast_descent_mounted", SYNTHETIC_DRONE_FAST_DESCENT_MS, True,
                           SYNTHETIC_DRONE_FAST_DESCENT_VZ, 0, 0, 0, 1))
    sc.segments.append(seg("hold_low_mounted", SYNTHETIC_HOLD_MS, True, 0, 0, 0, 0, 1))
    t0 = start_of(sc, 3)
    sc.faults.append(_w(FI.TARGET_IMU, FI.ZERO_READ, t0, t0 + SYNTHETIC_DRONE_FAST_DESCENT_MS))
    sc.markers.append(Marker(t0, "drone starts fast descent with CanSat still attached"))
    v.append(sc)

    sc = base("mounted_drone_falling", "OD-060 S4c: CanSat really still MOUNTED with healthy switches (closed) while "
                                       "the drone itself drops in near free fall and then recovers. IMU and baro are "
                                       "healthy and genuinely show free fall + descent.")
    sc.segments.append(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("ascent", SYNTHETIC_ASCENT_MS, True, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1))
    sc.segments.append(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, True, 0, 0, 0, 0, 1))
    sc.segments.append(seg("drone_falling_mounted", SYNTHETIC_DRONE_DROP_MS, True, 0, SYNTHETIC_FREEFALL_AZ, 0, 0,
                           SYNTHETIC_FREEFALL_ACCEL_G))
    sc.segments.append(seg_continue("drone_recovers_mounted", SYNTHETIC_DRONE_DROP_MS, True, -SYNTHETIC_FREEFALL_AZ,
                                    0, 0, SYNTHETIC_DRONE_RECOVER_G))
    sc.segments.append(seg("hold_low_mounted", SYNTHETIC_HOLD_MS, True, 0, 0, 0, 0, 1))
    sc.markers.append(Marker(start_of(sc, 3), "drone drops with CanSat still attached"))
    v.append(sc)

    sc = nominal("switch_bounce", "Both switches bounce around the release instant.")
    t0 = start_of(sc, K_FREE_FALL)
    sc.faults.append(_w(FI.TARGET_SWITCH1, FI.BOUNCE, t0, t0 + SYNTHETIC_BOUNCE_WINDOW_MS, SYNTHETIC_BOUNCE_PERIOD1_MS))
    sc.faults.append(_w(FI.TARGET_SWITCH2, FI.BOUNCE, t0, t0 + SYNTHETIC_BOUNCE_WINDOW_MS, SYNTHETIC_BOUNCE_PERIOD2_MS))
    v.append(sc)

    sc = nominal("reset_mid_flight", "Two MCU resets: one during free fall, one during descent. Uptime "
                                     "restarts; sensors re-initialised after each reboot gap.")
    sc.resets_at_ms.append(start_of(sc, K_FREE_FALL) + SYNTHETIC_RESET_DELAY_1_MS)
    sc.resets_at_ms.append(start_of(sc, K_DESCENT) + SYNTHETIC_RESET_DELAY_2_MS)
    v.append(sc)

    sc = nominal("imu_stuck_in_release", "IMU output freezes (fresh timestamps, data-ready set, identical values ~1 g) "
                                         "across the release: only the stuck-output check can catch it.")
    t0 = start_of(sc, K_FREE_FALL) - SYNTHETIC_STALE_LEAD_MS
    sc.faults.append(_w(FI.TARGET_IMU, FI.STUCK_OUTPUT, t0, t0 + SYNTHETIC_STALE_MS))
    v.append(sc)

    sc = nominal("imu_comm_failure_descent", "IMU bus transactions fail for a while during descent.")
    t0 = start_of(sc, K_DESCENT) + SYNTHETIC_INVALID_DELAY_MS
    sc.faults.append(_w(FI.TARGET_IMU, FI.COMM_FAILURE, t0, t0 + SYNTHETIC_BARO_DROPOUT_MS))
    v.append(sc)

    sc = nominal("imu_not_detected", "IMU absent at power-on: begin() fails, IMU invalid all flight.")
    sc.faults.append(_w(FI.TARGET_IMU, FI.NOT_DETECTED, 0, SYNTHETIC_NOT_DETECTED_MS))
    v.append(sc)
    return v


def recovery_fault_scenarios():
    """Recovery-fault scenarios (OD-069): outcomes DOCUMENT current behaviour, incl. hazards."""
    v = []
    sc = nominal("corrupt_record_after_release", "Reset in free fall after release was confirmed but BEFORE the parachute "
                                                 "request; the persisted record is corrupt at reboot. HAZARD (OD-069).")
    sc.resets_at_ms.append(start_of(sc, K_FREE_FALL) + SYNTHETIC_RESET_BEFORE_REQUEST_MS)
    sc.store_faults.append(StoreFaultAtReset(0, STORE_FAULT_CORRUPT_RECORD))
    v.append(sc)
    sc = nominal("corrupt_record_after_request", "Reset in free fall AFTER the parachute request; the persisted record is "
                                                 "corrupt at reboot. HAZARD documentation (OD-069).")
    sc.resets_at_ms.append(start_of(sc, K_FREE_FALL) + SYNTHETIC_RESET_DELAY_1_MS)
    sc.store_faults.append(StoreFaultAtReset(0, STORE_FAULT_CORRUPT_RECORD))
    v.append(sc)
    sc = nominal("corrupt_record_mounted_ascent", "Reset while still mounted during ascent; the persisted record is corrupt "
                                                  "at reboot. HAZARD documentation (OD-069).")
    sc.resets_at_ms.append(start_of(sc, K_ASCENT) + SYNTHETIC_RESET_IN_ASCENT_MS)
    sc.store_faults.append(StoreFaultAtReset(0, STORE_FAULT_CORRUPT_RECORD))
    v.append(sc)
    sc = nominal("record_erased_after_release", "Reset in free fall after release was confirmed, before the request; the "
                                                "persisted record is absent at reboot (looks like a first boot). HAZARD (OD-069).")
    sc.resets_at_ms.append(start_of(sc, K_FREE_FALL) + SYNTHETIC_RESET_BEFORE_REQUEST_MS)
    sc.store_faults.append(StoreFaultAtReset(0, STORE_FAULT_ERASE_RECORD))
    v.append(sc)
    return v


def every_synthetic_scenario():
    return all_synthetic_scenarios() + recovery_fault_scenarios()


def find_synthetic_scenario(name):
    for sc in every_synthetic_scenario():
        if sc.name == name:
            return sc
    return None
