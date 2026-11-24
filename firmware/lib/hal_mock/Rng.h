// Rng.h — tiny deterministic PRNG (xorshift32) for repeatable synthetic noise.
#pragma once

#include <stdint.h>

namespace cansat {
namespace mock {

class Rng {
 public:
  explicit Rng(uint32_t seed) : state_(seed != 0 ? seed : 0x9E3779B9u) {}

  uint32_t next() {
    uint32_t x = state_;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    state_ = x;
    return x;
  }

  // Uniform in [-amplitude, +amplitude]. Always consumes one draw so that
  // sequences stay aligned whether or not noise is enabled.
  float uniform(float amplitude) {
    const float u = static_cast<float>(next() >> 8) / static_cast<float>(1u << 24);  // [0,1)
    return (u * 2.0f - 1.0f) * amplitude;
  }

 private:
  uint32_t state_;
};

}  // namespace mock
}  // namespace cansat
