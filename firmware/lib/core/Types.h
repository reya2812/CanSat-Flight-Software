// Types.h — common data types shared by all modules. Pure C++, no Arduino.
//
// State / event / command separation (Phase 1 hard constraint):
//   FlightState      — where the mission is.
//   Event            — something detected (by sensors, logic or reset).
//   ActuatorRequest  — something the state machine would LIKE done.
//   ActuatorDecision — what ActuatorManager actually decided. Entering a
//                      deployment-related state never actuates anything by itself.
#pragma once

#include <stdint.h>

namespace cansat {

// [PDR] slide 19 state diagram, numbered 01–08 exactly as on the slide.
// No FAULT state: [RECOMMENDATION] faults are flags + degraded modes (MEETING_BRIEF G1, TBD).
enum class FlightState : uint8_t {
  PowerOnSelfCheck = 1,
  ReadyOnDrone = 2,
  Ascent = 3,
  ReleaseDetected = 4,
  ParachuteDeploy = 5,
  PanelDeploy = 6,
  Descent = 7,
  Landed = 8
};

constexpr uint8_t kFlightStateCount = 8;

inline const char* toString(FlightState s) {
  switch (s) {
    case FlightState::PowerOnSelfCheck: return "POWER_ON_SELF_CHECK";
    case FlightState::ReadyOnDrone: return "READY_ON_DRONE";
    case FlightState::Ascent: return "ASCENT";
    case FlightState::ReleaseDetected: return "RELEASE_DETECTED";
    case FlightState::ParachuteDeploy: return "PARACHUTE_DEPLOY";
    case FlightState::PanelDeploy: return "PANEL_DEPLOY";
    case FlightState::Descent: return "DESCENT";
    case FlightState::Landed: return "LANDED";
  }
  return "INVALID";
}

inline bool isValidFlightStateCode(uint8_t code) { return code >= 1 && code <= kFlightStateCount; }

// ---------------- Sensor samples ----------------
// `valid` = the driver produced a trustworthy reading. Consumers must check
// `valid` and sample age; invalid samples are never silently used (SW-12).

// Health metadata a real driver can report besides the values themselves
// (see docs/OPEN_DECISIONS.md OD-066). Defaults are "not established".
//   comm_ok    — the bus transaction(s) completed (I2C ACK, expected byte count).
//   data_ready — the chip's own status says this is a NEW conversion
//                (MPU6050 INT_STATUS.DATA_RDY, BMP280 status, INA219 CNVR;
//                [ASSUMPTION] register behaviour recalled from datasheets).
struct BaroSample {
  uint32_t t_ms = 0;
  float pressure_pa = 0.0f;
  float temp_c = 0.0f;
  bool valid = false;
  bool comm_ok = false;
  bool data_ready = false;
};

struct ImuSample {
  uint32_t t_ms = 0;
  float ax_g = 0.0f, ay_g = 0.0f, az_g = 0.0f;
  float gx_dps = 0.0f, gy_dps = 0.0f, gz_dps = 0.0f;
  bool valid = false;
  bool saturated = false;  // any accel axis at full scale; never report as a peak (PHASE1 §2.2)
  bool comm_ok = false;
  bool data_ready = false;
};

// Result of the MPU6050 on-chip self-test, if a driver ran it at boot.
enum class SelfTestResult : uint8_t { NotRun = 0, Passed = 1, Failed = 2 };

struct PowerSample {
  uint32_t t_ms = 0;
  float bus_v = 0.0f;       // [TBD] which rail (OD-014, OD-053)
  float current_ma = 0.0f;  // [TBD] which rail
  bool valid = false;
  bool comm_ok = false;
  bool data_ready = false;
};

constexpr uint8_t kSwitchCount = 2;  // [UNVERIFIED] two limit switches; roles TBD (OD-015)

struct SwitchSample {
  uint32_t t_ms = 0;
  bool raw[kSwitchCount] = {false, false};  // electrical level; polarity TBD (OD-051)
  bool valid = false;
};

struct SensorFrame {
  BaroSample baro;
  ImuSample imu;
  PowerSample power;
  SwitchSample switches;
};

// ---------------- Events ----------------

enum class EventType : uint8_t {
  SelfCheckPass = 1,
  SelfCheckFail = 2,
  AscentDetected = 3,
  ReleaseCandidate = 4,
  ReleaseConfirmed = 5,
  ReleaseUncorroborated = 6,
  ReleaseSensorsOnly = 7,  // switch still "mounted" but sensors indicate release (OD-060)
  SwitchReverted = 8,
  ChuteOpenDetected = 9,
  PanelsOutDetected = 10,
  TouchdownDetected = 11,
  SensorFault = 12,
  ResetRecovered = 13,
  ActuatorDecided = 14,     // detail: bits 0-15 InterlockReason, 16-23 ActuatorDecision,
                            //         24-30 ActuatorRequest, 31 phase (0 authorize, 1 execute)
  StateChanged = 15,        // detail = (from << 8) | to
  TransitionRejected = 16,  // detail = (from << 16) | (to << 8) | triggering EventType
  RequestEmitted = 17,      // detail = ActuatorRequest (a REQUEST only; nothing is actuated)
  RequestSuppressed = 18,   // duplicate one-shot request blocked; detail = ActuatorRequest
  SensorRecovered = 19,     // detail = fault bit that cleared
  DescentConfirmed = 20,    // sustained barometric descent after the chute opening was sensed
  ChuteOpenNotConfirmed = 21,  // opening NOT sensed within chute_open_timeout_ms: alarm only, no transition
  RequestWithheld = 22      // request not queued because its one-shot flag could not be persisted
};

// Detail codes for ReleaseConfirmed (which evidence confirmed release).
enum ReleaseBasis : uint32_t {
  kBasisSwitchAndFreefall = 1,
  kBasisSwitchAndBaro = 2,
  kBasisSwitchFreefallBaro = 3,
  kBasisSensorsOnlyPolicy = 4  // switch still "mounted"; accepted by StuckSwitchPolicy (OD-060)
};

// Detail bits for TouchdownDetected.
enum TouchdownDetail : uint32_t { kTouchdownMountReadsClosed = 1u << 0 };

// Parachute status as the software knows it. "Requested" is never "deployed":
// only a sensed opening counts, and nothing is actuated in Phase 2.
enum class ChuteStatus : uint8_t {
  NotRequested = 0,
  RequestedAwaitingOpening = 1,
  OpeningSensed = 2,
  OpeningNotSensedTimeout = 3  // alarm: requested, but no opening sensed in time
};
// Panels have no sensor (OD-037): their status can never be confirmed in software.
enum class PanelStatus : uint8_t { UnknownNoSensor = 0 };

inline const char* toString(ChuteStatus c) {
  switch (c) {
    case ChuteStatus::NotRequested: return "NOT_REQUESTED";
    case ChuteStatus::RequestedAwaitingOpening: return "REQUESTED_AWAITING_OPENING";
    case ChuteStatus::OpeningSensed: return "OPENING_SENSED";
    case ChuteStatus::OpeningNotSensedTimeout: return "OPENING_NOT_SENSED";
  }
  return "?";
}

inline const char* toString(EventType t) {
  switch (t) {
    case EventType::SelfCheckPass: return "SelfCheckPass";
    case EventType::SelfCheckFail: return "SelfCheckFail";
    case EventType::AscentDetected: return "AscentDetected";
    case EventType::ReleaseCandidate: return "ReleaseCandidate";
    case EventType::ReleaseConfirmed: return "ReleaseConfirmed";
    case EventType::ReleaseUncorroborated: return "ReleaseUncorroborated";
    case EventType::ReleaseSensorsOnly: return "ReleaseSensorsOnly";
    case EventType::SwitchReverted: return "SwitchReverted";
    case EventType::ChuteOpenDetected: return "ChuteOpenDetected";
    case EventType::PanelsOutDetected: return "PanelsOutDetected";
    case EventType::TouchdownDetected: return "TouchdownDetected";
    case EventType::SensorFault: return "SensorFault";
    case EventType::ResetRecovered: return "ResetRecovered";
    case EventType::ActuatorDecided: return "ActuatorDecided";
    case EventType::StateChanged: return "StateChanged";
    case EventType::TransitionRejected: return "TransitionRejected";
    case EventType::RequestEmitted: return "RequestEmitted";
    case EventType::RequestSuppressed: return "RequestSuppressed";
    case EventType::SensorRecovered: return "SensorRecovered";
    case EventType::DescentConfirmed: return "DescentConfirmed";
    case EventType::ChuteOpenNotConfirmed: return "ChuteOpenNotConfirmed";
    case EventType::RequestWithheld: return "RequestWithheld";
  }
  return "?";
}

struct Event {
  EventType type = EventType::SensorFault;
  uint32_t t_ms = 0;
  uint32_t detail = 0;  // event-specific payload (e.g. fault bit, decision code)
};

// ---------------- Commands (requests) and decisions ----------------

enum class ActuatorRequest : uint8_t {
  ReleaseParachute = 1,
  DeployPanels = 2,  // only meaningful if a solar servo exists (OD-037, H2)
  BuzzerOn = 3,
  BuzzerOff = 4
};

enum class ActuatorDecision : uint8_t {
  ExecutedSimulated = 1,        // a mock recorded it; nothing physical happened
  BlockedBuildDisabled = 2,     // physical actuation disabled at compile time
  BlockedNotArmed = 3,
  BlockedInterlockMounted = 4,  // mount interlock (policy per OD-060)
  BlockedAlreadyDone = 5,       // one-shot already issued (reset recovery)
  BlockedBusy = 6,              // another actuator is moving
  BlockedParamsIncomplete = 7,  // required FlightParams unset
  // Added with the mock-only DeploymentInterlock (OD-070). Codes are appended, never renumbered.
  BlockedWrongState = 8,             // request not valid in the current flight state
  BlockedReleaseNotConfirmed = 9,    // no confirmed release recorded by the state machine
  BlockedSeparationDelay = 10,       // min_separation_ms not yet elapsed (re-checked independently)
  BlockedConnectionUnavailable = 11, // no connection assessment exists
  BlockedConnectionInvalid = 12,     // the assessment source reported its evidence invalid
  BlockedConnectionIndeterminate = 13,
  BlockedConnectionStale = 14,       // assessment older than the allowed age, or time-inconsistent
  BlockedNotAuthorized = 15,         // execute() without a matching authorization
  BlockedStaleAuthorization = 16,    // authorization from an earlier boot (reset in between)
  BlockedUnsupportedRequest = 17,    // no interlock rule exists for this request (OD-037, OD-052)
  AuthorizedPendingExecution = 18    // authorize() passed; nothing has executed yet
};

inline const char* toString(ActuatorDecision d) {
  switch (d) {
    case ActuatorDecision::ExecutedSimulated: return "ExecutedSimulated";
    case ActuatorDecision::BlockedBuildDisabled: return "BlockedBuildDisabled";
    case ActuatorDecision::BlockedNotArmed: return "BlockedNotArmed";
    case ActuatorDecision::BlockedInterlockMounted: return "BlockedInterlockMounted";
    case ActuatorDecision::BlockedAlreadyDone: return "BlockedAlreadyDone";
    case ActuatorDecision::BlockedBusy: return "BlockedBusy";
    case ActuatorDecision::BlockedParamsIncomplete: return "BlockedParamsIncomplete";
    case ActuatorDecision::BlockedWrongState: return "BlockedWrongState";
    case ActuatorDecision::BlockedReleaseNotConfirmed: return "BlockedReleaseNotConfirmed";
    case ActuatorDecision::BlockedSeparationDelay: return "BlockedSeparationDelay";
    case ActuatorDecision::BlockedConnectionUnavailable: return "BlockedConnectionUnavailable";
    case ActuatorDecision::BlockedConnectionInvalid: return "BlockedConnectionInvalid";
    case ActuatorDecision::BlockedConnectionIndeterminate: return "BlockedConnectionIndeterminate";
    case ActuatorDecision::BlockedConnectionStale: return "BlockedConnectionStale";
    case ActuatorDecision::BlockedNotAuthorized: return "BlockedNotAuthorized";
    case ActuatorDecision::BlockedStaleAuthorization: return "BlockedStaleAuthorization";
    case ActuatorDecision::BlockedUnsupportedRequest: return "BlockedUnsupportedRequest";
    case ActuatorDecision::AuthorizedPendingExecution: return "AuthorizedPendingExecution";
  }
  return "?";
}

// ---------------- Deployment-interlock inputs (OD-070; mock-only) ----------------
//
// The interlock consumes an ABSTRACT connection assessment. How that assessment
// is established (limit switches, other indicators, ground confirmation, a
// mechanical path, a hardware interlock — candidate architectures A1–A5) is
// UNRESOLVED (OD-060, OD-068). Nothing in core code produces an assessment.
enum class ConnectionAssessment : uint8_t {
  Unavailable = 0,    // no assessment exists (no source, not fitted, not implemented)
  Invalid = 1,        // the source says its own evidence is invalid
  Indeterminate = 2,  // the source cannot decide
  Connected = 3,      // the source asserts the CanSat is still attached
  Separated = 4       // the source asserts the CanSat has separated
};

struct ConnectionAssessmentSample {
  ConnectionAssessment value = ConnectionAssessment::Unavailable;
  uint32_t t_ms = 0;        // device uptime at which the assessment was formed
  uint32_t provenance = 0;  // opaque, source-defined tag for logs; never interpreted by core code
};

// Arming (OD-059: arming source and procedure undecided). Unknown never permits.
enum class ArmState : uint8_t { Unknown = 0, Disarmed = 1, Armed = 2 };

struct ArmingSample {
  ArmState state = ArmState::Unknown;
  uint32_t t_ms = 0;
};

// Every reason an interlock evaluation blocked (bitmask; several may be set).
enum InterlockReason : uint32_t {
  kIlParamsIncomplete = 1u << 0,
  kIlUnsupportedRequest = 1u << 1,
  kIlWrongState = 1u << 2,
  kIlReleaseNotConfirmed = 1u << 3,
  kIlAlreadyDone = 1u << 4,
  kIlSeparationDelay = 1u << 5,
  kIlArmUnknown = 1u << 6,
  kIlNotArmed = 1u << 7,
  kIlConnUnavailable = 1u << 8,
  kIlConnInvalid = 1u << 9,
  kIlConnIndeterminate = 1u << 10,
  kIlConnConnected = 1u << 11,
  kIlConnStale = 1u << 12,
  kIlConnFutureTimestamp = 1u << 13,
  kIlPhysicalDriverRefused = 1u << 14
};

// ---------------- Faults (bitmask) ----------------

enum FaultBit : uint32_t {
  kFaultBaroInvalid = 1u << 0,
  kFaultImuInvalid = 1u << 1,
  kFaultPowerInvalid = 1u << 2,
  kFaultSwitchInvalid = 1u << 3,
  kFaultImuSaturated = 1u << 4,
  kFaultLogWrite = 1u << 5,
  kFaultPersistWrite = 1u << 6,
  kFaultRecoveryRecordCorrupt = 1u << 7,
  kFaultSelfCheck = 1u << 8,
  kFaultReleaseDegraded = 1u << 9,
  kFaultParamsIncomplete = 1u << 10,
  kFaultLowBattery = 1u << 11,          // threshold [TBD]; not chosen by software
  kFaultChuteOpenNotSensed = 1u << 12,  // requested, but no opening sensed within the timeout
  kFaultRequestQueueFull = 1u << 13,
  kFaultImuSelfTestNotRun = 1u << 14,   // informational: no self-test result available at boot
  kFaultImuSelfTestFailed = 1u << 15,
  kFaultLandingUnconfirmable = 1u << 16,  // no ground reference: touchdown cannot be confirmed
  kFaultRequestWithheld = 1u << 17,     // request withheld because persistence failed
  kFaultLandedMountClosed = 1u << 18    // touchdown confirmed while the mount switch reads closed
};

inline const char* toString(ActuatorRequest r) {
  switch (r) {
    case ActuatorRequest::ReleaseParachute: return "ReleaseParachute";
    case ActuatorRequest::DeployPanels: return "DeployPanels";
    case ActuatorRequest::BuzzerOn: return "BuzzerOn";
    case ActuatorRequest::BuzzerOff: return "BuzzerOff";
  }
  return "?";
}

// ---------------- Reset-recovery record ----------------
// Persisted on every state / one-shot change (NVS on hardware, mock in tests).
// Integrity check and restore policy are implemented in a later step (RecoveryManager).

enum OneShotFlag : uint8_t {
  kOneShotReleaseConfirmed = 1u << 0,
  kOneShotChuteRequested = 1u << 1,
  kOneShotChuteDecided = 1u << 2
};

struct RecoveryRecord {
  uint32_t magic = 0;
  uint16_t version = 0;
  uint16_t boot_count = 0;
  uint8_t last_state = 0;  // FlightState code
  uint8_t one_shot_flags = 0;
  uint32_t t_release_ms = 0;  // relative to the boot in which release was confirmed
  float ground_pressure_pa = 0.0f;  // ground reference captured at self-check
  uint32_t crc = 0;
};

}  // namespace cansat
