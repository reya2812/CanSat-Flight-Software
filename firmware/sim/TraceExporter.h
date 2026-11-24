// TraceExporter.h — machine-readable parity trace for the MicroPython port (D-017).
// [SIMULATED] Laptop only. Wraps FlightSoftwareHook without changing it and
// records, per run:
//   - every SensorFrame given to the flight software, at full float32 precision
//     ("%.9g" round-trips a 32-bit float), including t_ms, comm_ok, data_ready;
//   - every boot report, reset and scripted store fault;
//   - every flight-software event (type, t_ms, detail) and the state / chute
//     status / fault mask after each tick.
// The MicroPython port replays the F lines into its own flight software and
// compares its E and S lines against these.
//
// Line format (version 1), one record per line, comma separated:
//   B,<boot>,<uptime_ms>,<baro_ok>,<imu_ok>,<power_ok>,<imu_self_test>
//   R,<reset_index>,<store_fault>          store_fault: 0 none, else StoreFaultKind code(s) '+'-joined
//   F,<boot>,<uptime_ms>,
//     <baro t_ms,pressure_pa,temp_c,valid,comm_ok,data_ready>,
//     <imu t_ms,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,valid,saturated,comm_ok,data_ready>,
//     <power t_ms,bus_v,current_ma,valid,comm_ok,data_ready>,
//     <switches t_ms,raw0,raw1,valid>
//   E,<boot>,<uptime_ms>,<event_type>,<event_t_ms>,<detail>
//   S,<boot>,<uptime_ms>,<state>,<chute_status>,<fault_mask>
// All enum values are numeric codes from lib/core/Types.h.
#pragma once

#include <stdint.h>

#include <string>
#include <vector>

#include "FswHook.h"
#include "HalInterfaces.h"
#include "Scenario.h"
#include "SimRunner.h"

namespace cansat {
namespace sim {

constexpr int kTraceFormatVersion = 1;

class TraceHook : public ISimHook {
 public:
  TraceHook(FlightSoftwareHook& inner, ILogSink& trace, const std::vector<StoreFaultAtReset>& store_faults);

  std::string extraHeader() const override { return inner_.extraHeader(); }
  std::string bannerLine() const override { return inner_.bannerLine(); }
  std::string onBoot(bool baro_ok, bool imu_ok, bool power_ok, uint32_t uptime_ms) override;
  void onReset() override;
  std::string onTick(const SensorFrame& frame, uint32_t uptime_ms) override;
  std::string emptyColumns() const override { return inner_.emptyColumns(); }

  uint32_t writeFailures() const { return write_failures_; }

 private:
  void line(const std::string& s);
  void events(uint32_t uptime_ms);
  void stateLine(uint32_t uptime_ms);

  FlightSoftwareHook& inner_;
  ILogSink& trace_;
  std::vector<StoreFaultAtReset> store_faults_;
  uint32_t boot_ = 0;
  size_t resets_ = 0;
  uint32_t write_failures_ = 0;
};

// Header comment lines for a trace file.
std::string traceHeader(const std::string& scenario, const std::string& policy);

}  // namespace sim
}  // namespace cansat
