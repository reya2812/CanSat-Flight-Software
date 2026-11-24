// FileLogSink.h — ILogSink writing lines to a laptop file (simulation only).
#pragma once

#include <cstdio>

#include "HalInterfaces.h"

namespace cansat {
namespace sim {

class FileLogSink : public ILogSink {
 public:
  explicit FileLogSink(const char* path) : f_(std::fopen(path, "w")) {}
  ~FileLogSink() override {
    if (f_) std::fclose(f_);
  }
  FileLogSink(const FileLogSink&) = delete;
  FileLogSink& operator=(const FileLogSink&) = delete;

  bool ok() const { return f_ != nullptr; }
  bool append(const char* line) override {
    return f_ && std::fputs(line, f_) >= 0 && std::fputc('\n', f_) != EOF;
  }
  bool flush() override { return f_ && std::fflush(f_) == 0; }

 private:
  std::FILE* f_;
};

}  // namespace sim
}  // namespace cansat
