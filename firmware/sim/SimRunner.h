// SimRunner.h — executes a Scenario against the mock sensors and writes a log.
// [SIMULATED] There is no flight software in the loop yet (Step 2): the runner
// only polls the mocks and records readings, validity flags and simulation
// events. It never touches any actuator interface.
#pragma once

#include <stdint.h>

#include <string>
#include <vector>

#include "HalInterfaces.h"
#include "Scenario.h"

namespace cansat {
namespace sim {

struct SimSummary {
  std::string scenario;
  uint32_t ticks = 0;
  uint32_t sample_rows = 0;     // rows with sensor readings (device running)
  uint32_t booting_rows = 0;    // rows while the device was rebooting
  uint32_t baro_invalid = 0;
  uint32_t imu_invalid = 0;
  uint32_t imu_saturated = 0;
  uint32_t power_invalid = 0;
  uint32_t switch_invalid = 0;
  uint32_t resets = 0;
  uint16_t final_boot = 0;
  uint32_t log_write_failures = 0;
  std::vector<std::string> segment_sequence;  // labels in the order entered
  std::vector<std::string> timeline;          // "t=..ms EVENT" lines, human readable
};

// CSV columns written for every tick (after '#' comment header lines):
extern const char* const kSimCsvHeader;

// Optional software-under-test plugged into the runner (Step 3: flight software).
// Without a hook the runner behaves exactly as in Step 2.
class ISimHook {
 public:
  virtual ~ISimHook() = default;
  virtual std::string extraHeader() const = 0;  // e.g. ",fsw_state,..." (leading comma)
  virtual std::string bannerLine() const = 0;   // extra '#' line for the log header
  // Device finished booting (first power-on or after a reset). Returns event text.
  virtual std::string onBoot(bool baro_ok, bool imu_ok, bool power_ok, uint32_t uptime_ms) = 0;
  // Device RAM lost (simulated reset).
  virtual void onReset() = 0;
  // One sample tick. Returns the extra CSV columns (leading comma).
  virtual std::string onTick(const SensorFrame& frame, uint32_t uptime_ms) = 0;
  // Extra columns for a row while the device is rebooting (leading comma).
  virtual std::string emptyColumns() const = 0;
};

class SimRunner {
 public:
  SimSummary run(const Scenario& scenario, ILogSink& out, ISimHook* hook = nullptr);
};

// Human-readable summary (multi-line, '#'-prefixed).
std::string formatSummary(const SimSummary& s);

}  // namespace sim
}  // namespace cansat
