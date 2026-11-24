#include "FlightProfile.h"

#include <cmath>

namespace cansat {
namespace sim {

float pressureAtAltitude(float ground_pressure_pa, float alt_m) {
  // [ASSUMPTION] ISA approximation: p = p0 * (1 - h/44330)^5.255
  return ground_pressure_pa * std::pow(1.0f - alt_m / 44330.0f, 5.255f);
}

FlightProfile::FlightProfile(const Scenario& scenario) : sc_(scenario) {
  float alt = 0.0f;
  float vz = 0.0f;
  uint32_t t = 0;
  for (const Segment& s : sc_.segments) {
    Resolved r;
    r.def = &s;
    r.start_ms = t;
    r.alt0 = alt;
    r.v0 = s.set_vz ? s.vz_mps : vz;
    uint32_t dur = s.duration_ms;
    if (s.end_at_ground) {
      dur = (r.v0 < 0.0f && alt > 0.0f && s.az_mps2 == 0.0f)
                ? static_cast<uint32_t>(std::ceil(alt / -r.v0 * 1000.0f))
                : 0u;
    }
    r.duration_ms = dur;
    const float T = static_cast<float>(dur) / 1000.0f;
    alt = r.alt0 + r.v0 * T + 0.5f * s.az_mps2 * T * T;
    vz = r.v0 + s.az_mps2 * T;
    if (s.end_at_ground) {
      alt = 0.0f;
      vz = 0.0f;
    }
    t += dur;
    segs_.push_back(r);
  }
  total_ms_ = t;
}

mock::TruthState FlightProfile::truthAt(uint32_t truth_ms) const {
  mock::TruthState st;
  st.truth_ms = truth_ms;
  st.temp_c = sc_.temp_c;
  st.bus_v = sc_.bus_v;
  st.current_ma = sc_.current_ma;
  st.pressure_pa = sc_.ground_pressure_pa;
  if (segs_.empty()) return st;

  size_t idx = 0;
  for (size_t i = 0; i < segs_.size(); ++i) {
    if (segs_[i].start_ms <= truth_ms) idx = i;
  }
  // Skip zero-length segments that share a start time with the next one.
  while (idx + 1 < segs_.size() && segs_[idx].duration_ms == 0 &&
         segs_[idx + 1].start_ms <= truth_ms) {
    ++idx;
  }
  const Resolved& r = segs_[idx];
  uint32_t elapsed = truth_ms - r.start_ms;
  if (elapsed > r.duration_ms) elapsed = r.duration_ms;  // hold end state after the script
  const float T = static_cast<float>(elapsed) / 1000.0f;
  float alt = r.alt0 + r.v0 * T + 0.5f * r.def->az_mps2 * T * T;
  float vz = r.v0 + r.def->az_mps2 * T;
  if (r.def->end_at_ground && alt < 0.0f) alt = 0.0f;
  if (r.def->end_at_ground && elapsed == r.duration_ms) vz = 0.0f;

  st.segment = static_cast<int>(idx);
  st.label = r.def->label.c_str();
  st.alt_m = alt;
  st.vz_mps = vz;
  st.pressure_pa = pressureAtAltitude(sc_.ground_pressure_pa, alt);
  for (int i = 0; i < 3; ++i) {
    st.accel_g[i] = r.def->accel_g[i];
    st.gyro_dps[i] = r.def->gyro_dps[i];
  }
  st.mounted = r.def->mounted;
  return st;
}

}  // namespace sim
}  // namespace cansat
