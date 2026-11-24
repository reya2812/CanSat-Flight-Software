// gen_golden_m2.cpp - prints C++ reference values for the MicroPython port's
// module 2 unit tests (D-017). Laptop only; not part of the firmware build.
//
//   cd micropython
//   c++ -std=c++17 -I../firmware/include -I../firmware/include/config -I../firmware/lib/core \
//       -I../firmware/lib/hal tools/gen_golden_m2.cpp ../firmware/lib/core/RecoveryManager.cpp ../firmware/lib/core/EventDetector.cpp \
//       -o /tmp/gen_golden_m2 && /tmp/gen_golden_m2 > tests/golden_m2.txt
//
// Same compiler and flags as firmware/Makefile (no -O, default FP contraction),
// so accelMag() is compiled exactly as in the reference build. Lines:
//   A <pressure_pa> <reference_pa> <altitude bits hex>
//   M <ax> <ay> <az> <|a| bits hex>
//   N <ax> <ay> <az> <|a| bits hex>   same formula with FP contraction OFF (every
//                                     operation rounded to float32, as MicroPython does)
//   C <magic> <version> <boot> <state> <flags> <t_release> <ground bits hex> <crc hex>
#include <cstdio>
#include <cmath>
#include <cstring>

#define private public  // read EventDetector::accelMag (scratch tool only)
#include "EventDetector.h"
#undef private
#include "Altitude.h"
#include "RecoveryManager.h"

using namespace cansat;

static unsigned bitsOf(float f) {
  unsigned u;
  std::memcpy(&u, &f, 4);
  return u;
}

static unsigned lcg = 12345u;
static float uni(float lo, float hi) {
  lcg = lcg * 1664525u + 1013904223u;
  return lo + (hi - lo) * static_cast<float>(lcg >> 8) / 16777216.0f;
}

// Uncontracted float32 |a|: each multiply and add rounded separately.
static float magNoContract(float x, float y, float z) {
#pragma STDC FP_CONTRACT OFF
  return std::sqrt(x * x + y * y + z * z);
}

namespace {
struct NullSink : IEventSink {
  void onEvent(const Event&) override {}
};
}  // namespace

int main() {
  for (int i = 0; i < 2000; ++i) {
    const float ref = uni(95000.0f, 103000.0f);
    const float p = (i % 4 == 0) ? ref : ref - uni(-50.0f, 1500.0f);
    std::printf("A %.9g %.9g %08x\n", p, ref, bitsOf(altitudeAboveReference(p, ref)));
  }
  FlightParams fp;
  NullSink sink;
  EventDetector det(fp, sink);
  for (int i = 0; i < 2000; ++i) {
    ImuSample m;
    const float s = (i % 3 == 0) ? 0.4f : (i % 3 == 1) ? 2.0f : 17.0f;
    m.ax_g = uni(-s, s);
    m.ay_g = uni(-s, s);
    m.az_g = uni(-s, s);
    std::printf("M %.9g %.9g %.9g %08x\n", m.ax_g, m.ay_g, m.az_g, bitsOf(det.accelMag(m)));
    std::printf("N %.9g %.9g %.9g %08x\n", m.ax_g, m.ay_g, m.az_g, bitsOf(magNoContract(m.ax_g, m.ay_g, m.az_g)));
  }
  for (int i = 0; i < 50; ++i) {
    RecoveryRecord r;
    r.magic = (i == 0) ? 0u : kRecoveryMagic;
    r.version = static_cast<uint16_t>(i % 3);
    r.boot_count = static_cast<uint16_t>(i * 1311u);
    r.last_state = static_cast<uint8_t>(i % 10);
    r.one_shot_flags = static_cast<uint8_t>(i % 8);
    r.t_release_ms = i * 2654435761u;
    r.ground_pressure_pa = (i % 5 == 0) ? 0.0f : uni(90000.0f, 104000.0f);
    std::printf("C %u %u %u %u %u %u %08x %08x\n", r.magic, r.version, r.boot_count, r.last_state,
                r.one_shot_flags, r.t_release_ms, bitsOf(r.ground_pressure_pa), recoveryCrc(r));
  }
  return 0;
}
