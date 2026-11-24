// MemoryLogSink.h — ILogSink that keeps lines in memory (tests). [SIMULATED]
#pragma once

#include <string>
#include <vector>

#include "HalInterfaces.h"

namespace cansat {
namespace mock {

class MemoryLogSink : public ILogSink {
 public:
  bool append(const char* line) override {
    if (fail_writes) return false;
    lines.emplace_back(line);
    return true;
  }
  bool flush() override { return !fail_writes; }

  std::vector<std::string> lines;
  bool fail_writes = false;  // inject storage failure
};

}  // namespace mock
}  // namespace cansat
