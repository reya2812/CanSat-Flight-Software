// FswHook.h — plugs the flight software (validator → detector → state machine)
// into the SimRunner. [SIMULATED]
//
// Actuator logic is DISABLED: ActuatorRequests are drained from the queue and
// written to the log as "REQUEST:<name>(NOT_EXECUTED)". No actuator interface is
// referenced here.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "FlightSoftware.h"
#include "MockPersistentStore.h"
#include "Scenario.h"
#include "SimRunner.h"
#include "config/FlightParams.h"

namespace cansat {
namespace sim {

struct FswStats {
  std::vector<FlightState> states_entered;  // in order, across boots (resumes not repeated)
  FlightState final_state = FlightState::PowerOnSelfCheck;
  uint32_t final_faults = 0;
  uint32_t requests = 0;              // ReleaseParachute requests drained (NOT executed)
  uint32_t rejected_transitions = 0;
  uint32_t suppressed_requests = 0;
  uint32_t resets_recovered = 0;
  uint32_t sensors_only_events = 0;
  uint32_t release_confirmed = 0;
  uint32_t last_release_basis = 0;
  uint32_t chute_not_confirmed_alarms = 0;  // ChuteOpenNotConfirmed (alarm, no transition)
  uint32_t corrupt_restarts = 0;            // boots that found a corrupt record
  uint32_t store_faults_applied = 0;
  ChuteStatus final_chute = ChuteStatus::NotRequested;
  std::vector<std::string> timeline;
};

class FlightSoftwareHook : public ISimHook {
 public:
  explicit FlightSoftwareHook(const FlightParams& params);

  std::string extraHeader() const override;
  std::string bannerLine() const override;
  std::string onBoot(bool baro_ok, bool imu_ok, bool power_ok, uint32_t uptime_ms) override;
  void onReset() override;
  std::string onTick(const SensorFrame& frame, uint32_t uptime_ms) override;
  std::string emptyColumns() const override { return ",,,,,"; }

  // Store faults to apply at scripted resets (see Scenario::store_faults).
  void setStoreFaults(const std::vector<StoreFaultAtReset>& f) { store_faults_ = f; }

  const FswStats& stats() const { return stats_; }
  // Read-only view for the parity trace exporter (sim/TraceExporter). nullptr while rebooting.
  const FlightSoftware* fsw() const { return fsw_.get(); }
  mock::MockPersistentStore& store() { return store_; }

 private:
  std::string drainEvents();

  FlightParams params_;
  mock::MockPersistentStore store_;
  std::unique_ptr<FlightSoftware> fsw_;
  std::string pending_;
  FswStats stats_;
  std::vector<StoreFaultAtReset> store_faults_;
  size_t resets_seen_ = 0;
  std::string store_note_;
};

std::string formatFswStats(const FswStats& s);

}  // namespace sim
}  // namespace cansat
