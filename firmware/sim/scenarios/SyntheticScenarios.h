// SyntheticScenarios.h — library of SYNTHETIC scenarios. [SIMULATED]
#pragma once

#include <string>
#include <vector>

#include "Scenario.h"

namespace cansat {
namespace sim {

// The Step 2/3 scenario set (13). Unchanged so existing tests keep their meaning.
std::vector<Scenario> allSyntheticScenarios();
// Recovery-fault scenarios (OD-069): the persisted record is corrupted or
// erased at a scripted reset. Outcomes DOCUMENT current behaviour, including
// known hazards; they are not approved behaviour.
std::vector<Scenario> recoveryFaultScenarios();
// Both sets, in that order.
std::vector<Scenario> everySyntheticScenario();
// Searches every set. Returns false if no scenario has that name.
bool findSyntheticScenario(const std::string& name, Scenario& out);

}  // namespace sim
}  // namespace cansat
