// VirtualClock.h — deterministic simulated time. [SIMULATED]
//
// Two time bases:
//   truth time  — the simulated wall clock of the world; never resets.
//   uptime      — what the flight computer sees via IClock::nowMs(); restarts
//                 at 0 after a simulated reset (like millis() on an ESP32).
// During the simulated reboot gap the device is "booting" and nowMs() is 0.
#pragma once

#include <stdint.h>

#include "HalInterfaces.h"

namespace cansat {
namespace mock {

class VirtualClock : public IClock {
 public:
  uint32_t nowMs() override { return booting() ? 0 : truth_ms_ - boot_start_ms_; }

  uint32_t truthMs() const { return truth_ms_; }
  uint16_t bootCount() const { return boot_count_; }
  bool booting() const { return truth_ms_ < boot_start_ms_; }

  void advance(uint32_t ms) { truth_ms_ += ms; }

  // Moves forward only; returns false (and does nothing) for a backwards target.
  bool advanceTo(uint32_t truth_ms) {
    if (truth_ms < truth_ms_) return false;
    truth_ms_ = truth_ms;
    return true;
  }

  // Simulated MCU reset: uptime restarts after `reboot_ms` of truth time.
  void simulateReset(uint32_t reboot_ms) {
    boot_start_ms_ = truth_ms_ + reboot_ms;
    ++boot_count_;
  }

 private:
  uint32_t truth_ms_ = 0;
  uint32_t boot_start_ms_ = 0;
  uint16_t boot_count_ = 1;
};

}  // namespace mock
}  // namespace cansat
