// TruthSource.h — the simulated "true" physical state that mock sensors sample.
// [SIMULATED] Produced by a scripted SYNTHETIC flight profile (sim/), never by hardware.
#pragma once

#include <stdint.h>

namespace cansat {
namespace mock {

struct TruthState {
  uint32_t truth_ms = 0;
  int segment = -1;          // index of the active scripted segment
  const char* label = "";    // segment label, e.g. "free_fall"
  float alt_m = 0.0f;        // above the simulated ground reference
  float vz_mps = 0.0f;       // vertical speed, + up
  float pressure_pa = 0.0f;  // derived from alt_m by the profile
  float temp_c = 0.0f;
  float accel_g[3] = {0.0f, 0.0f, 0.0f};  // specific force an ideal accelerometer would read
  float gyro_dps[3] = {0.0f, 0.0f, 0.0f};
  bool mounted = false;      // physically attached to the drone (switches closed if healthy)
  float bus_v = 0.0f;
  float current_ma = 0.0f;
};

class ITruthSource {
 public:
  virtual ~ITruthSource() = default;
  virtual TruthState truthAt(uint32_t truth_ms) const = 0;
};

}  // namespace mock
}  // namespace cansat
