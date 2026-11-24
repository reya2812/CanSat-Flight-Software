// SyntheticFlightParams.h — SYNTHETIC parameter sets for simulation/tests ONLY.
#pragma once

#include <vector>

#include "config/FlightParams.h"

namespace cansat {
namespace sim {

// Complete FlightParams filled with SYNTHETIC values and the given policy.
// NOT flight values: never copy into firmware configuration.
FlightParams syntheticFlightParams(StuckSwitchPolicy policy);

// The four software-expressible OD-060 candidate policies (no default among them).
std::vector<StuckSwitchPolicy> candidatePolicies();

}  // namespace sim
}  // namespace cansat
