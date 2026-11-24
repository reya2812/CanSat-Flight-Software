// TestHarness.h — minimal zero-dependency test runner for native builds.
// (PlatformIO/Unity can replace this later once installation is approved.)
#pragma once

#include <cstdio>
#include <vector>

namespace th {
struct Case {
  const char* name;
  void (*fn)();
};
inline std::vector<Case>& registry() {
  static std::vector<Case> r;
  return r;
}
inline int& failures() {
  static int f = 0;
  return f;
}
inline int& checks() {
  static int c = 0;
  return c;
}
struct Registrar {
  Registrar(const char* n, void (*f)()) { registry().push_back({n, f}); }
};
inline int runAll() {
  int failedCases = 0;
  for (const Case& c : registry()) {
    const int before = failures();
    c.fn();
    const bool ok = failures() == before;
    if (!ok) ++failedCases;
    std::printf("[%s] %s\n", ok ? "PASS" : "FAIL", c.name);
  }
  std::printf("\n%zu test cases, %d failed; %d checks, %d failed\n", registry().size(),
              failedCases, checks(), failures());
  return failures() == 0 ? 0 : 1;
}
}  // namespace th

#define TEST_CASE(name)                                   \
  static void name();                                     \
  static th::Registrar name##_registrar(#name, &name);    \
  static void name()

#define CHECK(cond)                                                          \
  do {                                                                       \
    ++th::checks();                                                          \
    if (!(cond)) {                                                           \
      ++th::failures();                                                      \
      std::printf("  check failed %s:%d: %s\n", __FILE__, __LINE__, #cond); \
    }                                                                        \
  } while (0)
