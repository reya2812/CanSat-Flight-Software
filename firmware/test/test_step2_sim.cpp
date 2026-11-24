// Phase 2 step 2 tests: mocks, virtual clock, fault injection, profile, runner.
// [SIMULATED] Everything here is software-only; SYNTHETIC_* values are test-only.
#include <cmath>
#include <cstdlib>
#include <string>
#include <vector>

#include "FaultInjector.h"
#include "FlightProfile.h"
#include "MemoryLogSink.h"
#include "MockSensors.h"
#include "Rng.h"
#include "SimRunner.h"
#include "TestHarness.h"
#include "VirtualClock.h"
#include "scenarios/SyntheticScenarios.h"

using namespace cansat;
using namespace cansat::mock;
using namespace cansat::sim;

// ---------- SYNTHETIC test values ----------
static const float SYNTHETIC_P_PA = 100000.0f;
static const float SYNTHETIC_T_C = 21.5f;
static const float SYNTHETIC_ACC_Z_G = 1.0f;
static const float SYNTHETIC_BUS_V = 3.7f;
static const float SYNTHETIC_I_MA = 120.0f;
static const float SYNTHETIC_NOISE_PA = 5.0f;
static const float SYNTHETIC_BIG_G = 25.0f;
static const float SYNTHETIC_OOR = 12345.0f;

// Truth source with directly settable state (unit tests of the mocks).
class FixedTruth : public ITruthSource {
 public:
  TruthState st;
  FixedTruth() {
    st.pressure_pa = SYNTHETIC_P_PA;
    st.temp_c = SYNTHETIC_T_C;
    st.accel_g[2] = SYNTHETIC_ACC_Z_G;
    st.bus_v = SYNTHETIC_BUS_V;
    st.current_ma = SYNTHETIC_I_MA;
    st.mounted = true;
  }
  TruthState truthAt(uint32_t t) const override {
    TruthState s = st;
    s.truth_ms = t;
    return s;
  }
};

static bool near(float a, float b, float tol) { return std::fabs(a - b) <= tol; }

static std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> out;
  std::string cur;
  for (char c : s) {
    if (c == sep) {
      out.push_back(cur);
      cur.clear();
    } else {
      cur += c;
    }
  }
  out.push_back(cur);
  return out;
}

// Data rows of a runner log (skips '#' comments and the CSV header).
static std::vector<std::vector<std::string>> rows(const MemoryLogSink& log) {
  std::vector<std::vector<std::string>> r;
  for (const std::string& l : log.lines) {
    if (l.empty() || l[0] == '#' || l.rfind("truth_ms,", 0) == 0) continue;
    r.push_back(split(l, ','));
  }
  return r;
}
enum Col { cT = 0, cBoot, cUp, cSeg, cAlt, cVz, cMounted, cBV, cP, cTemp, cIV, cISat, cAx, cAy, cAz,
           cGx, cGy, cGz, cPV, cBus, cI, cSV, cSw1, cSw2, cBComm, cBReady, cIComm, cIReady, cPComm, cPReady,
           cFaults, cEvents, kCols };

static SimSummary runScenario(const std::string& name, MemoryLogSink& log) {
  Scenario sc;
  const bool found = findSyntheticScenario(name, sc);
  CHECK(found);
  SimRunner r;
  return r.run(sc, log);
}

// ================= VirtualClock / Rng =================
TEST_CASE(clock_starts_at_zero_on_first_boot) {
  VirtualClock c;
  CHECK(c.nowMs() == 0 && c.truthMs() == 0 && c.bootCount() == 1 && !c.booting());
}

TEST_CASE(clock_advances_deterministically_and_never_backwards) {
  VirtualClock c;
  c.advance(250);
  CHECK(c.nowMs() == 250);
  CHECK(c.advanceTo(1000));
  CHECK(c.nowMs() == 1000);
  CHECK(!c.advanceTo(999));
  CHECK(c.truthMs() == 1000);
}

TEST_CASE(clock_reset_restarts_uptime_after_reboot_gap) {
  VirtualClock c;
  c.advanceTo(5000);
  c.simulateReset(300);
  CHECK(c.bootCount() == 2);
  CHECK(c.booting());
  CHECK(c.nowMs() == 0);
  c.advanceTo(5299);
  CHECK(c.booting());
  c.advanceTo(5300);
  CHECK(!c.booting() && c.nowMs() == 0);
  c.advanceTo(5450);
  CHECK(c.nowMs() == 150 && c.truthMs() == 5450);
}

TEST_CASE(rng_is_deterministic_and_bounded) {
  Rng a(7), b(7), c(8);
  bool differs = false;
  for (int i = 0; i < 1000; ++i) {
    const float x = a.uniform(2.0f);
    CHECK(x == b.uniform(2.0f));
    CHECK(x >= -2.0f && x <= 2.0f);
    if (x != c.uniform(2.0f)) differs = true;
  }
  CHECK(differs);
  Rng z(0);  // zero seed must not lock up at 0
  CHECK(z.next() != 0);
}

// ================= FaultInjector =================
TEST_CASE(fault_window_is_start_inclusive_end_exclusive) {
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::Dropout, 100, 200, 0});
  CHECK(!f.query(FaultTarget::Baro, 99).dropout);
  CHECK(f.query(FaultTarget::Baro, 100).dropout);
  CHECK(f.query(FaultTarget::Baro, 199).dropout);
  CHECK(!f.query(FaultTarget::Baro, 200).dropout);
}

TEST_CASE(fault_query_filters_by_target_and_combines_kinds) {
  FaultInjector f;
  f.add({FaultTarget::Imu, FaultKind::Noise, 0, 100, 0.1f});
  f.add({FaultTarget::Imu, FaultKind::Noise, 0, 100, 0.2f});
  f.add({FaultTarget::Imu, FaultKind::Stale, 50, 100, 0});
  f.add({FaultTarget::Baro, FaultKind::Dropout, 0, 100, 0});
  const ActiveFaults a = f.query(FaultTarget::Imu, 60);
  CHECK(near(a.noise_amp, 0.3f, 1e-6f));
  CHECK(a.stale && !a.dropout);
  CHECK(!f.query(FaultTarget::Power, 60).dropout);
}

// ================= FlightProfile =================
TEST_CASE(pressure_model_is_p0_at_ground_and_falls_with_altitude) {
  CHECK(near(pressureAtAltitude(101325.0f, 0.0f), 101325.0f, 0.01f));
  const float p100 = pressureAtAltitude(101325.0f, 100.0f);
  CHECK(p100 < 101325.0f);
  CHECK(near(101325.0f - p100, 1200.0f, 50.0f));  // ~12 Pa/m near sea level
}

TEST_CASE(profile_kinematics_segments_and_end_at_ground) {
  Scenario sc;
  sc.ground_pressure_pa = SYNTHETIC_P_PA;
  Segment up;
  up.label = "up";
  up.duration_ms = 2000;
  up.set_vz = true;
  up.vz_mps = 5.0f;
  up.mounted = true;
  Segment fall;
  fall.label = "fall";
  fall.duration_ms = 1000;
  fall.set_vz = true;
  fall.vz_mps = 0.0f;
  fall.az_mps2 = -4.0f;  // -> alt 10 - 2 = 8 m, vz -4
  Segment down;
  down.label = "down";
  down.end_at_ground = true;  // continues at -4 m/s -> 2000 ms to ground
  sc.segments = {up, fall, down};
  FlightProfile p(sc);
  CHECK(p.segmentCount() == 3);
  CHECK(p.segmentDurationMs(2) == 2000);
  CHECK(p.totalMs() == 5000);
  CHECK(near(p.truthAt(1000).alt_m, 5.0f, 1e-4f));
  CHECK(p.truthAt(1000).mounted);
  CHECK(near(p.truthAt(2000).alt_m, 10.0f, 1e-4f));
  CHECK(std::string(p.truthAt(2500).label) == "fall");
  CHECK(!p.truthAt(2500).mounted);
  CHECK(near(p.truthAt(3000).alt_m, 8.0f, 1e-3f));
  CHECK(near(p.truthAt(3000).vz_mps, -4.0f, 1e-3f));
  CHECK(near(p.truthAt(5000).alt_m, 0.0f, 1e-3f));
  CHECK(near(p.truthAt(9000).alt_m, 0.0f, 1e-3f));  // holds end state after the script
  CHECK(p.truthAt(9000).vz_mps == 0.0f);
  CHECK(p.truthAt(2500).pressure_pa > p.truthAt(2000).pressure_pa - 1.0f);
}

TEST_CASE(nominal_profile_reaches_100m_and_ends_on_ground) {
  Scenario sc;
  CHECK(findSyntheticScenario("nominal", sc));
  FlightProfile p(sc);
  CHECK(near(p.truthAt(p.segmentStartMs(2)).alt_m, 100.0f, 0.01f));
  CHECK(near(p.truthAt(p.totalMs()).alt_m, 0.0f, 0.01f));
}

// ================= MockBarometer =================
TEST_CASE(baro_reads_truth_with_uptime_timestamp) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  MockBarometer b(c, t, f, SensorNoise(), 1);
  CHECK(b.begin());
  c.advanceTo(400);
  const BaroSample s = b.read();
  CHECK(s.valid && s.t_ms == 400);
  CHECK(s.pressure_pa == SYNTHETIC_P_PA && s.temp_c == SYNTHETIC_T_C);
}

TEST_CASE(baro_not_detected_makes_begin_fail_and_reads_invalid) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::NotDetected, 0, 10, 0});
  MockBarometer b(c, t, f, SensorNoise(), 1);
  CHECK(!b.begin());
  c.advanceTo(50);
  CHECK(!b.read().valid);  // still uninitialised until begin() succeeds
  CHECK(b.begin());
  CHECK(b.read().valid);
}

TEST_CASE(baro_read_before_begin_is_invalid) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  MockBarometer b(c, t, f, SensorNoise(), 1);
  CHECK(!b.read().valid);
}

TEST_CASE(baro_dropout_is_invalid_then_recovers) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::Dropout, 100, 200, 0});
  MockBarometer b(c, t, f, SensorNoise(), 1);
  b.begin();
  c.advanceTo(150);
  CHECK(!b.read().valid);
  c.advanceTo(200);
  CHECK(b.read().valid);
}

TEST_CASE(baro_stale_repeats_last_fresh_sample_and_timestamp) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::Stale, 100, 300, 0});
  MockBarometer b(c, t, f, SensorNoise(), 1);
  b.begin();
  c.advanceTo(50);
  const BaroSample fresh = b.read();
  t.st.pressure_pa = SYNTHETIC_P_PA - 500.0f;  // truth changes
  c.advanceTo(200);
  const BaroSample stale = b.read();
  CHECK(stale.valid);
  CHECK(stale.t_ms == fresh.t_ms);  // age must be detectable by consumers
  CHECK(stale.pressure_pa == fresh.pressure_pa);
  c.advanceTo(300);
  const BaroSample after = b.read();
  CHECK(after.t_ms == 300 && after.pressure_pa == SYNTHETIC_P_PA - 500.0f);
}

TEST_CASE(baro_stale_without_history_is_invalid) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::Stale, 0, 100, 0});
  MockBarometer b(c, t, f, SensorNoise(), 1);
  b.begin();
  CHECK(!b.read().valid);
}

TEST_CASE(baro_noise_is_bounded_and_deterministic) {
  VirtualClock c1, c2;
  FixedTruth t;
  FaultInjector f;
  SensorNoise n;
  n.pressure_pa = SYNTHETIC_NOISE_PA;
  MockBarometer a(c1, t, f, n, 99), b(c2, t, f, n, 99);
  a.begin();
  b.begin();
  bool varied = false;
  float first = 0;
  for (int i = 0; i < 200; ++i) {
    c1.advance(10);
    c2.advance(10);
    const float pa = a.read().pressure_pa;
    CHECK(pa == b.read().pressure_pa);
    CHECK(std::fabs(pa - SYNTHETIC_P_PA) <= SYNTHETIC_NOISE_PA + 0.01f);
    if (i == 0) first = pa;
    if (pa != first) varied = true;
  }
  CHECK(varied);
}

TEST_CASE(baro_invalid_values_are_reported_valid_for_later_validation) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Baro, FaultKind::ZeroRead, 0, 10, 0});
  f.add({FaultTarget::Baro, FaultKind::NaNValue, 10, 20, 0});
  f.add({FaultTarget::Baro, FaultKind::OutOfRange, 20, 30, SYNTHETIC_OOR});
  MockBarometer b(c, t, f, SensorNoise(), 1);
  b.begin();
  BaroSample s = b.read();
  CHECK(s.valid && s.pressure_pa == 0.0f && s.temp_c == 0.0f);
  c.advanceTo(10);
  s = b.read();
  CHECK(s.valid && std::isnan(s.pressure_pa));
  c.advanceTo(20);
  s = b.read();
  CHECK(s.valid && s.pressure_pa == SYNTHETIC_OOR);
}

// ================= MockImu =================
TEST_CASE(imu_reads_truth_without_saturation) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  MockImu m(c, t, f, SensorNoise(), 1);
  CHECK(m.begin());
  const ImuSample s = m.read();
  CHECK(s.valid && !s.saturated && s.az_g == SYNTHETIC_ACC_Z_G && s.ax_g == 0.0f);
}

TEST_CASE(imu_clips_at_16g_and_flags_saturation) {
  VirtualClock c;
  FixedTruth t;
  t.st.accel_g[2] = SYNTHETIC_BIG_G;
  t.st.accel_g[0] = -SYNTHETIC_BIG_G;
  FaultInjector f;
  MockImu m(c, t, f, SensorNoise(), 1);
  m.begin();
  const ImuSample s = m.read();
  CHECK(s.valid && s.saturated);
  CHECK(s.az_g == kMpu6050FullScaleG && s.ax_g == -kMpu6050FullScaleG);
}

TEST_CASE(imu_zero_read_looks_like_free_fall_but_is_reported_valid) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Imu, FaultKind::ZeroRead, 0, 100, 0});
  MockImu m(c, t, f, SensorNoise(), 1);
  m.begin();
  const ImuSample s = m.read();
  CHECK(s.valid);
  CHECK(s.ax_g == 0 && s.ay_g == 0 && s.az_g == 0 && s.gx_dps == 0 && s.gy_dps == 0 && s.gz_dps == 0);
  CHECK(t.st.mounted);  // truth: still mounted (OD-060 S4b ingredient)
}

TEST_CASE(imu_dropout_and_stale) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Imu, FaultKind::Dropout, 100, 200, 0});
  f.add({FaultTarget::Imu, FaultKind::Stale, 200, 300, 0});
  MockImu m(c, t, f, SensorNoise(), 1);
  m.begin();
  c.advanceTo(50);
  const ImuSample fresh = m.read();
  c.advanceTo(150);
  CHECK(!m.read().valid);
  c.advanceTo(250);
  const ImuSample st = m.read();
  CHECK(st.valid && st.t_ms == fresh.t_ms);
}

// ================= MockPowerMonitor =================
TEST_CASE(power_reads_truth_and_handles_faults) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Power, FaultKind::OutOfRange, 100, 200, SYNTHETIC_OOR});
  f.add({FaultTarget::Power, FaultKind::Dropout, 200, 300, 0});
  MockPowerMonitor p(c, t, f, SensorNoise(), 1);
  CHECK(p.begin());
  PowerSample s = p.read();
  CHECK(s.valid && s.bus_v == SYNTHETIC_BUS_V && s.current_ma == SYNTHETIC_I_MA);
  c.advanceTo(150);
  s = p.read();
  CHECK(s.valid && s.current_ma == SYNTHETIC_OOR);
  c.advanceTo(250);
  CHECK(!p.read().valid);
}

// ================= MockSwitches =================
TEST_CASE(switch_levels_follow_truth_and_polarity) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  MockSwitches lowClosed(c, t, f, false, true);  // switch1 closed=LOW, switch2 closed=HIGH
  SwitchSample s = lowClosed.read();
  CHECK(s.valid && s.raw[0] == false && s.raw[1] == true);  // mounted -> closed
  t.st.mounted = false;
  s = lowClosed.read();
  CHECK(s.raw[0] == true && s.raw[1] == false);  // released -> open
  CHECK(lowClosed.levelMeansClosed(0, false) && lowClosed.levelMeansClosed(1, true));
}

TEST_CASE(switch_stuck_closed_overrides_released_truth) {
  VirtualClock c;
  FixedTruth t;
  t.st.mounted = false;
  FaultInjector f;
  f.add({FaultTarget::Switch1, FaultKind::StuckClosed, 0, 1000, 0});
  MockSwitches sw(c, t, f, true, true);
  const SwitchSample s = sw.read();
  CHECK(s.valid && s.raw[0] == true && s.raw[1] == false);
}

TEST_CASE(switch_stuck_open_overrides_mounted_truth) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Switch2, FaultKind::StuckOpen, 0, 1000, 0});
  MockSwitches sw(c, t, f, true, true);
  const SwitchSample s = sw.read();
  CHECK(s.raw[0] == true && s.raw[1] == false);
}

TEST_CASE(switch_bounce_toggles_with_period) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Switch1, FaultKind::Bounce, 100, 400, 50.0f});
  MockSwitches sw(c, t, f, true, true);
  c.advanceTo(110);
  CHECK(sw.read().raw[0] == true);   // first half-period: truth (closed)
  c.advanceTo(160);
  CHECK(sw.read().raw[0] == false);  // toggled
  c.advanceTo(210);
  CHECK(sw.read().raw[0] == true);
  c.advanceTo(400);
  CHECK(sw.read().raw[0] == true);   // window over
}

TEST_CASE(switch_dropout_invalidates_sample) {
  VirtualClock c;
  FixedTruth t;
  FaultInjector f;
  f.add({FaultTarget::Switch1, FaultKind::Dropout, 0, 100, 0});
  MockSwitches sw(c, t, f, true, true);
  CHECK(!sw.read().valid);
}

// ================= Runner =================
TEST_CASE(runner_nominal_visits_all_segments_in_order) {
  MemoryLogSink log;
  const SimSummary s = runScenario("nominal", log);
  const std::vector<std::string> expected = {"mounted_on_ground", "ascent", "hold_at_altitude",
                                             "free_fall", "chute_opening", "descent",
                                             "landing_impact", "landed"};
  CHECK(s.segment_sequence == expected);
  CHECK(s.baro_invalid == 0 && s.imu_invalid == 0 && s.power_invalid == 0 && s.switch_invalid == 0);
  CHECK(s.resets == 0 && s.final_boot == 1 && s.log_write_failures == 0);
}

TEST_CASE(runner_log_is_labelled_simulated_and_well_formed) {
  MemoryLogSink log;
  runScenario("nominal", log);
  CHECK(!log.lines.empty());
  CHECK(log.lines[0].find("SIMULATED") != std::string::npos);
  CHECK(log.lines[0].find("SYNTHETIC") != std::string::npos);
  bool header = false;
  for (const std::string& l : log.lines) header = header || l == kSimCsvHeader;
  CHECK(header);
  for (const auto& r : rows(log)) CHECK(r.size() == kCols);
}

TEST_CASE(runner_nominal_logs_markers_including_chute_request_point) {
  MemoryLogSink log;
  runScenario("nominal", log);
  bool release = false, chute = false, booted = false;
  for (const auto& r : rows(log)) {
    if (r[cEvents].find("MARK:scripted release") != std::string::npos) {
      release = true;
      CHECK(r[cSeg] == "free_fall");
    }
    if (r[cEvents].find("MARK:parachute deployment request point") != std::string::npos) {
      chute = true;
      CHECK(r[cEvents].find("nothing actuated") != std::string::npos);
    }
    if (r[cEvents].find("BEGIN:baro=ok/imu=ok/power=ok") != std::string::npos) booted = true;
  }
  CHECK(release && chute && booted);
}

TEST_CASE(runner_nominal_switches_open_at_release_and_imu_saturates_only_at_chute_opening) {
  MemoryLogSink log;
  const SimSummary s = runScenario("nominal", log);
  CHECK(s.imu_saturated > 0);
  for (const auto& r : rows(log)) {
    if (r[cISat] == "1") CHECK(r[cSeg] == "chute_opening");
    // SYNTHETIC wiring: closed = LOW, so mounted -> 0, released -> 1
    if (r[cMounted] == "1") CHECK(r[cSw1] == "0" && r[cSw2] == "0");
    if (r[cMounted] == "0") CHECK(r[cSw1] == "1" && r[cSw2] == "1");
    if (r[cSeg] == "free_fall") CHECK(std::fabs(std::atof(r[cAz].c_str())) < 0.2f);
  }
}

TEST_CASE(every_synthetic_scenario_runs_and_is_deterministic) {
  const std::vector<Scenario> all = allSyntheticScenarios();
  CHECK(all.size() >= 9);
  for (const Scenario& sc : all) {
    MemoryLogSink a, b;
    SimRunner r1, r2;
    const SimSummary s1 = r1.run(sc, a);
    r2.run(sc, b);
    CHECK(a.lines == b.lines);
    CHECK(s1.ticks > 0 && s1.log_write_failures == 0);
    CHECK(sc.description.size() > 0);
  }
}

TEST_CASE(runner_baro_dropout_counts_invalid_samples) {
  MemoryLogSink log;
  const SimSummary s = runScenario("baro_dropout", log);
  CHECK(s.baro_invalid == 60);  // SYNTHETIC 3000 ms window / 50 ms tick
  CHECK(s.imu_invalid == 0);
  bool on = false, off = false;
  for (const auto& r : rows(log)) {
    if (r[cBV] == "0") CHECK(r[cFaults] == "baro.dropout");
    on = on || r[cEvents].find("FAULT_ON:baro.dropout") != std::string::npos;
    off = off || r[cEvents].find("FAULT_OFF:baro.dropout") != std::string::npos;
  }
  CHECK(on && off);
}

TEST_CASE(runner_stale_imu_freezes_timestamp_across_release) {
  MemoryLogSink log;
  runScenario("stale_imu", log);
  std::string frozen_az;
  int stale_rows = 0;
  for (const auto& r : rows(log)) {
    if (r[cFaults] == "imu.stale") {
      if (frozen_az.empty()) frozen_az = r[cAz];
      CHECK(r[cAz] == frozen_az);  // stays ~1 g even in free fall
      ++stale_rows;
    }
  }
  CHECK(stale_rows == 40);
}

TEST_CASE(runner_stuck_switch_reads_closed_through_free_fall) {
  MemoryLogSink log;
  runScenario("stuck_switch_released", log);
  int freefall_rows = 0;
  for (const auto& r : rows(log)) {
    CHECK(r[cSw1] == "0" && r[cSw2] == "0");  // always "closed" level
    if (r[cSeg] == "free_fall") {
      ++freefall_rows;
      CHECK(r[cMounted] == "0");  // truth: released
    }
  }
  CHECK(freefall_rows > 0);
}

TEST_CASE(runner_mounted_imu_zero_looks_like_free_fall_while_mounted) {
  MemoryLogSink log;
  runScenario("mounted_imu_zero", log);
  int faulty = 0;
  for (const auto& r : rows(log)) {
    CHECK(r[cMounted] == "1");
    if (r[cFaults] == "imu.zero_read") {
      ++faulty;
      CHECK(r[cIV] == "1" && r[cAz] == "0.000");
      CHECK(std::atof(r[cVz].c_str()) < 0.0f);  // truth: descending
    }
  }
  CHECK(faulty == 160);
}

TEST_CASE(runner_reset_mid_flight_restarts_uptime_and_reinitialises) {
  MemoryLogSink log;
  const SimSummary s = runScenario("reset_mid_flight", log);
  CHECK(s.resets == 2 && s.final_boot == 3);
  CHECK(s.booting_rows == 16);  // 2 x SYNTHETIC 400 ms / 50 ms
  int boot_complete = 0;
  for (const auto& r : rows(log)) {
    if (r[cEvents].find("BOOT_COMPLETE") != std::string::npos) {
      ++boot_complete;
      CHECK(r[cUp] == "0");
      CHECK(r[cEvents].find("BEGIN:baro=ok/imu=ok/power=ok") != std::string::npos);
    }
    if (r[cEvents].find("BOOTING") != std::string::npos) CHECK(r[cBV].empty());
  }
  CHECK(boot_complete == 2);
}

TEST_CASE(runner_imu_not_detected_invalid_for_whole_run) {
  MemoryLogSink log;
  const SimSummary s = runScenario("imu_not_detected", log);
  CHECK(s.imu_invalid == s.sample_rows);
  CHECK(log.lines.size() > 5 && rows(log)[0][cEvents].find("imu=FAIL") != std::string::npos);
}

TEST_CASE(runner_counts_log_write_failures) {
  MemoryLogSink log;
  log.fail_writes = true;
  const SimSummary s = runScenario("nominal", log);
  CHECK(s.log_write_failures > 0);
}

int main() { return th::runAll(); }
