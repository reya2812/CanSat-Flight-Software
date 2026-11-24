// HalInterfaces.h — hardware abstraction layer interfaces.
//
// Core logic depends only on these. Two families of implementations:
//   lib/hal_mock/   laptop tests and simulation (Phase 2 step 2+)
//   lib/hal_esp32/  real drivers (later; requires resolved HardwareConfig)
// [TEAM DECISION] IActuatorDriver (servos and buzzers) gets mock implementations
// only in Phases 1–2. No physical implementation may be written until OD-059.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "Types.h"

namespace cansat {

class IClock {
 public:
  virtual ~IClock() = default;
  virtual uint32_t nowMs() = 0;  // monotonic ms since boot (wraps after ~49.7 days)
};

class IBarometer {
 public:
  virtual ~IBarometer() = default;
  virtual bool begin() = 0;  // false = not detected / init failed (self-check input)
  virtual BaroSample read() = 0;
};

class IImu {
 public:
  virtual ~IImu() = default;
  virtual bool begin() = 0;
  virtual ImuSample read() = 0;
};

class IPowerMonitor {
 public:
  virtual ~IPowerMonitor() = default;
  virtual bool begin() = 0;
  virtual PowerSample read() = 0;
};

class IDigitalInputs {
 public:
  virtual ~IDigitalInputs() = default;
  virtual SwitchSample read() = 0;  // raw electrical levels; debounce is done in core logic
};

// Byte transport (HC-12 UART on hardware; capture/corrupt/drop in tests).
class ISerialLink {
 public:
  virtual ~ISerialLink() = default;
  virtual size_t write(const uint8_t* data, size_t len) = 0;  // returns bytes accepted
  virtual int read() = 0;                                     // next byte, or -1 if none
};

// Line-oriented log sink (SD card on hardware; file/memory in tests).
class ILogSink {
 public:
  virtual ~ILogSink() = default;
  virtual bool append(const char* line) = 0;
  virtual bool flush() = 0;
};

// Small persistent record for reset recovery (NVS on hardware).
class IPersistentStore {
 public:
  virtual ~IPersistentStore() = default;
  virtual bool load(RecoveryRecord& out) = 0;  // false = absent or unreadable
  virtual bool save(const RecoveryRecord& rec) = 0;
};

// Actuator output. Only ActuatorManager may call this, after its interlock.
// [TEAM DECISION] Mock-only in Phases 1–2. ActuatorManager refuses any driver
// whose isPhysical() is true (physical actuation disabled, OD-059).
class IActuatorDriver {
 public:
  virtual ~IActuatorDriver() = default;
  virtual void apply(ActuatorRequest request) = 0;
  virtual bool isPhysical() const = 0;  // mocks return false; checked by tests
};

// Abstract connection assessment for the deployment interlock (OD-070).
// HOW the assessment is formed is unresolved (OD-060 / OD-068; candidate
// architectures A1–A5). No firmware implementation exists; tests use mocks.
class IConnectionAssessmentSource {
 public:
  virtual ~IConnectionAssessmentSource() = default;
  virtual ConnectionAssessmentSample assess(uint32_t now_ms) = 0;
};

// Arming state for the deployment interlock. Source and procedure are
// unresolved (OD-059). No firmware implementation exists; tests use mocks.
class IArmingSource {
 public:
  virtual ~IArmingSource() = default;
  virtual ArmingSample read(uint32_t now_ms) = 0;
};

// Event consumer (state machine, logger, telemetry).
class IEventSink {
 public:
  virtual ~IEventSink() = default;
  virtual void onEvent(const Event& e) = 0;
};

}  // namespace cansat
