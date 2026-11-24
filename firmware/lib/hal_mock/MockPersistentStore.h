// MockPersistentStore.h — in-memory IPersistentStore that survives simulated
// resets (models ESP32 NVS). Supports write-failure and corruption injection. [SIMULATED]
#pragma once

#include "HalInterfaces.h"
#include "Types.h"

namespace cansat {
namespace mock {

class MockPersistentStore : public IPersistentStore {
 public:
  bool load(RecoveryRecord& out) override {
    if (!has_) return false;
    out = rec_;
    return true;
  }
  bool save(const RecoveryRecord& rec) override {
    ++writes;
    if (fail_writes) return false;
    rec_ = rec;
    has_ = true;
    return true;
  }
  void corrupt() { rec_.crc ^= 0xA5A5A5A5u; }
  void erase() { has_ = false; }
  bool has() const { return has_; }
  const RecoveryRecord& record() const { return rec_; }

  bool fail_writes = false;
  int writes = 0;

 private:
  bool has_ = false;
  RecoveryRecord rec_;
};

}  // namespace mock
}  // namespace cansat
