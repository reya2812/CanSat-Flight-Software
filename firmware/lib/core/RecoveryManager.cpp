#include "RecoveryManager.h"

#include <cstring>

namespace cansat {

namespace {
uint32_t crc32Update(uint32_t crc, const uint8_t* data, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return crc;
}
template <typename T>
uint32_t crcField(uint32_t crc, const T& v) {
  uint8_t buf[sizeof(T)];
  std::memcpy(buf, &v, sizeof(T));
  return crc32Update(crc, buf, sizeof(T));
}
}  // namespace

uint32_t recoveryCrc(const RecoveryRecord& r) {
  uint32_t c = 0xFFFFFFFFu;
  c = crcField(c, r.magic);
  c = crcField(c, r.version);
  c = crcField(c, r.boot_count);
  c = crcField(c, r.last_state);
  c = crcField(c, r.one_shot_flags);
  c = crcField(c, r.t_release_ms);
  c = crcField(c, r.ground_pressure_pa);
  return ~c;
}

RestoreResult RecoveryManager::restoreOnBoot() {
  RestoreResult res;
  RecoveryRecord loaded;
  const bool have = store_.load(loaded);
  res.had_record = have;
  const bool sane = have && loaded.magic == kRecoveryMagic && loaded.version == kRecoveryVersion &&
                    loaded.crc == recoveryCrc(loaded) && isValidFlightStateCode(loaded.last_state);
  if (have && !sane) res.corrupt = true;

  rec_ = RecoveryRecord();
  rec_.magic = kRecoveryMagic;
  rec_.version = kRecoveryVersion;
  rec_.boot_count = sane ? static_cast<uint16_t>(loaded.boot_count + 1) : 1;
  rec_.last_state = static_cast<uint8_t>(FlightState::PowerOnSelfCheck);

  if (sane && loaded.last_state >= static_cast<uint8_t>(FlightState::Ascent)) {
    res.resumed = true;
    res.state = static_cast<FlightState>(loaded.last_state);
    res.one_shot_flags = loaded.one_shot_flags;
    res.has_ground = loaded.ground_pressure_pa > 0.0f;
    res.ground_pressure_pa = loaded.ground_pressure_pa;
    rec_.last_state = loaded.last_state;
    rec_.one_shot_flags = loaded.one_shot_flags;
    rec_.ground_pressure_pa = loaded.ground_pressure_pa;
  }
  res.boot_count = rec_.boot_count;
  rec_.crc = recoveryCrc(rec_);
  store_.save(rec_);
  return res;
}

bool RecoveryManager::persist(FlightState state, uint8_t one_shot_flags) {
  rec_.last_state = static_cast<uint8_t>(state);
  rec_.one_shot_flags = one_shot_flags;
  rec_.crc = recoveryCrc(rec_);
  return store_.save(rec_);
}

}  // namespace cansat
