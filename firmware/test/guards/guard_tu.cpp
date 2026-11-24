// Translation unit used by run_guard_checks.sh. It must compile in a native
// build and must FAIL to compile under the guarded configurations.
#include "config/BuildFlags.h"
#include "config/FlightParams.h"
#include "config/HardwareConfig.h"

int guard_tu_symbol() { return cansat::hw::kPinTbd; }
