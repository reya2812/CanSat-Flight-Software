#include "SimRunner.h"

#include <cstdio>

#include "FaultInjector.h"
#include "FlightProfile.h"
#include "MockSensors.h"
#include "VirtualClock.h"

namespace cansat {
namespace sim {

const char* const kSimCsvHeader =
    "truth_ms,boot,uptime_ms,segment,truth_alt_m,truth_vz_mps,truth_mounted,"
    "baro_valid,p_pa,temp_c,"
    "imu_valid,imu_sat,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,"
    "pwr_valid,bus_v,i_ma,"
    "sw_valid,sw1_raw,sw2_raw,"
    "baro_comm_ok,baro_data_ready,imu_comm_ok,imu_data_ready,pwr_comm_ok,pwr_data_ready,"
    "active_faults,events";

namespace {

// True if instant x lies in the tick interval (prev, now], or x==now==0 at start.
bool inTick(uint32_t x, uint32_t prev, uint32_t now, bool first) {
  return first ? x <= now : (x > prev && x <= now);
}

// Event tokens live in the last CSV column: commas and ';' (the token
// separator) inside a token are replaced so a row always has the same columns.
void appendToken(std::string& s, const std::string& tok) {
  if (!s.empty()) s += ";";
  for (char c : tok) s += (c == ',' || c == ';') ? '/' : c;
}

std::string activeFaultList(const mock::FaultInjector& fi, uint32_t t) {
  std::string s;
  for (const mock::FaultWindow& w : fi.windows()) {
    if (mock::FaultInjector::isActive(w, t)) {
      appendToken(s, std::string(mock::toString(w.target)) + "." + mock::toString(w.kind));
    }
  }
  return s;
}

}  // namespace

SimSummary SimRunner::run(const Scenario& sc, ILogSink& out, ISimHook* hook) {
  SimSummary sum;
  sum.scenario = sc.name;

  mock::VirtualClock clock;
  FlightProfile profile(sc);
  mock::FaultInjector faults;
  for (const mock::FaultWindow& w : sc.faults) faults.add(w);

  mock::MockBarometer baro(clock, profile, faults, sc.noise, sc.seed * 4u + 1u);
  mock::MockImu imu(clock, profile, faults, sc.noise, sc.seed * 4u + 2u);
  mock::MockPowerMonitor power(clock, profile, faults, sc.noise, sc.seed * 4u + 3u);
  mock::MockSwitches switches(clock, profile, faults, sc.switch_closed_level_high[0],
                              sc.switch_closed_level_high[1]);

  auto write = [&](const std::string& line) {
    if (!out.append(line.c_str())) ++sum.log_write_failures;
  };

  write("# SIMULATED - not hardware validation. All sensor values are SYNTHETIC.");
  write("# scenario: " + sc.name);
  write("# description: " + sc.description);
  if (hook) {
    write(hook->bannerLine());
  } else {
    write("# no flight software or actuator is in the loop (Phase 2 step 2)");
  }
  write(std::string(kSimCsvHeader) + (hook ? hook->extraHeader() : std::string()));

  auto beginAll = [&]() {
    const bool b = baro.begin();
    const bool i = imu.begin();
    const bool p = power.begin();
    char buf[96];
    std::snprintf(buf, sizeof buf, "BEGIN:baro=%s/imu=%s/power=%s", b ? "ok" : "FAIL",
                  i ? "ok" : "FAIL", p ? "ok" : "FAIL");
    std::string r(buf);
    if (hook) {
      const std::string h = hook->onBoot(b, i, p, clock.nowMs());
      if (!h.empty()) r += ";" + h;
    }
    return r;
  };

  const uint32_t end_ms = profile.totalMs() + sc.tail_ms;
  const uint32_t tick = sc.tick_ms > 0 ? sc.tick_ms : 1u;
  int last_segment = -1;
  bool was_booting = false;
  uint32_t prev = 0;
  size_t next_reset = 0;

  for (uint32_t t = 0;; t += tick) {
    if (t > end_ms) break;
    const bool first = (t == 0);
    clock.advanceTo(t);
    ++sum.ticks;
    std::string events;

    if (first) {
      appendToken(events, "BOOT:1");
      appendToken(events, beginAll());
    }

    const mock::TruthState truth = profile.truthAt(t);
    if (truth.segment != last_segment) {
      last_segment = truth.segment;
      sum.segment_sequence.push_back(truth.label);
      appendToken(events, std::string("SEGMENT:") + truth.label);
    }
    for (const Marker& m : sc.markers) {
      if (inTick(m.t_ms, prev, t, first)) appendToken(events, "MARK:" + m.text);
    }
    for (const mock::FaultWindow& w : sc.faults) {
      const std::string name = std::string(mock::toString(w.target)) + "." + mock::toString(w.kind);
      if (inTick(w.start_ms, prev, t, first)) appendToken(events, "FAULT_ON:" + name);
      if (!first && inTick(w.end_ms, prev, t, false)) appendToken(events, "FAULT_OFF:" + name);
    }
    while (next_reset < sc.resets_at_ms.size() &&
           inTick(sc.resets_at_ms[next_reset], prev, t, first)) {
      clock.simulateReset(sc.reboot_ms);
      if (hook) hook->onReset();
      ++sum.resets;
      appendToken(events, "RESET:boot=" + std::to_string(clock.bootCount()));
      ++next_reset;
    }
    if (was_booting && !clock.booting()) {
      appendToken(events, "BOOT_COMPLETE:boot=" + std::to_string(clock.bootCount()));
      appendToken(events, beginAll());
    }
    was_booting = clock.booting();

    char head[160];
    std::snprintf(head, sizeof head, "%u,%u,%u,%s,%.2f,%.2f,%d,", t,
                  static_cast<unsigned>(clock.bootCount()), clock.nowMs(), truth.label,
                  truth.alt_m, truth.vz_mps, truth.mounted ? 1 : 0);
    const std::string faults_now = activeFaultList(faults, t);
    std::string row = head;
    std::string extra;

    if (clock.booting()) {
      ++sum.booting_rows;
      row += ",,,,,,,,,,,,,,,,,,,,,,,";  // no readings while rebooting (23 empty fields)
      appendToken(events, "BOOTING");
      extra = hook ? hook->emptyColumns() : std::string();
    } else {
      ++sum.sample_rows;
      const BaroSample b = baro.read();
      const ImuSample m = imu.read();
      const PowerSample p = power.read();
      const SwitchSample s = switches.read();
      if (!b.valid) ++sum.baro_invalid;
      if (!m.valid) ++sum.imu_invalid;
      if (m.valid && m.saturated) ++sum.imu_saturated;
      if (!p.valid) ++sum.power_invalid;
      if (!s.valid) ++sum.switch_invalid;
      char buf[384];
      std::snprintf(buf, sizeof buf,
                    "%d,%.1f,%.2f,%d,%d,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%d,%.3f,%.1f,%d,%d,%d,"
                    "%d,%d,%d,%d,%d,%d,",
                    b.valid ? 1 : 0, b.pressure_pa, b.temp_c, m.valid ? 1 : 0, m.saturated ? 1 : 0,
                    m.ax_g, m.ay_g, m.az_g, m.gx_dps, m.gy_dps, m.gz_dps, p.valid ? 1 : 0, p.bus_v,
                    p.current_ma, s.valid ? 1 : 0, s.raw[0] ? 1 : 0, s.raw[1] ? 1 : 0,
                    b.comm_ok ? 1 : 0, b.data_ready ? 1 : 0, m.comm_ok ? 1 : 0, m.data_ready ? 1 : 0,
                    p.comm_ok ? 1 : 0, p.data_ready ? 1 : 0);
      row += buf;
      if (hook) {
        SensorFrame frame;
        frame.baro = b;
        frame.imu = m;
        frame.power = p;
        frame.switches = s;
        extra = hook->onTick(frame, clock.nowMs());
      }
    }
    row += faults_now + "," + events + extra;
    write(row);

    if (!events.empty() && events != "BOOTING") {
      char tl[48];
      std::snprintf(tl, sizeof tl, "t=%7u ms  boot=%u  ", t, static_cast<unsigned>(clock.bootCount()));
      sum.timeline.push_back(std::string(tl) + events);
    }
    prev = t;
  }
  sum.final_boot = clock.bootCount();
  out.flush();
  return sum;
}

std::string formatSummary(const SimSummary& s) {
  std::string r;
  char buf[256];
  r += "# ===== SIMULATED run summary (not hardware validation; SYNTHETIC data) =====\n";
  r += "# scenario: " + s.scenario + "\n";
  std::snprintf(buf, sizeof buf,
                "# ticks=%u sample_rows=%u booting_rows=%u resets=%u final_boot=%u log_write_failures=%u\n",
                s.ticks, s.sample_rows, s.booting_rows, s.resets, static_cast<unsigned>(s.final_boot),
                s.log_write_failures);
  r += buf;
  std::snprintf(buf, sizeof buf,
                "# invalid samples: baro=%u imu=%u power=%u switches=%u | imu saturated=%u\n",
                s.baro_invalid, s.imu_invalid, s.power_invalid, s.switch_invalid, s.imu_saturated);
  r += buf;
  r += "# segments:";
  for (const std::string& seg : s.segment_sequence) r += " " + seg;
  r += "\n# event timeline:\n";
  for (const std::string& line : s.timeline) r += "#   " + line + "\n";
  return r;
}

}  // namespace sim
}  // namespace cansat
