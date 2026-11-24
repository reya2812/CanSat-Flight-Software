// FlightProfile.h — turns a Scenario's segments into a continuous truth trajectory.
// [SIMULATED] Kinematics are a scripted approximation, not a physics model:
// the accelerometer reading of each segment is scripted independently of the
// vertical motion so that tests can create inconsistent (faulty) situations.
#pragma once

#include <stdint.h>

#include <vector>

#include "Scenario.h"
#include "TruthSource.h"

namespace cansat {
namespace sim {

// [ASSUMPTION] International Standard Atmosphere approximation (the same form
// as the altitude formula commonly used with the BMP280). Used only to make
// synthetic pressure consistent with synthetic altitude.
float pressureAtAltitude(float ground_pressure_pa, float alt_m);

class FlightProfile : public mock::ITruthSource {
 public:
  explicit FlightProfile(const Scenario& scenario);

  mock::TruthState truthAt(uint32_t truth_ms) const override;

  uint32_t totalMs() const { return total_ms_; }
  size_t segmentCount() const { return segs_.size(); }
  uint32_t segmentStartMs(size_t i) const { return segs_[i].start_ms; }
  uint32_t segmentDurationMs(size_t i) const { return segs_[i].duration_ms; }

 private:
  struct Resolved {
    const Segment* def;
    uint32_t start_ms;
    uint32_t duration_ms;
    float alt0;
    float v0;
  };
  const Scenario& sc_;
  std::vector<Resolved> segs_;
  uint32_t total_ms_ = 0;
};

}  // namespace sim
}  // namespace cansat
