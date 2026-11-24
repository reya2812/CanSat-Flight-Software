// Phase 2 step 1 tests: config, common types and interfaces.
// All values below named SYNTHETIC_* are test-only. They are NOT flight values
// and must never be copied into firmware defaults.
#include <cstring>
#include <type_traits>

#include "HalInterfaces.h"
#include "TestHarness.h"
#include "Types.h"
#include "config/BuildFlags.h"
#include "config/FlightParams.h"
#include "config/HardwareConfig.h"

using namespace cansat;

// ---------- SYNTHETIC test values (not flight values) ----------
static const uint32_t SYNTHETIC_DEBOUNCE_MS = 11;
static const float SYNTHETIC_FREEFALL_G = 0.123f;
static const uint32_t SYNTHETIC_FREEFALL_MS = 22;
static const float SYNTHETIC_BARO_DROP_M = 3.21f;
static const uint32_t SYNTHETIC_BARO_WINDOW_MS = 333;
static const uint32_t SYNTHETIC_CONFIRM_MS = 444;
static const uint32_t SYNTHETIC_STALE_MS = 555;
static const uint32_t SYNTHETIC_SEPARATION_MS = 666;
static const uint32_t SYNTHETIC_FALLBACK_MS = 777;

static ReleaseParams syntheticReleaseParams() {
  ReleaseParams p;
  p.switch_debounce_ms.set(SYNTHETIC_DEBOUNCE_MS);
  p.switch1_open_is_high.set(true);
  p.switch2_open_is_high.set(true);
  p.switch_vote.set(SwitchVote::Any);
  p.freefall_accel_max_g.set(SYNTHETIC_FREEFALL_G);
  p.freefall_min_ms.set(SYNTHETIC_FREEFALL_MS);
  p.baro_min_drop_m.set(SYNTHETIC_BARO_DROP_M);
  p.baro_window_ms.set(SYNTHETIC_BARO_WINDOW_MS);
  p.confirm_window_ms.set(SYNTHETIC_CONFIRM_MS);
  p.sample_stale_ms.set(SYNTHETIC_STALE_MS);
  return p;
}

// ---------- Build flags ----------
TEST_CASE(build_flags_default_to_native_and_actuators_disabled) {
  CHECK(!build::kTargetHardware);
  CHECK(!build::kPhysicalActuatorsEnabled);
}

// ---------- Hardware config ----------
TEST_CASE(all_pins_are_tbd_and_hardware_unresolved) {
  const int pins[] = {hw::PIN_I2C_SDA, hw::PIN_I2C_SCL, hw::PIN_HC12_TX, hw::PIN_HC12_RX,
                      hw::PIN_HC12_SET, hw::PIN_SD_SCK, hw::PIN_SD_MISO, hw::PIN_SD_MOSI,
                      hw::PIN_SD_CS, hw::PIN_SWITCH_1, hw::PIN_SWITCH_2, hw::PIN_BUZZER_1,
                      hw::PIN_BUZZER_2, hw::PIN_SERVO_1, hw::PIN_SERVO_2, hw::PIN_SERVO_3};
  for (int p : pins) CHECK(p == hw::kPinTbd);
  CHECK(hw::kHc12UartBaud == 0);
  CHECK(!hw::requiredHardwareResolved());
}

TEST_CASE(i2c_addresses_match_team_reported_baseline) {
  // [UNVERIFIED] values from docs/03; this only checks the config matches the doc.
  CHECK(hw::kBmp280AddrCandidateA == 0x76);
  CHECK(hw::kBmp280AddrCandidateB == 0x77);
  CHECK(hw::kMpu6050Addr == 0x68);
  CHECK(hw::kIna219Addr == 0x40);
  CHECK(hw::kGroundStationUsbBaud == 115200u);
}

// ---------- Param<T>: no defaults ----------
TEST_CASE(param_starts_unset_and_get_fails) {
  Param<float> p;
  float out = 42.0f;
  CHECK(!p.isSet());
  CHECK(!p.get(out));
  CHECK(out == 42.0f);  // untouched: no fallback value leaks out
  p.set(1.5f);
  CHECK(p.isSet());
  CHECK(p.get(out) && out == 1.5f);
  p.clear();
  CHECK(!p.isSet());
}

TEST_CASE(default_flight_params_are_incomplete) {
  FlightParams fp;
  CHECK(!fp.release.isComplete());
  CHECK(!fp.interlock.isComplete());
  CHECK(!fp.isComplete());
}

TEST_CASE(release_params_complete_only_when_every_field_set) {
  CHECK(syntheticReleaseParams().isComplete());
  // Clearing any single field must make it incomplete.
  for (int i = 0; i < 10; ++i) {
    ReleaseParams p = syntheticReleaseParams();
    switch (i) {
      case 0: p.switch_debounce_ms.clear(); break;
      case 1: p.switch1_open_is_high.clear(); break;
      case 2: p.switch2_open_is_high.clear(); break;
      case 3: p.switch_vote.clear(); break;
      case 4: p.freefall_accel_max_g.clear(); break;
      case 5: p.freefall_min_ms.clear(); break;
      case 6: p.baro_min_drop_m.clear(); break;
      case 7: p.baro_window_ms.clear(); break;
      case 8: p.confirm_window_ms.clear(); break;
      case 9: p.sample_stale_ms.clear(); break;
    }
    CHECK(!p.isComplete());
  }
  ReleaseParams unsetVote = syntheticReleaseParams();
  unsetVote.switch_vote.set(SwitchVote::Unset);
  CHECK(!unsetVote.isComplete());
}

TEST_CASE(stuck_switch_policy_has_no_default_and_unset_is_invalid) {
  InterlockParams ip;
  StuckSwitchPolicy p = StuckSwitchPolicy::StrictSwitchVeto;
  CHECK(!ip.stuck_switch_policy.get(p));
  ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS);
  CHECK(!ip.isComplete());  // policy still unset
  ip.stuck_switch_policy.set(StuckSwitchPolicy::Unset);
  CHECK(!ip.isComplete());  // explicit Unset is rejected too
}

TEST_CASE(persist_failure_policy_has_no_default_and_unset_is_invalid) {
  InterlockParams ip;
  ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS);
  ip.stuck_switch_policy.set(StuckSwitchPolicy::StrictSwitchVeto);
  CHECK(!ip.isComplete());  // OD-067 policy unset
  ip.persist_failure_policy.set(PersistFailurePolicy::Unset);
  CHECK(!ip.isComplete());
  ip.persist_failure_policy.set(PersistFailurePolicy::WithholdUntilPersisted);
  CHECK(ip.isComplete());
  FlightParams fp;
  CHECK(!fp.validation.isComplete() && !fp.transitions.isComplete());
}

TEST_CASE(every_candidate_policy_is_expressible_for_side_by_side_simulation) {
  const StuckSwitchPolicy candidates[] = {
      StuckSwitchPolicy::StrictSwitchVeto, StuckSwitchPolicy::SensorOverride,
      StuckSwitchPolicy::Vote2of3, StuckSwitchPolicy::DelayedFallback};
  for (StuckSwitchPolicy c : candidates) {
    InterlockParams ip;
    ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS);
    ip.persist_failure_policy.set(PersistFailurePolicy::RequestAnyway);
    ip.stuck_switch_policy.set(c);
    if (c == StuckSwitchPolicy::DelayedFallback) {
      CHECK(!ip.isComplete());  // fallback delay required for this policy
      ip.fallback_delay_ms.set(SYNTHETIC_FALLBACK_MS);
    }
    CHECK(ip.isComplete());
  }
}

// ---------- Types ----------
TEST_CASE(flight_states_match_pdr_slide19_numbering) {
  CHECK(static_cast<uint8_t>(FlightState::PowerOnSelfCheck) == 1);
  CHECK(static_cast<uint8_t>(FlightState::ReadyOnDrone) == 2);
  CHECK(static_cast<uint8_t>(FlightState::Ascent) == 3);
  CHECK(static_cast<uint8_t>(FlightState::ReleaseDetected) == 4);
  CHECK(static_cast<uint8_t>(FlightState::ParachuteDeploy) == 5);
  CHECK(static_cast<uint8_t>(FlightState::PanelDeploy) == 6);
  CHECK(static_cast<uint8_t>(FlightState::Descent) == 7);
  CHECK(static_cast<uint8_t>(FlightState::Landed) == 8);
  CHECK(std::strcmp(toString(FlightState::ReleaseDetected), "RELEASE_DETECTED") == 0);
  CHECK(std::strcmp(toString(static_cast<FlightState>(99)), "INVALID") == 0);
  CHECK(!isValidFlightStateCode(0));
  CHECK(isValidFlightStateCode(8));
  CHECK(!isValidFlightStateCode(9));
}

TEST_CASE(default_samples_are_invalid) {
  SensorFrame f;
  CHECK(!f.baro.valid);
  CHECK(!f.imu.valid);
  CHECK(!f.imu.saturated);
  CHECK(!f.power.valid);
  CHECK(!f.switches.valid);
}

TEST_CASE(fault_bits_are_distinct) {
  const uint32_t bits[] = {kFaultBaroInvalid, kFaultImuInvalid, kFaultPowerInvalid,
                           kFaultSwitchInvalid, kFaultImuSaturated, kFaultLogWrite,
                           kFaultPersistWrite, kFaultRecoveryRecordCorrupt, kFaultSelfCheck,
                           kFaultReleaseDegraded, kFaultParamsIncomplete, kFaultLowBattery};
  uint32_t acc = 0;
  for (uint32_t b : bits) {
    CHECK((b & (b - 1)) == 0);  // single bit
    CHECK((acc & b) == 0);      // not reused
    acc |= b;
  }
}

TEST_CASE(state_event_command_are_distinct_types) {
  CHECK((!std::is_same<FlightState, EventType>::value));
  CHECK((!std::is_same<EventType, ActuatorRequest>::value));
  CHECK((!std::is_same<ActuatorRequest, ActuatorDecision>::value));
  CHECK((!std::is_convertible<FlightState, ActuatorRequest>::value));
  CHECK((!std::is_convertible<EventType, ActuatorRequest>::value));
}

// ---------- HAL interfaces are implementable (trivial test doubles) ----------
namespace {
class FakeClock : public IClock {
 public:
  uint32_t t = 0;
  uint32_t nowMs() override { return t; }
};
class CountingActuator : public IActuatorDriver {
 public:
  int calls = 0;
  void apply(ActuatorRequest) override { ++calls; }
  bool isPhysical() const override { return false; }
};
}  // namespace

TEST_CASE(hal_interfaces_are_abstract_and_implementable) {
  CHECK(std::is_abstract<IClock>::value);
  CHECK(std::is_abstract<IBarometer>::value);
  CHECK(std::is_abstract<IImu>::value);
  CHECK(std::is_abstract<IPowerMonitor>::value);
  CHECK(std::is_abstract<IDigitalInputs>::value);
  CHECK(std::is_abstract<ISerialLink>::value);
  CHECK(std::is_abstract<ILogSink>::value);
  CHECK(std::is_abstract<IPersistentStore>::value);
  CHECK(std::is_abstract<IActuatorDriver>::value);
  CHECK(std::is_abstract<IEventSink>::value);
  FakeClock c;
  c.t = 1234;
  IClock& ic = c;
  CHECK(ic.nowMs() == 1234);
  CountingActuator a;
  CHECK(!a.isPhysical());
}

int main() { return th::runAll(); }
