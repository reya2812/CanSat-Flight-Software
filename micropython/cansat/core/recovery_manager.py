# recovery_manager.py - persisted state for reset recovery ([PDR] slide 19).
# (port of lib/core/RecoveryManager.h/.cpp)
#
# Restore policy (provisional; G4 in MEETING_BRIEF still open; OD-069 hazards apply):
#   no record            -> start at POWER_ON_SELF_CHECK (normal first boot)
#   corrupt record       -> start at POWER_ON_SELF_CHECK, raise FAULT_RECOVERY_RECORD_CORRUPT
#   last state <= READY  -> start at POWER_ON_SELF_CHECK (still on the ground/drone)
#   last state >= ASCENT -> resume that state; one-shot flags and ground reference
#                           restored; recorded one-shot requests are NEVER re-issued.
#
# [UNVERIFIED] Whether the ESP32 NVS write survives a brownout mid-write.
import struct

from cansat.core import types as T
from cansat.core.num import f32, u16

RECOVERY_MAGIC = 0x43534154  # "CSAT"
RECOVERY_VERSION = 1

# MicroPython's struct has no Struct class ([ASSUMPTION], recalled): plain pack/unpack only.
# Byte layout used for the CRC: the C++ fields in order, little-endian, no
# padding (C++ feeds each field's bytes to the CRC separately).
CRC_FIELDS_FORMAT = "<IHHBBIf"
# Storage layout for a byte-oriented store (NVS on the board): CRC fields + crc.
RECORD_FORMAT = "<IHHBBIfI"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)  # 22 bytes


def _crc32_update(crc, data):
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc


def recovery_crc(r):
    """CRC-32 over all fields except crc (same bytes and algorithm as C++ recoveryCrc)."""
    data = struct.pack(CRC_FIELDS_FORMAT, r.magic, r.version, r.boot_count, r.last_state, r.one_shot_flags,
                            r.t_release_ms, r.ground_pressure_pa)
    return (~_crc32_update(0xFFFFFFFF, data)) & 0xFFFFFFFF


def copy_record(r):
    c = T.RecoveryRecord()
    c.magic, c.version, c.boot_count = r.magic, r.version, r.boot_count
    c.last_state, c.one_shot_flags, c.t_release_ms = r.last_state, r.one_shot_flags, r.t_release_ms
    c.ground_pressure_pa, c.crc = r.ground_pressure_pa, r.crc
    return c


def record_to_bytes(r):
    return struct.pack(RECORD_FORMAT, r.magic, r.version, r.boot_count, r.last_state, r.one_shot_flags,
                             r.t_release_ms, r.ground_pressure_pa, r.crc)


def record_from_bytes(b):
    """Return a RecoveryRecord, or None if the length is wrong (validation is restore_on_boot's job)."""
    if b is None or len(b) != RECORD_SIZE:
        return None
    r = T.RecoveryRecord()
    (r.magic, r.version, r.boot_count, r.last_state, r.one_shot_flags, r.t_release_ms,
     r.ground_pressure_pa, r.crc) = struct.unpack(RECORD_FORMAT, b)
    return r


class RestoreResult:
    def __init__(self):
        self.had_record = False
        self.corrupt = False
        self.resumed = False  # True when resuming an in-flight state
        self.state = T.STATE_POWER_ON_SELF_CHECK
        self.one_shot_flags = 0
        self.has_ground = False
        self.ground_pressure_pa = 0.0
        self.boot_count = 1


class RecoveryManager:
    def __init__(self, store):
        self._store = store
        self._rec = T.RecoveryRecord()

    def restore_on_boot(self):
        """Load and validate the record, increment boot_count and save it back."""
        res = RestoreResult()
        have, loaded = self._store.load()
        res.had_record = have
        sane = (have and loaded is not None and loaded.magic == RECOVERY_MAGIC and
                loaded.version == RECOVERY_VERSION and loaded.crc == recovery_crc(loaded) and
                T.is_valid_flight_state_code(loaded.last_state))
        if have and not sane:
            res.corrupt = True

        rec = T.RecoveryRecord()
        rec.magic = RECOVERY_MAGIC
        rec.version = RECOVERY_VERSION
        rec.boot_count = u16(loaded.boot_count + 1) if sane else 1
        rec.last_state = T.STATE_POWER_ON_SELF_CHECK

        if sane and loaded.last_state >= T.STATE_ASCENT:
            res.resumed = True
            res.state = loaded.last_state
            res.one_shot_flags = loaded.one_shot_flags
            res.has_ground = loaded.ground_pressure_pa > 0.0
            res.ground_pressure_pa = loaded.ground_pressure_pa
            rec.last_state = loaded.last_state
            rec.one_shot_flags = loaded.one_shot_flags
            rec.ground_pressure_pa = loaded.ground_pressure_pa
        res.boot_count = rec.boot_count
        rec.crc = recovery_crc(rec)
        self._rec = rec
        self._store.save(copy_record(rec))
        return res

    def persist(self, state, one_shot_flags):
        """Persist the current state. Returns False on write failure."""
        self._rec.last_state = state
        self._rec.one_shot_flags = one_shot_flags
        self._rec.crc = recovery_crc(self._rec)
        return self._store.save(copy_record(self._rec))

    def set_ground_pressure(self, pa):
        self._rec.ground_pressure_pa = f32(pa)

    def record(self):
        return self._rec
