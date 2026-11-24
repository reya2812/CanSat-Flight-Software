# persistent_store.py - in-memory PersistentStore that survives simulated resets
# (models ESP32 NVS). Write-failure and corruption injection. [SIMULATED]
# (port of lib/hal_mock/MockPersistentStore.h). Stores COPIES, like the C++ struct copy.
from cansat.core.recovery_manager import copy_record
from cansat.hal.interfaces import PersistentStore


class MockPersistentStore(PersistentStore):
    def __init__(self):
        self._has = False
        self._rec = None
        self.fail_writes = False
        self.writes = 0

    def load(self):
        if not self._has:
            return False, None
        return True, copy_record(self._rec)

    def save(self, rec):
        self.writes += 1
        if self.fail_writes:
            return False
        self._rec = copy_record(rec)
        self._has = True
        return True

    def corrupt(self):
        self._rec.crc ^= 0xA5A5A5A5

    def erase(self):
        self._has = False

    def has(self):
        return self._has

    def record(self):
        return self._rec
