// BuildFlags.h — compile-time build switches.
//
// [TEAM DECISION] (software lead, Phase 1 constraint) Physical actuation is
// disabled by default in Phases 1–2. No physical servo driver exists.
// See docs/OPEN_DECISIONS.md OD-059 (safety review / arming) and OD-060.
#pragma once

// 1 = building for the real ESP32 flight computer; 0 = laptop (native) build.
#ifndef CANSAT_TARGET_HARDWARE
#define CANSAT_TARGET_HARDWARE 0
#endif

// [TEAM DECISION] Default 0. Must stay 0 until OD-059 is closed by the team.
#ifndef CANSAT_ENABLE_PHYSICAL_ACTUATORS
#define CANSAT_ENABLE_PHYSICAL_ACTUATORS 0
#endif

#if CANSAT_ENABLE_PHYSICAL_ACTUATORS
#error "CANSAT_ENABLE_PHYSICAL_ACTUATORS=1 rejected: no approved physical actuator driver, safety review or arming procedure exists (OD-059). Deployment commands stay simulated/disabled."
#endif

namespace cansat {
namespace build {
constexpr bool kTargetHardware = (CANSAT_TARGET_HARDWARE != 0);
constexpr bool kPhysicalActuatorsEnabled = (CANSAT_ENABLE_PHYSICAL_ACTUATORS != 0);
static_assert(!kPhysicalActuatorsEnabled, "physical actuators must be disabled (OD-059)");
}  // namespace build
}  // namespace cansat
