# Module 1: HAL interfaces mirror the C++ set; unimplemented methods fail loudly.
import unittest

from cansat.hal import interfaces as I
from tests import cpp_ref

CPP_TO_PY = {"IClock": "Clock", "IBarometer": "Barometer", "IImu": "Imu", "IPowerMonitor": "PowerMonitor",
             "IDigitalInputs": "DigitalInputs", "ISerialLink": "SerialLink", "ILogSink": "LogSink",
             "IPersistentStore": "PersistentStore", "IActuatorDriver": "ActuatorDriver",
             "IConnectionAssessmentSource": "ConnectionAssessmentSource", "IArmingSource": "ArmingSource",
             "IEventSink": "EventSink"}


class Interfaces(unittest.TestCase):
    def test_same_interface_set_as_cpp(self):
        h = cpp_ref.read("lib/hal/HalInterfaces.h")
        cpp = sorted(l.split()[1] for l in h.split("\n") if l.startswith("class I"))
        self.assertEqual(cpp, sorted(CPP_TO_PY))
        for py in CPP_TO_PY.values():
            self.assertTrue(hasattr(I, py), py)

    def test_unimplemented_methods_raise(self):
        calls = [(I.Clock(), "now_ms", ()), (I.Barometer(), "begin", ()), (I.Barometer(), "read", ()),
                 (I.Imu(), "read", ()), (I.PowerMonitor(), "read", ()), (I.DigitalInputs(), "read", ()),
                 (I.SerialLink(), "write", (b"x",)), (I.SerialLink(), "read", ()),
                 (I.LogSink(), "append", ("x",)), (I.LogSink(), "flush", ()),
                 (I.PersistentStore(), "load", ()), (I.PersistentStore(), "save", (None,)),
                 (I.ActuatorDriver(), "apply", (1,)), (I.ActuatorDriver(), "is_physical", ()),
                 (I.ConnectionAssessmentSource(), "assess", (0,)), (I.ArmingSource(), "read", (0,)),
                 (I.EventSink(), "on_event", (None,))]
        for obj, name, args in calls:
            with self.subTest(cls=type(obj).__name__, method=name):
                with self.assertRaises(NotImplementedError):
                    getattr(obj, name)(*args)


if __name__ == "__main__":
    unittest.main()
