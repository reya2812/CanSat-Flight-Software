# interfaces.py - hardware abstraction layer interfaces.  (port of lib/hal/HalInterfaces.h)
#
# Core logic depends only on these. Implementations:
#   cansat/mock/   laptop tests and simulation (CPython)
#   cansat/hal_mp/ real MicroPython drivers (later; requires resolved hardware_config)
# Portable: base classes only, no MicroPython imports. Methods raise
# NotImplementedError so a missing override fails loudly (C++: pure virtual).
#
# [TEAM DECISION] ActuatorDriver gets MOCK implementations only (D-017, OD-059).
# No servo or buzzer output code exists in this port.


class Clock:
    def now_ms(self):
        """Monotonic ms since boot as a uint32 that wraps after ~49.7 days (as C++)."""
        raise NotImplementedError


class Barometer:
    def begin(self):
        """False = not detected / init failed (self-check input)."""
        raise NotImplementedError

    def read(self):
        """Return a types.BaroSample."""
        raise NotImplementedError


class Imu:
    def begin(self):
        raise NotImplementedError

    def read(self):
        """Return a types.ImuSample."""
        raise NotImplementedError


class PowerMonitor:
    def begin(self):
        raise NotImplementedError

    def read(self):
        """Return a types.PowerSample."""
        raise NotImplementedError


class DigitalInputs:
    def read(self):
        """Return a types.SwitchSample with raw electrical levels; debounce is core logic."""
        raise NotImplementedError


class SerialLink:
    """Byte transport (HC-12 UART on hardware; capture/corrupt/drop in tests)."""

    def write(self, data):
        """Write bytes; return the number of bytes accepted."""
        raise NotImplementedError

    def read(self):
        """Next byte as an int 0-255, or -1 if none."""
        raise NotImplementedError


class LogSink:
    """Line-oriented log sink (SD card on hardware; file/memory in tests)."""

    def append(self, line):
        raise NotImplementedError

    def flush(self):
        raise NotImplementedError


class PersistentStore:
    """Small persistent record for reset recovery (NVS on hardware, [UNVERIFIED] brownout survival)."""

    def load(self):
        """Return (True, RecoveryRecord) or (False, None) when absent or unreadable."""
        raise NotImplementedError

    def save(self, rec):
        """Return True on success."""
        raise NotImplementedError


class ActuatorDriver:
    """Actuator output. Only ActuatorManager may call apply(), after its interlock.

    MOCK-ONLY (D-017). ActuatorManager refuses any driver whose is_physical()
    is True, and boot_checks refuses to start if one is registered.
    """

    def apply(self, request):
        raise NotImplementedError

    def is_physical(self):
        raise NotImplementedError


class ConnectionAssessmentSource:
    """Abstract connection assessment (OD-070). HOW it is formed is unresolved (OD-060/OD-068)."""

    def assess(self, now_ms):
        raise NotImplementedError


class ArmingSource:
    """Arming state for the deployment interlock. Source/procedure unresolved (OD-059)."""

    def read(self, now_ms):
        raise NotImplementedError


class EventSink:
    def on_event(self, e):
        raise NotImplementedError
