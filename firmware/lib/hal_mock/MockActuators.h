// MockActuators.h — mocks for the deployment interlock and actuator manager.
// [SIMULATED] Nothing here drives hardware. MockActuatorDriver::isPhysical()
// is always false; it only records what it was asked to do.
#pragma once

#include <vector>

#include "HalInterfaces.h"
#include "Types.h"

namespace cansat {
namespace mock {

class MockActuatorDriver : public IActuatorDriver {
 public:
  void apply(ActuatorRequest request) override { applied.push_back(request); }
  bool isPhysical() const override { return false; }
  std::vector<ActuatorRequest> applied;
};

// Returns a scripted assessment. `next` (if non-empty) is consumed one entry
// per assess() call, which lets a test change the evidence between the
// authorization and execution reads; afterwards `current` is returned.
// Stamps t_ms with the caller's time unless `fixed_time` is set.
class ScriptedConnectionSource : public IConnectionAssessmentSource {
 public:
  ConnectionAssessmentSample assess(uint32_t now_ms) override {
    ++calls;
    ConnectionAssessmentSample s = current;
    if (!next.empty()) {
      s = next.front();
      next.erase(next.begin());
      current = s;
    }
    if (!fixed_time) s.t_ms = now_ms;
    return s;
  }
  ConnectionAssessmentSample current;
  std::vector<ConnectionAssessmentSample> next;
  bool fixed_time = false;
  int calls = 0;
};

class MockArmingSource : public IArmingSource {
 public:
  ArmingSample read(uint32_t now_ms) override {
    ++calls;
    ArmingSample s = current;
    if (!next.empty()) {
      s = next.front();
      next.erase(next.begin());
      current = s;
    }
    s.t_ms = now_ms;
    return s;
  }
  ArmingSample current;
  std::vector<ArmingSample> next;
  int calls = 0;
};

}  // namespace mock
}  // namespace cansat
