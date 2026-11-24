// FaultInjector.h — time-windowed fault injection for mock sensors. [SIMULATED]
//
// A window is active for truth time t when start_ms <= t < end_ms.
// Several windows may be active for one target at once; mocks apply them in a
// fixed precedence (see each mock's read()).
#pragma once

#include <stdint.h>

#include <vector>

namespace cansat {
namespace mock {

enum class FaultTarget : uint8_t { Baro, Imu, Power, Switch1, Switch2 };

enum class FaultKind : uint8_t {
  NotDetected,  // begin() fails while active (sensor absent at init)
  Dropout,      // read() returns valid=false
  Stale,        // read() repeats the last fresh sample, including its old timestamp
  Noise,        // extra uniform noise of +/- magnitude on the primary channel
  ZeroRead,     // all-zero values reported as valid (e.g. failed bus read) — must be caught later
  NaNValue,     // NaN values reported as valid
  OutOfRange,   // primary channel forced to `magnitude`, reported as valid
  StuckClosed,  // switch reads closed regardless of truth
  StuckOpen,    // switch reads open regardless of truth
  Bounce,       // switch level toggles every `magnitude` ms
  CommFailure,  // bus transaction fails: comm_ok=false, valid=false
  NotReady,     // bus OK but chip reports no new data: previous values, data_ready=false
  StuckOutput   // chip output frozen: previous values repeated with fresh timestamps and data_ready=true
};

struct FaultWindow {
  FaultTarget target;
  FaultKind kind;
  uint32_t start_ms;
  uint32_t end_ms;
  float magnitude;
};

struct ActiveFaults {
  bool not_detected = false;
  bool dropout = false;
  bool stale = false;
  bool zero = false;
  bool nan = false;
  bool out_of_range = false;
  bool stuck_closed = false;
  bool stuck_open = false;
  bool bounce = false;
  bool comm_failure = false;
  bool not_ready = false;
  bool stuck_output = false;
  float noise_amp = 0.0f;
  float out_of_range_value = 0.0f;
  uint32_t bounce_period_ms = 0;
  uint32_t bounce_start_ms = 0;
};

inline const char* toString(FaultTarget t) {
  switch (t) {
    case FaultTarget::Baro: return "baro";
    case FaultTarget::Imu: return "imu";
    case FaultTarget::Power: return "power";
    case FaultTarget::Switch1: return "switch1";
    case FaultTarget::Switch2: return "switch2";
  }
  return "?";
}

inline const char* toString(FaultKind k) {
  switch (k) {
    case FaultKind::NotDetected: return "not_detected";
    case FaultKind::Dropout: return "dropout";
    case FaultKind::Stale: return "stale";
    case FaultKind::Noise: return "noise";
    case FaultKind::ZeroRead: return "zero_read";
    case FaultKind::NaNValue: return "nan";
    case FaultKind::OutOfRange: return "out_of_range";
    case FaultKind::StuckClosed: return "stuck_closed";
    case FaultKind::StuckOpen: return "stuck_open";
    case FaultKind::Bounce: return "bounce";
    case FaultKind::CommFailure: return "comm_failure";
    case FaultKind::NotReady: return "not_ready";
    case FaultKind::StuckOutput: return "stuck_output";
  }
  return "?";
}

class FaultInjector {
 public:
  void add(const FaultWindow& w) { windows_.push_back(w); }
  const std::vector<FaultWindow>& windows() const { return windows_; }

  static bool isActive(const FaultWindow& w, uint32_t t) { return t >= w.start_ms && t < w.end_ms; }

  ActiveFaults query(FaultTarget target, uint32_t t) const {
    ActiveFaults a;
    for (const FaultWindow& w : windows_) {
      if (w.target != target || !isActive(w, t)) continue;
      switch (w.kind) {
        case FaultKind::NotDetected: a.not_detected = true; break;
        case FaultKind::Dropout: a.dropout = true; break;
        case FaultKind::Stale: a.stale = true; break;
        case FaultKind::Noise: a.noise_amp += w.magnitude; break;
        case FaultKind::ZeroRead: a.zero = true; break;
        case FaultKind::NaNValue: a.nan = true; break;
        case FaultKind::OutOfRange:
          a.out_of_range = true;
          a.out_of_range_value = w.magnitude;
          break;
        case FaultKind::StuckClosed: a.stuck_closed = true; break;
        case FaultKind::StuckOpen: a.stuck_open = true; break;
        case FaultKind::Bounce:
          a.bounce = true;
          a.bounce_period_ms = w.magnitude > 0.0f ? static_cast<uint32_t>(w.magnitude) : 1u;
          a.bounce_start_ms = w.start_ms;
          break;
        case FaultKind::CommFailure: a.comm_failure = true; break;
        case FaultKind::NotReady: a.not_ready = true; break;
        case FaultKind::StuckOutput: a.stuck_output = true; break;
      }
    }
    return a;
  }

 private:
  std::vector<FaultWindow> windows_;
};

}  // namespace mock
}  // namespace cansat
