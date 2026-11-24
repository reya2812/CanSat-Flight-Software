#include "TraceExporter.h"

#include <cstdio>

namespace cansat {
namespace sim {

namespace {
const char* b01(bool v) { return v ? "1" : "0"; }
}  // namespace

TraceHook::TraceHook(FlightSoftwareHook& inner, ILogSink& trace,
                     const std::vector<StoreFaultAtReset>& store_faults)
    : inner_(inner), trace_(trace), store_faults_(store_faults) {}

void TraceHook::line(const std::string& s) {
  if (!trace_.append(s.c_str())) ++write_failures_;
}

void TraceHook::events(uint32_t uptime_ms) {
  const FlightSoftware* f = inner_.fsw();
  if (!f) return;
  char buf[96];
  for (int i = 0; i < f->eventCount(); ++i) {
    const Event& e = f->eventAt(i);
    std::snprintf(buf, sizeof buf, "E,%u,%u,%u,%u,%u", boot_, uptime_ms, static_cast<unsigned>(e.type),
                  e.t_ms, e.detail);
    line(buf);
  }
}

void TraceHook::stateLine(uint32_t uptime_ms) {
  const FlightSoftware* f = inner_.fsw();
  if (!f) return;
  char buf[96];
  std::snprintf(buf, sizeof buf, "S,%u,%u,%u,%u,%u", boot_, uptime_ms, static_cast<unsigned>(f->state()),
                static_cast<unsigned>(f->chuteStatus()), f->faultMask());
  line(buf);
}

std::string TraceHook::onBoot(bool baro_ok, bool imu_ok, bool power_ok, uint32_t uptime_ms) {
  ++boot_;
  char buf[96];
  // FlightSoftwareHook never runs the IMU self-test, so the report is NotRun (0).
  std::snprintf(buf, sizeof buf, "B,%u,%u,%s,%s,%s,%u", boot_, uptime_ms, b01(baro_ok), b01(imu_ok),
                b01(power_ok), static_cast<unsigned>(SelfTestResult::NotRun));
  line(buf);
  const std::string r = inner_.onBoot(baro_ok, imu_ok, power_ok, uptime_ms);
  events(uptime_ms);
  stateLine(uptime_ms);
  return r;
}

void TraceHook::onReset() {
  std::string kinds;
  for (const StoreFaultAtReset& f : store_faults_) {
    if (f.reset_index != resets_) continue;
    if (!kinds.empty()) kinds += "+";
    kinds += std::to_string(static_cast<unsigned>(f.kind));
  }
  char buf[64];
  std::snprintf(buf, sizeof buf, "R,%u,%s", static_cast<unsigned>(resets_), kinds.empty() ? "0" : kinds.c_str());
  line(buf);
  ++resets_;
  inner_.onReset();
}

std::string TraceHook::onTick(const SensorFrame& fr, uint32_t uptime_ms) {
  char buf[512];
  const BaroSample& b = fr.baro;
  const ImuSample& m = fr.imu;
  const PowerSample& p = fr.power;
  const SwitchSample& s = fr.switches;
  std::snprintf(buf, sizeof buf,
                "F,%u,%u,%u,%.9g,%.9g,%s,%s,%s,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%s,%s,%s,%s,"
                "%u,%.9g,%.9g,%s,%s,%s,%u,%s,%s,%s",
                boot_, uptime_ms, b.t_ms, static_cast<double>(b.pressure_pa), static_cast<double>(b.temp_c),
                b01(b.valid), b01(b.comm_ok), b01(b.data_ready), m.t_ms, static_cast<double>(m.ax_g),
                static_cast<double>(m.ay_g), static_cast<double>(m.az_g), static_cast<double>(m.gx_dps),
                static_cast<double>(m.gy_dps), static_cast<double>(m.gz_dps), b01(m.valid), b01(m.saturated),
                b01(m.comm_ok), b01(m.data_ready), p.t_ms, static_cast<double>(p.bus_v),
                static_cast<double>(p.current_ma), b01(p.valid), b01(p.comm_ok), b01(p.data_ready), s.t_ms,
                b01(s.raw[0]), b01(s.raw[1]), b01(s.valid));
  line(buf);
  const std::string r = inner_.onTick(fr, uptime_ms);
  events(uptime_ms);
  stateLine(uptime_ms);
  return r;
}

std::string traceHeader(const std::string& scenario, const std::string& policy) {
  return "# SIMULATED - not hardware validation. SYNTHETIC data and parameters.\n"
         "# cansat parity trace v" + std::to_string(kTraceFormatVersion) + "\n"
         "# scenario: " + scenario + "\n"
         "# policy: " + policy;
}

}  // namespace sim
}  // namespace cansat
