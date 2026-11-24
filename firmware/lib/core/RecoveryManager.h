// RecoveryManager.h — persisted state for reset recovery ([PDR] slide 19:
// "restores the last saved state … prevents repeated deployment commands").
//
// Restore policy (provisional; G4 in MEETING_BRIEF is still open):
//   no record            → start at POWER_ON_SELF_CHECK (normal first boot)
//   corrupt record       → start at POWER_ON_SELF_CHECK, raise kFaultRecoveryRecordCorrupt
//   last state ≤ READY   → start at POWER_ON_SELF_CHECK (still on the ground/drone)
//   last state ≥ ASCENT  → resume that state; one-shot flags and ground reference
//                          restored; recorded one-shot requests are NEVER re-issued.
#pragma once

#include <stdint.h>

#include "HalInterfaces.h"
#include "Types.h"

namespace cansat {

constexpr uint32_t kRecoveryMagic = 0x43534154u;  // "CSAT"
constexpr uint16_t kRecoveryVersion = 1;

uint32_t recoveryCrc(const RecoveryRecord& r);  // CRC-32 over all fields except crc

struct RestoreResult {
  bool had_record = false;
  bool corrupt = false;
  bool resumed = false;  // true when resuming an in-flight state
  FlightState state = FlightState::PowerOnSelfCheck;
  uint8_t one_shot_flags = 0;
  bool has_ground = false;
  float ground_pressure_pa = 0.0f;
  uint16_t boot_count = 1;
};

class RecoveryManager {
 public:
  explicit RecoveryManager(IPersistentStore& store) : store_(store) {}

  // Loads + validates the record, increments boot_count and saves it back.
  RestoreResult restoreOnBoot();

  // Persists current state. Returns false on write failure.
  bool persist(FlightState state, uint8_t one_shot_flags);
  void setGroundPressure(float pa) {
    rec_.ground_pressure_pa = pa;
  }
  const RecoveryRecord& record() const { return rec_; }

 private:
  IPersistentStore& store_;
  RecoveryRecord rec_;
};

}  // namespace cansat
