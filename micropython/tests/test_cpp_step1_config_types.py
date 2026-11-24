# One-to-one port of firmware/test/test_step1_config_types.cpp (14 cases):
# config, common types and interfaces. SYNTHETIC_* values are test-only.
import unittest

from cansat.config import build_flags, flight_params as FP, hardware_config as hw
from cansat.core import types as T
from cansat.core.num import f32
from cansat.core.param import KIND_FLOAT, Param
from cansat.hal import interfaces as I

SYNTHETIC_DEBOUNCE_MS = 11
SYNTHETIC_FREEFALL_G = 0.123
SYNTHETIC_FREEFALL_MS = 22
SYNTHETIC_BARO_DROP_M = 3.21
SYNTHETIC_BARO_WINDOW_MS = 333
SYNTHETIC_CONFIRM_MS = 444
SYNTHETIC_STALE_MS = 555
SYNTHETIC_SEPARATION_MS = 666
SYNTHETIC_FALLBACK_MS = 777


def synthetic_release_params():
    p = FP.ReleaseParams()
    p.switch_debounce_ms.set(SYNTHETIC_DEBOUNCE_MS)
    p.switch1_open_is_high.set(True)
    p.switch2_open_is_high.set(True)
    p.switch_vote.set(FP.SWITCH_VOTE_ANY)
    p.freefall_accel_max_g.set(SYNTHETIC_FREEFALL_G)
    p.freefall_min_ms.set(SYNTHETIC_FREEFALL_MS)
    p.baro_min_drop_m.set(SYNTHETIC_BARO_DROP_M)
    p.baro_window_ms.set(SYNTHETIC_BARO_WINDOW_MS)
    p.confirm_window_ms.set(SYNTHETIC_CONFIRM_MS)
    p.sample_stale_ms.set(SYNTHETIC_STALE_MS)
    return p


class Step1(unittest.TestCase):
    def test_build_flags_default_to_native_and_actuators_disabled(self):
        self.assertIs(build_flags.TARGET_HARDWARE, False)
        self.assertIs(build_flags.PHYSICAL_ACTUATORS_ENABLED, False)

    def test_all_pins_are_tbd_and_hardware_unresolved(self):
        for name in ("PIN_I2C_SDA", "PIN_I2C_SCL", "PIN_HC12_TX", "PIN_HC12_RX", "PIN_HC12_SET", "PIN_SD_SCK",
                     "PIN_SD_MISO", "PIN_SD_MOSI", "PIN_SD_CS", "PIN_SWITCH_1", "PIN_SWITCH_2", "PIN_BUZZER_1",
                     "PIN_BUZZER_2", "PIN_SERVO_1", "PIN_SERVO_2", "PIN_SERVO_3"):
            self.assertEqual(getattr(hw, name), hw.PIN_TBD, name)
        self.assertEqual(hw.HC12_UART_BAUD, 0)
        self.assertFalse(hw.required_hardware_resolved())

    def test_i2c_addresses_match_team_reported_baseline(self):
        self.assertEqual((hw.BMP280_ADDR_CANDIDATE_A, hw.BMP280_ADDR_CANDIDATE_B, hw.MPU6050_ADDR, hw.INA219_ADDR),
                         (0x76, 0x77, 0x68, 0x40))
        self.assertEqual(hw.GROUND_STATION_USB_BAUD, 115200)

    def test_param_starts_unset_and_get_fails(self):
        p = Param(KIND_FLOAT)
        self.assertFalse(p.is_set())
        self.assertEqual(p.get(), (False, None))  # no fallback value leaks out
        p.set(1.5)
        self.assertTrue(p.is_set())
        self.assertEqual(p.get(), (True, 1.5))
        p.clear()
        self.assertFalse(p.is_set())

    def test_default_flight_params_are_incomplete(self):
        fp = FP.FlightParams()
        self.assertFalse(fp.release.is_complete() or fp.interlock.is_complete() or fp.is_complete())

    def test_release_params_complete_only_when_every_field_set(self):
        self.assertTrue(synthetic_release_params().is_complete())
        for field in ("switch_debounce_ms", "switch1_open_is_high", "switch2_open_is_high", "switch_vote",
                      "freefall_accel_max_g", "freefall_min_ms", "baro_min_drop_m", "baro_window_ms",
                      "confirm_window_ms", "sample_stale_ms"):
            p = synthetic_release_params()
            getattr(p, field).clear()
            self.assertFalse(p.is_complete(), field)
        p = synthetic_release_params()
        p.switch_vote.set(FP.SWITCH_VOTE_UNSET)
        self.assertFalse(p.is_complete())

    def test_stuck_switch_policy_has_no_default_and_unset_is_invalid(self):
        ip = FP.InterlockParams()
        self.assertFalse(ip.stuck_switch_policy.get()[0])
        ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS)
        self.assertFalse(ip.is_complete())
        ip.stuck_switch_policy.set(FP.POLICY_UNSET)
        self.assertFalse(ip.is_complete())

    def test_persist_failure_policy_has_no_default_and_unset_is_invalid(self):
        ip = FP.InterlockParams()
        ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS)
        ip.stuck_switch_policy.set(FP.POLICY_STRICT_SWITCH_VETO)
        self.assertFalse(ip.is_complete())
        ip.persist_failure_policy.set(FP.PERSIST_UNSET)
        self.assertFalse(ip.is_complete())
        ip.persist_failure_policy.set(FP.PERSIST_WITHHOLD_UNTIL_PERSISTED)
        self.assertTrue(ip.is_complete())
        fp = FP.FlightParams()
        self.assertFalse(fp.validation.is_complete() or fp.transitions.is_complete())

    def test_every_candidate_policy_is_expressible_for_side_by_side_simulation(self):
        for c in (FP.POLICY_STRICT_SWITCH_VETO, FP.POLICY_SENSOR_OVERRIDE, FP.POLICY_VOTE_2_OF_3,
                  FP.POLICY_DELAYED_FALLBACK):
            ip = FP.InterlockParams()
            ip.min_separation_ms.set(SYNTHETIC_SEPARATION_MS)
            ip.persist_failure_policy.set(FP.PERSIST_REQUEST_ANYWAY)
            ip.stuck_switch_policy.set(c)
            if c == FP.POLICY_DELAYED_FALLBACK:
                self.assertFalse(ip.is_complete())  # fallback delay required for this policy
                ip.fallback_delay_ms.set(SYNTHETIC_FALLBACK_MS)
            self.assertTrue(ip.is_complete(), c)

    def test_flight_states_match_pdr_slide19_numbering(self):
        self.assertEqual([T.STATE_POWER_ON_SELF_CHECK, T.STATE_READY_ON_DRONE, T.STATE_ASCENT,
                          T.STATE_RELEASE_DETECTED, T.STATE_PARACHUTE_DEPLOY, T.STATE_PANEL_DEPLOY,
                          T.STATE_DESCENT, T.STATE_LANDED], list(range(1, 9)))
        self.assertEqual(T.state_name(T.STATE_RELEASE_DETECTED), "RELEASE_DETECTED")
        self.assertEqual(T.state_name(99), "INVALID")
        self.assertFalse(T.is_valid_flight_state_code(0))
        self.assertTrue(T.is_valid_flight_state_code(8))
        self.assertFalse(T.is_valid_flight_state_code(9))

    def test_default_samples_are_invalid(self):
        f = T.SensorFrame()
        self.assertFalse(f.baro.valid or f.imu.valid or f.imu.saturated or f.power.valid or f.switches.valid)

    def test_fault_bits_are_distinct(self):
        acc = 0
        for b in (T.FAULT_BARO_INVALID, T.FAULT_IMU_INVALID, T.FAULT_POWER_INVALID, T.FAULT_SWITCH_INVALID,
                  T.FAULT_IMU_SATURATED, T.FAULT_LOG_WRITE, T.FAULT_PERSIST_WRITE, T.FAULT_RECOVERY_RECORD_CORRUPT,
                  T.FAULT_SELF_CHECK, T.FAULT_RELEASE_DEGRADED, T.FAULT_PARAMS_INCOMPLETE, T.FAULT_LOW_BATTERY):
            self.assertEqual(b & (b - 1), 0)  # single bit
            self.assertEqual(acc & b, 0)      # not reused
            acc |= b

    def test_LIMITATION_state_event_command_are_not_distinct_types(self):
        # C++ checks at compile time that FlightState, EventType, ActuatorRequest and
        # ActuatorDecision are distinct, non-convertible types. Python cannot express
        # this (plain int codes, D-019): codes from different sets compare equal, so a
        # mix-up is NOT caught by the language. This test pins that limitation.
        self.assertEqual(T.STATE_POWER_ON_SELF_CHECK, T.REQ_RELEASE_PARACHUTE)
        self.assertEqual(T.EV_SELF_CHECK_PASS, T.DEC_EXECUTED_SIMULATED)
        # What remains checkable: the name tables are separate.
        self.assertNotEqual(T.state_name(1), T.request_name(1))
        self.assertNotEqual(T.event_name(1), T.decision_name(1))

    def test_hal_interfaces_are_abstract_and_implementable(self):
        for cls in (I.Clock, I.Barometer, I.Imu, I.PowerMonitor, I.DigitalInputs, I.SerialLink, I.LogSink,
                    I.PersistentStore, I.ActuatorDriver, I.EventSink):
            obj = cls()
            meth = [m for m in ("now_ms", "read", "write", "append", "load", "apply", "on_event") if hasattr(obj, m)]
            self.assertTrue(meth, cls.__name__)

        class FakeClock(I.Clock):
            t = 0

            def now_ms(self):
                return self.t

        class CountingActuator(I.ActuatorDriver):
            calls = 0

            def apply(self, r):
                self.calls += 1

            def is_physical(self):
                return False

        c = FakeClock()
        c.t = 1234
        self.assertEqual(c.now_ms(), 1234)
        self.assertIs(CountingActuator().is_physical(), False)


if __name__ == "__main__":
    unittest.main()
