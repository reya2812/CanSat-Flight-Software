// Altitude.h — pressure to altitude above a reference pressure.
// [ASSUMPTION] International Standard Atmosphere approximation (the formula
// commonly used with the BMP280). Accuracy on real hardware is unverified.
#pragma once

#include <cmath>

namespace cansat {

inline float altitudeAboveReference(float pressure_pa, float reference_pa) {
  return 44330.0f * (1.0f - std::pow(pressure_pa / reference_pa, 1.0f / 5.255f));
}

}  // namespace cansat
