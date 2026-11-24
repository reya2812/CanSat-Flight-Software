// Param.h — a value that starts UNSET and has no default.
//
// [TEAM DECISION] (Phase 1 constraint) Firmware holds no default values for
// flight thresholds or deployment timings. Every such value is a Param<T>
// that is unset until explicitly assigned from an approved source (or, in
// tests/simulation only, from a clearly labelled SYNTHETIC_* constant).
#pragma once

namespace cansat {

template <typename T>
class Param {
 public:
  constexpr Param() : set_(false), value_() {}

  void set(T v) {
    value_ = v;
    set_ = true;
  }
  void clear() {
    set_ = false;
    value_ = T();
  }
  constexpr bool isSet() const { return set_; }

  // Returns false (and leaves `out` untouched) when unset. There is
  // deliberately no accessor that returns a fallback value.
  bool get(T& out) const {
    if (!set_) return false;
    out = value_;
    return true;
  }

 private:
  bool set_;
  T value_;
};

}  // namespace cansat
