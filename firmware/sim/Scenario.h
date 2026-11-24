// Scenario.h — a scripted, fully SYNTHETIC flight scenario. [SIMULATED]
//
// Every number in a Scenario is SYNTHETIC: chosen only to exercise software
// paths. None is a flight threshold, timing or measured value, and none may
// be copied into firmware configuration.
#pragma once

#include <stdint.h>

#include <string>
#include <vector>

#include "FaultInjector.h"
#include "MockSensors.h"

namespace cansat {
namespace sim {

// One scripted phase of the truth trajectory.
struct Segment {
  std::string label;
  uint32_t duration_ms = 0;  // ignored when end_at_ground is true
  bool end_at_ground = false;  // duration computed so altitude reaches 0 (needs vz<0, az=0)
  bool set_vz = false;         // override vertical speed at segment start
  float vz_mps = 0.0f;         // + up
  float az_mps2 = 0.0f;        // constant vertical acceleration during the segment
  float accel_g[3] = {0.0f, 0.0f, 1.0f};  // what an ideal accelerometer reads (specific force)
  float gyro_dps[3] = {0.0f, 0.0f, 0.0f};
  bool mounted = false;        // physically attached to the drone
};

// Annotation written into the log at a truth time. Script markers are NOT
// flight-software events: no state machine or actuator exists in Step 2.
struct Marker {
  uint32_t t_ms;
  std::string text;
};

// Fault applied to the persisted recovery record just before a scripted
// reset (models e.g. power loss during a flash write). [SIMULATED] The real
// ESP32 NVS behaviour under brownout is unverified (OD-069, PT-06).
enum class StoreFaultKind : uint8_t { CorruptRecord = 1, EraseRecord = 2 };

inline const char* toString(StoreFaultKind k) {
  return k == StoreFaultKind::CorruptRecord ? "corrupt_record" : "erase_record";
}

struct StoreFaultAtReset {
  size_t reset_index = 0;  // 0 = the first entry of resets_at_ms
  StoreFaultKind kind = StoreFaultKind::CorruptRecord;
};

struct Scenario {
  std::string name;
  std::string description;
  uint32_t seed = 1;
  uint32_t tick_ms = 0;          // simulated sensor polling period
  uint32_t reboot_ms = 0;        // simulated reset-to-running gap
  uint32_t tail_ms = 0;          // extra simulated time after the last segment
  float ground_pressure_pa = 0.0f;
  float temp_c = 0.0f;
  float bus_v = 0.0f;
  float current_ma = 0.0f;
  mock::SensorNoise noise;
  bool switch_closed_level_high[2] = {false, false};
  std::vector<Segment> segments;
  std::vector<mock::FaultWindow> faults;
  std::vector<uint32_t> resets_at_ms;
  std::vector<StoreFaultAtReset> store_faults;  // only honoured by the flight-software hook
  std::vector<Marker> markers;
};

}  // namespace sim
}  // namespace cansat
