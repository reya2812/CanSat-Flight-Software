// SyntheticScenarios.cpp — scripted flights for software testing only.
//
// !!! EVERY NUMBER IN THIS FILE IS SYNTHETIC !!!
// The values below were picked to exercise code paths (and, loosely, to look
// like the PDR's 100 m drop profile). They are NOT flight thresholds, timings,
// sensor characteristics or measurements, and must never be copied into
// firmware configuration (include/, lib/, src/). Guard checks enforce that the
// SYNTHETIC_ prefix never appears there.
#include "SyntheticScenarios.h"

#include <stdint.h>

#include "FlightProfile.h"

namespace cansat {
namespace sim {
namespace {

using mock::FaultKind;
using mock::FaultTarget;
using mock::FaultWindow;

// ---- Simulation settings (SYNTHETIC) ----
const uint32_t SYNTHETIC_TICK_MS = 50;
const uint32_t SYNTHETIC_REBOOT_MS = 400;
const uint32_t SYNTHETIC_TAIL_MS = 2000;
const float SYNTHETIC_GROUND_PRESSURE_PA = 101325.0f;
const float SYNTHETIC_TEMP_C = 25.0f;
const float SYNTHETIC_BUS_V = 3.90f;
const float SYNTHETIC_CURRENT_MA = 150.0f;
const bool SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH = false;  // wiring is TBD (OD-051)

// ---- Noise (SYNTHETIC) ----
const float SYNTHETIC_NOISE_PRESSURE_PA = 3.0f;
const float SYNTHETIC_NOISE_TEMP_C = 0.05f;
const float SYNTHETIC_NOISE_ACCEL_G = 0.02f;
const float SYNTHETIC_NOISE_GYRO_DPS = 0.5f;
const float SYNTHETIC_NOISE_BUS_V = 0.01f;
const float SYNTHETIC_NOISE_CURRENT_MA = 2.0f;

// ---- Trajectory (SYNTHETIC) ----
const uint32_t SYNTHETIC_GROUND_MS = 3000;
const uint32_t SYNTHETIC_ASCENT_MS = 20000;
const float SYNTHETIC_ASCENT_VZ = 5.0f;  // -> 100 m, echoing the PDR mission height
const uint32_t SYNTHETIC_HOLD_MS = 3000;
const uint32_t SYNTHETIC_FREEFALL_MS = 1500;
const float SYNTHETIC_FREEFALL_AZ = -9.0f;
const float SYNTHETIC_FREEFALL_ACCEL_G = 0.08f;
const uint32_t SYNTHETIC_CHUTE_OPEN_MS = 200;
const float SYNTHETIC_CHUTE_OPEN_AZ = 50.0f;
const float SYNTHETIC_CHUTE_SHOCK_G = 20.0f;  // > 16 g on purpose: demonstrates clipping
const float SYNTHETIC_DESCENT_VZ = -3.0f;
const float SYNTHETIC_SWING_DPS = 5.0f;
const uint32_t SYNTHETIC_IMPACT_MS = 100;
const float SYNTHETIC_IMPACT_G = 6.0f;
const uint32_t SYNTHETIC_LANDED_MS = 5000;
const uint32_t SYNTHETIC_DRONE_FAST_DESCENT_MS = 8000;
const float SYNTHETIC_DRONE_FAST_DESCENT_VZ = -6.0f;
const uint32_t SYNTHETIC_DRONE_DROP_MS = 2000;
const float SYNTHETIC_DRONE_RECOVER_G = 1.9f;

// ---- Fault parameters (SYNTHETIC) ----
const uint32_t SYNTHETIC_BARO_DROPOUT_DELAY_MS = 5000;
const uint32_t SYNTHETIC_BARO_DROPOUT_MS = 3000;
const uint32_t SYNTHETIC_STALE_LEAD_MS = 500;
const uint32_t SYNTHETIC_STALE_MS = 2000;
const float SYNTHETIC_EXTRA_NOISE_PA = 40.0f;
const float SYNTHETIC_EXTRA_NOISE_G = 0.3f;
const uint32_t SYNTHETIC_INVALID_MS = 1000;
const float SYNTHETIC_OUT_OF_RANGE_MA = 99999.0f;
const float SYNTHETIC_BOUNCE_PERIOD1_MS = 30.0f;
const float SYNTHETIC_BOUNCE_PERIOD2_MS = 70.0f;
const uint32_t SYNTHETIC_BOUNCE_WINDOW_MS = 400;
const uint32_t SYNTHETIC_RESET_DELAY_1_MS = 500;
const uint32_t SYNTHETIC_RESET_DELAY_2_MS = 4000;
const uint32_t SYNTHETIC_NOT_DETECTED_MS = 500;
const uint32_t SYNTHETIC_RESET_IN_ASCENT_MS = 10000;  // mid-ascent, after AscentDetected
// Free-fall offset that falls between ReleaseConfirmed and the request with the
// SYNTHETIC params (confirm ~150 ms in, request ~450 ms in). Verified by test.
const uint32_t SYNTHETIC_RESET_BEFORE_REQUEST_MS = 200;
const uint32_t SYNTHETIC_INVALID_DELAY_MS = 2000;
const uint32_t SYNTHETIC_SEED = 12345;
const float SYNTHETIC_CHUTE_SHOCK_X_G = 0.5f;
const float SYNTHETIC_CHUTE_SHOCK_Y_G = -0.4f;
const float SYNTHETIC_IMPACT_X_G = 0.8f;
const float SYNTHETIC_IMPACT_Y_G = 0.3f;
const uint32_t FOREVER = 0xFFFFFFFFu;  // window end meaning "until the end of the run"

Segment seg(const char* label, uint32_t dur, bool mounted, float vz, float az, float ax, float ay,
            float azg) {
  Segment s;
  s.label = label;
  s.duration_ms = dur;
  s.mounted = mounted;
  s.set_vz = true;
  s.vz_mps = vz;
  s.az_mps2 = az;
  s.accel_g[0] = ax;
  s.accel_g[1] = ay;
  s.accel_g[2] = azg;
  return s;
}

Segment segContinue(const char* label, uint32_t dur, bool mounted, float az, float ax, float ay,
                    float azg) {
  Segment s = seg(label, dur, mounted, 0.0f, az, ax, ay, azg);
  s.set_vz = false;  // carry vertical speed over from the previous segment
  return s;
}

Scenario base(const char* name, const char* description) {
  Scenario sc;
  sc.name = name;
  sc.description = description;
  sc.seed = SYNTHETIC_SEED;
  sc.tick_ms = SYNTHETIC_TICK_MS;
  sc.reboot_ms = SYNTHETIC_REBOOT_MS;
  sc.tail_ms = SYNTHETIC_TAIL_MS;
  sc.ground_pressure_pa = SYNTHETIC_GROUND_PRESSURE_PA;
  sc.temp_c = SYNTHETIC_TEMP_C;
  sc.bus_v = SYNTHETIC_BUS_V;
  sc.current_ma = SYNTHETIC_CURRENT_MA;
  sc.noise.pressure_pa = SYNTHETIC_NOISE_PRESSURE_PA;
  sc.noise.temp_c = SYNTHETIC_NOISE_TEMP_C;
  sc.noise.accel_g = SYNTHETIC_NOISE_ACCEL_G;
  sc.noise.gyro_dps = SYNTHETIC_NOISE_GYRO_DPS;
  sc.noise.bus_v = SYNTHETIC_NOISE_BUS_V;
  sc.noise.current_ma = SYNTHETIC_NOISE_CURRENT_MA;
  sc.switch_closed_level_high[0] = SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH;
  sc.switch_closed_level_high[1] = SYNTHETIC_SWITCH_CLOSED_LEVEL_HIGH;
  return sc;
}

// Segment indices of the nominal profile (for computing fault/marker times).
enum NominalSeg { kGround, kAscent, kHold, kFreeFall, kChuteOpen, kDescent, kImpact, kLanded };

Scenario nominal(const char* name, const char* description) {
  Scenario sc = base(name, description);
  sc.segments.push_back(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, true, 0, 0, 0, 0, 1));
  sc.segments.push_back(seg("ascent", SYNTHETIC_ASCENT_MS, true, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1));
  sc.segments.push_back(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, true, 0, 0, 0, 0, 1));
  sc.segments.push_back(seg("free_fall", SYNTHETIC_FREEFALL_MS, false, 0, SYNTHETIC_FREEFALL_AZ, 0,
                            0, SYNTHETIC_FREEFALL_ACCEL_G));
  sc.segments.push_back(segContinue("chute_opening", SYNTHETIC_CHUTE_OPEN_MS, false,
                                    SYNTHETIC_CHUTE_OPEN_AZ, SYNTHETIC_CHUTE_SHOCK_X_G,
                                    SYNTHETIC_CHUTE_SHOCK_Y_G, SYNTHETIC_CHUTE_SHOCK_G));
  Segment descent = seg("descent", 0, false, SYNTHETIC_DESCENT_VZ, 0, 0, 0, 1);
  descent.end_at_ground = true;
  descent.gyro_dps[0] = SYNTHETIC_SWING_DPS;
  descent.gyro_dps[1] = -SYNTHETIC_SWING_DPS;
  sc.segments.push_back(descent);
  sc.segments.push_back(seg("landing_impact", SYNTHETIC_IMPACT_MS, false, 0, 0, SYNTHETIC_IMPACT_X_G,
                            SYNTHETIC_IMPACT_Y_G, SYNTHETIC_IMPACT_G));
  sc.segments.push_back(seg("landed", SYNTHETIC_LANDED_MS, false, 0, 0, 0, 0, 1));

  const FlightProfile p(sc);
  sc.markers.push_back({static_cast<uint32_t>(p.segmentStartMs(kAscent)),
                        "scripted drone takeoff"});
  sc.markers.push_back({static_cast<uint32_t>(p.segmentStartMs(kFreeFall)),
                        "scripted release (drone pin opens)"});
  sc.markers.push_back({static_cast<uint32_t>(p.segmentStartMs(kChuteOpen)),
                        "parachute deployment request point (script annotation only: no FSM / nothing actuated)"});
  sc.markers.push_back({static_cast<uint32_t>(p.segmentStartMs(kImpact)), "scripted touchdown"});
  return sc;
}

uint32_t startOf(const Scenario& sc, int seg_index) {
  const FlightProfile p(sc);
  return p.segmentStartMs(static_cast<size_t>(seg_index));
}

}  // namespace

std::vector<Scenario> allSyntheticScenarios() {
  std::vector<Scenario> v;

  v.push_back(nominal("nominal",
                      "Mounted, ascent, hold, release, free fall, chute opening (clips at 16 g), "
                      "descent, landing. No faults."));

  {
    Scenario sc = nominal("baro_dropout", "Barometer returns invalid samples during descent.");
    const uint32_t t0 = startOf(sc, kDescent) + SYNTHETIC_BARO_DROPOUT_DELAY_MS;
    sc.faults.push_back({FaultTarget::Baro, FaultKind::Dropout, t0, t0 + SYNTHETIC_BARO_DROPOUT_MS, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("stale_imu",
                          "IMU repeats its last sample (frozen ~1 g) across the release window.");
    const uint32_t t0 = startOf(sc, kFreeFall) - SYNTHETIC_STALE_LEAD_MS;
    sc.faults.push_back({FaultTarget::Imu, FaultKind::Stale, t0, t0 + SYNTHETIC_STALE_MS, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("noisy", "Extra noise on barometer and accelerometer for the whole flight.");
    sc.faults.push_back({FaultTarget::Baro, FaultKind::Noise, 0, FOREVER, SYNTHETIC_EXTRA_NOISE_PA});
    sc.faults.push_back({FaultTarget::Imu, FaultKind::Noise, 0, FOREVER, SYNTHETIC_EXTRA_NOISE_G});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("invalid_values",
                          "NaN pressure during ascent, out-of-range current, all-zero IMU read in "
                          "descent. All reported VALID by the mock: the validation layer must catch them.");
    const uint32_t ta = startOf(sc, kAscent) + SYNTHETIC_INVALID_DELAY_MS;
    const uint32_t td = startOf(sc, kDescent) + SYNTHETIC_INVALID_DELAY_MS;
    sc.faults.push_back({FaultTarget::Baro, FaultKind::NaNValue, ta, ta + SYNTHETIC_INVALID_MS, 0});
    sc.faults.push_back({FaultTarget::Power, FaultKind::OutOfRange, ta, ta + SYNTHETIC_INVALID_MS,
                         SYNTHETIC_OUT_OF_RANGE_MA});
    sc.faults.push_back({FaultTarget::Imu, FaultKind::ZeroRead, td, td + SYNTHETIC_INVALID_MS, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("stuck_switch_released",
                          "OD-060 S4: both mount switches stuck CLOSED although the CanSat is "
                          "really released (free fall + baro descent present).");
    sc.faults.push_back({FaultTarget::Switch1, FaultKind::StuckClosed, 0, FOREVER, 0});
    sc.faults.push_back({FaultTarget::Switch2, FaultKind::StuckClosed, 0, FOREVER, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = base("mounted_imu_zero",
                       "OD-060 S4b: CanSat really still MOUNTED; drone descends fast while the IMU "
                       "returns all-zero reads (looks like free fall).");
    sc.segments.push_back(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, true, 0, 0, 0, 0, 1));
    sc.segments.push_back(seg("ascent", SYNTHETIC_ASCENT_MS, true, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1));
    sc.segments.push_back(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, true, 0, 0, 0, 0, 1));
    sc.segments.push_back(seg("drone_fast_descent_mounted", SYNTHETIC_DRONE_FAST_DESCENT_MS, true,
                              SYNTHETIC_DRONE_FAST_DESCENT_VZ, 0, 0, 0, 1));
    sc.segments.push_back(seg("hold_low_mounted", SYNTHETIC_HOLD_MS, true, 0, 0, 0, 0, 1));
    const uint32_t t0 = startOf(sc, 3);
    sc.faults.push_back({FaultTarget::Imu, FaultKind::ZeroRead, t0, t0 + SYNTHETIC_DRONE_FAST_DESCENT_MS, 0});
    sc.markers.push_back({t0, "drone starts fast descent with CanSat still attached"});
    v.push_back(sc);
  }
  {
    Scenario sc = base("mounted_drone_falling",
                       "OD-060 S4c: CanSat really still MOUNTED with healthy switches (closed) while "
                       "the drone itself drops in near free fall and then recovers. IMU and baro are "
                       "healthy and genuinely show free fall + descent.");
    sc.segments.push_back(seg("mounted_on_ground", SYNTHETIC_GROUND_MS, true, 0, 0, 0, 0, 1));
    sc.segments.push_back(seg("ascent", SYNTHETIC_ASCENT_MS, true, SYNTHETIC_ASCENT_VZ, 0, 0, 0, 1));
    sc.segments.push_back(seg("hold_at_altitude", SYNTHETIC_HOLD_MS, true, 0, 0, 0, 0, 1));
    sc.segments.push_back(seg("drone_falling_mounted", SYNTHETIC_DRONE_DROP_MS, true, 0,
                              SYNTHETIC_FREEFALL_AZ, 0, 0, SYNTHETIC_FREEFALL_ACCEL_G));
    sc.segments.push_back(segContinue("drone_recovers_mounted", SYNTHETIC_DRONE_DROP_MS, true,
                                      -SYNTHETIC_FREEFALL_AZ, 0, 0, SYNTHETIC_DRONE_RECOVER_G));
    sc.segments.push_back(seg("hold_low_mounted", SYNTHETIC_HOLD_MS, true, 0, 0, 0, 0, 1));
    sc.markers.push_back({startOf(sc, 3), "drone drops with CanSat still attached"});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("switch_bounce", "Both switches bounce around the release instant.");
    const uint32_t t0 = startOf(sc, kFreeFall);
    sc.faults.push_back({FaultTarget::Switch1, FaultKind::Bounce, t0, t0 + SYNTHETIC_BOUNCE_WINDOW_MS,
                         SYNTHETIC_BOUNCE_PERIOD1_MS});
    sc.faults.push_back({FaultTarget::Switch2, FaultKind::Bounce, t0, t0 + SYNTHETIC_BOUNCE_WINDOW_MS,
                         SYNTHETIC_BOUNCE_PERIOD2_MS});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("reset_mid_flight",
                          "Two MCU resets: one during free fall, one during descent. Uptime "
                          "restarts; sensors re-initialised after each reboot gap.");
    sc.resets_at_ms.push_back(startOf(sc, kFreeFall) + SYNTHETIC_RESET_DELAY_1_MS);
    sc.resets_at_ms.push_back(startOf(sc, kDescent) + SYNTHETIC_RESET_DELAY_2_MS);
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("imu_stuck_in_release",
                          "IMU output freezes (fresh timestamps, data-ready set, identical values ~1 g) "
                          "across the release: only the stuck-output check can catch it.");
    const uint32_t t0 = startOf(sc, kFreeFall) - SYNTHETIC_STALE_LEAD_MS;
    sc.faults.push_back({FaultTarget::Imu, FaultKind::StuckOutput, t0, t0 + SYNTHETIC_STALE_MS, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("imu_comm_failure_descent", "IMU bus transactions fail for a while during descent.");
    const uint32_t t0 = startOf(sc, kDescent) + SYNTHETIC_INVALID_DELAY_MS;
    sc.faults.push_back({FaultTarget::Imu, FaultKind::CommFailure, t0, t0 + SYNTHETIC_BARO_DROPOUT_MS, 0});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("imu_not_detected", "IMU absent at power-on: begin() fails, IMU invalid all flight.");
    sc.faults.push_back({FaultTarget::Imu, FaultKind::NotDetected, 0, SYNTHETIC_NOT_DETECTED_MS, 0});
    v.push_back(sc);
  }
  return v;
}

std::vector<Scenario> recoveryFaultScenarios() {
  std::vector<Scenario> v;
  {
    Scenario sc = nominal("corrupt_record_after_release",
                          "Reset in free fall after release was confirmed but BEFORE the parachute "
                          "request; the persisted record is corrupt at reboot. HAZARD (OD-069).");
    sc.resets_at_ms.push_back(startOf(sc, kFreeFall) + SYNTHETIC_RESET_BEFORE_REQUEST_MS);
    sc.store_faults.push_back({0, StoreFaultKind::CorruptRecord});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("corrupt_record_after_request",
                          "Reset in free fall AFTER the parachute request; the persisted record is "
                          "corrupt at reboot. HAZARD documentation (OD-069).");
    sc.resets_at_ms.push_back(startOf(sc, kFreeFall) + SYNTHETIC_RESET_DELAY_1_MS);
    sc.store_faults.push_back({0, StoreFaultKind::CorruptRecord});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("corrupt_record_mounted_ascent",
                          "Reset while still mounted during ascent; the persisted record is corrupt "
                          "at reboot. HAZARD documentation (OD-069).");
    sc.resets_at_ms.push_back(startOf(sc, kAscent) + SYNTHETIC_RESET_IN_ASCENT_MS);
    sc.store_faults.push_back({0, StoreFaultKind::CorruptRecord});
    v.push_back(sc);
  }
  {
    Scenario sc = nominal("record_erased_after_release",
                          "Reset in free fall after release was confirmed, before the request; the "
                          "persisted record is absent at reboot (looks like a first boot). HAZARD (OD-069).");
    sc.resets_at_ms.push_back(startOf(sc, kFreeFall) + SYNTHETIC_RESET_BEFORE_REQUEST_MS);
    sc.store_faults.push_back({0, StoreFaultKind::EraseRecord});
    v.push_back(sc);
  }
  return v;
}

std::vector<Scenario> everySyntheticScenario() {
  std::vector<Scenario> v = allSyntheticScenarios();
  for (const Scenario& sc : recoveryFaultScenarios()) v.push_back(sc);
  return v;
}

bool findSyntheticScenario(const std::string& name, Scenario& out) {
  for (const Scenario& sc : everySyntheticScenario()) {
    if (sc.name == name) {
      out = sc;
      return true;
    }
  }
  return false;
}

}  // namespace sim
}  // namespace cansat
