# Integration: flight node (real drivers on fake I2C) -> fake radio -> ground
# station; sensor-failure propagation; communication-failure isolation; the
# EXISTING flight software in the loop. SIMULATED / LOGIC ONLY - no ESP32, no RF.
import io
import types
import unittest

import fakes
from fakes import FLIGHT_MAC, GROUND_MAC, FakeI2C, flight_cfg, full_bus, radio_pair
import cs_display
import cs_link as L
import cs_proto as P
from cs_flight import BringupState, FlightNode, RefusedState
from cs_sensors import SensorSuite

PERIOD = 250


class CountingState(BringupState):
    """Stands in for the flight software: counts ticks, reports a fixed state."""
    running = True

    def __init__(self):
        self.ticks = 0

    def tick(self, suite, now, uptime_ms):
        self.ticks += 1

    def state(self):
        return 3

    def fault(self):
        return 0x40000


class Bench:
    def __init__(self, devices=None, state=None, cfg=None):
        self.air, self.fr, self.gr = radio_pair()
        self.i2c = FakeI2C(devices if devices is not None else full_bus())
        self.cfg = cfg or flight_cfg()
        self.now = 0
        self.suite = SensorSuite(self.cfg).discover(self.i2c, 0)
        self.link = L.FlightLink(self.fr, GROUND_MAC, 0x1234, 0, PERIOD, 500, 1000, 2000)
        self.state = state or BringupState()
        self.node = FlightNode(self.suite, self.link, self.state, 0)
        self.ground = L.GroundLink(self.gr, FLIGHT_MAC, 1000, 3000)
        self.rx = []

    def run(self, ms, step=10):
        end = self.now + ms
        while self.now < end:
            self.node.step(self.now)
            self.rx += self.ground.poll(self.now, self.now)
            self.now += step


class EndToEnd(unittest.TestCase):
    def test_sensor_readings_reach_ground_station(self):
        b = Bench()
        b.run(3000)
        self.assertGreaterEqual(len(b.rx), 11)
        t = b.rx[-1]
        self.assertEqual(t.state, P.STATE_NO_FSW)
        self.assertFalse(t.flags & P.F_FSW_RUNNING)
        self.assertTrue(t.flags & P.F_POWER_GATED)
        self.assertTrue(t.flags & P.F_ALT_REF_AUTO)
        for bit in (P.V_BARO1, P.V_BARO2, P.V_ALT, P.V_ACCEL, P.V_GYRO, P.V_IMU_TEMP):
            self.assertTrue(t.has(bit), bit)
        self.assertFalse(t.has(P.V_BUS_V))       # INA219 gated: no invented voltage/current
        self.assertFalse(t.has(P.V_CURRENT))
        self.assertAlmostEqual(t.p1_pa, 100653.3, delta=0.1)
        self.assertAlmostEqual(t.accel_g[2], 1.0, places=3)
        self.assertEqual(t.status, [P.ST_OK, P.ST_OK, P.ST_OK, P.ST_DISABLED, P.ST_DISABLED])
        self.assertEqual(b.ground.stats.lost, 0)
        self.assertEqual(b.link.state(b.now), P.LINK_UP)
        text = cs_display.render(b.ground, b.now, b.now)
        for s in ("LINK OK", "NO_FSW", "baro1 [OK]", "100653.3 Pa", "power [DISABLED]", "loss 0.0%"):
            self.assertIn(s, text)
        line = cs_display.csv_line(t)
        self.assertEqual(len(line.split(",")), len(cs_display.CSV_HEADER.split(",")))

    def test_ina219_measurements_when_declared_connected(self):
        b = Bench(cfg=flight_cfg(INA219_BUS_CONNECTED=True, INA219_SHUNT_CONNECTED=True))
        b.run(1000)
        t = b.rx[-1]
        self.assertTrue(t.has(P.V_BUS_V) and t.has(P.V_CURRENT))
        self.assertAlmostEqual(t.current_ma, 123.4, places=3)
        self.assertFalse(t.flags & P.F_POWER_GATED)

    def test_display_before_any_data(self):
        air, fr, gr = radio_pair()
        g = L.GroundLink(gr, FLIGHT_MAC, 1000, 3000)
        self.assertIn("no valid telemetry", cs_display.render(g, 0))
        self.assertIn("NO_DATA", cs_display.render(g, 0))


class SensorFailurePropagation(unittest.TestCase):
    def test_imu_failure_visible_on_ground_others_unaffected(self):
        b = Bench()
        b.run(1000)
        b.i2c.fail_regs.add((0x68, None))
        b.run(1000)
        t = b.rx[-1]
        self.assertFalse(t.has(P.V_ACCEL))
        self.assertIn(t.status[2], (P.ST_READ_ERROR, P.ST_INIT_FAILED))
        self.assertTrue(t.has(P.V_BARO1))
        b.i2c.fail_regs.clear()
        b.run(3000)                                # retried and recovered
        self.assertTrue(b.rx[-1].has(P.V_ACCEL))

    def test_missing_barometer_flags_duplicate_suspicion(self):
        bus = full_bus()
        del bus[0x77]
        b = Bench(bus)
        b.run(600)
        t = b.rx[-1]
        self.assertTrue(t.flags & P.F_BARO_DUP_SUSPECT)
        self.assertEqual(t.status[1], P.ST_NOT_PRESENT)
        self.assertFalse(t.has(P.V_BARO2))

    def test_stale_reading_is_not_sent_as_valid(self):
        b = Bench()
        b.run(500)
        b.suite.sample = lambda now, t: None      # sensors stop updating (stuck loop)
        b.run(1000)
        self.assertFalse(b.rx[-1].has(P.V_BARO1))
        self.assertFalse(b.rx[-1].has(P.V_ACCEL))


class CommunicationFailureIsolation(unittest.TestCase):
    def test_state_source_keeps_ticking_with_radio_dead(self):
        st = CountingState()
        b = Bench(state=st)
        b.fr.send_raises = OSError("ESP_ERR_ESPNOW_NO_MEM")
        b.fr.recv_raises = OSError("radio gone")
        b.run(5000)
        self.assertEqual(st.ticks, 100)                 # every 50 ms sample still reached the state source
        self.assertEqual(b.node.state_ticks, 100)
        self.assertEqual(b.link.stats.sent, 0)
        self.assertEqual(b.link.stats.send_errors, 20)
        self.assertEqual(b.node.link_exceptions, 0)     # contained inside the link layer
        self.assertEqual(b.link.state(b.now), P.LINK_DOWN)
        self.assertGreater(b.fr.recovers, 0)

    def test_even_a_crashing_link_layer_cannot_stop_the_state_source(self):
        st = CountingState()
        b = Bench(state=st)

        def boom(now):
            raise RuntimeError("bug in link")
        b.link.poll = boom
        b.run(1000)
        self.assertEqual(st.ticks, 20)
        self.assertEqual(b.node.link_exceptions, 100)

    def test_link_recovers_after_temporary_loss(self):
        b = Bench(state=CountingState())
        b.run(1000)
        b.air.blackout = True
        b.run(3000)
        self.assertEqual(b.link.state(b.now), P.LINK_DOWN)
        b.air.blackout = False
        b.run(3000)
        self.assertEqual(b.link.state(b.now), P.LINK_UP)
        self.assertEqual(b.ground.status(b.now), L.GS_OK)
        self.assertGreater(b.ground.stats.lost, 0)
        t = b.rx[-1]
        self.assertEqual((t.state, t.fault), (3, 0x40000))
        self.assertTrue(t.flags & P.F_FSW_RUNNING)

    def test_sensor_exception_does_not_stop_telemetry(self):
        b = Bench()

        def boom(now, t):
            raise RuntimeError("bus driver bug")
        b.suite.sample = boom
        b.run(1000)
        self.assertGreater(b.node.sensor_exceptions, 0)
        self.assertGreaterEqual(len(b.rx), 3)


class RefusedFlightSoftware(unittest.TestCase):
    def test_refused_state_reported(self):
        b = Bench(state=RefusedState(["B4 unresolved hardware item: PIN_I2C_SDA"]))
        b.run(500)
        t = b.rx[-1]
        self.assertTrue(t.flags & P.F_FSW_REFUSED)
        self.assertFalse(t.flags & P.F_FSW_RUNNING)
        self.assertEqual(t.state, P.STATE_NO_FSW)


# ---------------------------------------------------------------------------
# The EXISTING MicroPython flight software in the loop (unchanged code)
# ---------------------------------------------------------------------------
from cansat.core import types as T                                    # noqa: E402
from cansat.mock.memory_log import MemoryLogSink                      # noqa: E402
from cansat.mock.persistent_store import MockPersistentStore          # noqa: E402
from cansat.sim.fsw_hook import FlightSoftwareHook                    # noqa: E402
from cansat.sim.runner import run as sim_run                          # noqa: E402
from cansat.sim.scenarios import all_synthetic_scenarios              # noqa: E402
from cansat.sim.synthetic_flight_params import CANDIDATE_POLICIES, synthetic_flight_params  # noqa: E402
import cs_fsw_bridge                                                  # noqa: E402
from cs_telemetry import build_telemetry                              # noqa: E402


class FswBridge(unittest.TestCase):
    def test_real_boot_checks_refuse_on_hardware(self):
        b = Bench()
        st = cs_fsw_bridge.start_flight_software(b.suite, 0, fakes.os.path.join(fakes.REPO, "micropython"),
                                                 params=synthetic_flight_params(CANDIDATE_POLICIES[0]),
                                                 store=MockPersistentStore(), target_hardware=True)
        self.assertTrue(st.refused)
        self.assertTrue(any("B4 unresolved hardware item: PIN_I2C_SDA" in r for r in st.reasons))
        self.assertTrue(any("flight parameters not approved" in r for r in st.reasons))

    def test_refuses_without_params_or_store_even_if_checks_pass(self):
        b = Bench()
        st = cs_fsw_bridge.start_flight_software(b.suite, 0, "/", boot_checks_fn=lambda *a: [])
        self.assertTrue(st.refused)
        self.assertEqual(len(st.reasons), 2)

    def test_frame_mapping_preserves_validity_and_freshness(self):
        b = Bench()
        b.run(200)
        f = cs_fsw_bridge.to_sensor_frame(b.suite)
        self.assertTrue(f.baro.valid and f.baro.comm_ok and f.baro.data_ready)
        self.assertAlmostEqual(f.baro.pressure_pa, b.suite.baro1.last.pressure_pa)
        self.assertTrue(f.imu.valid)
        self.assertAlmostEqual(f.imu.az_g, 1.0)
        self.assertFalse(f.power.valid)          # INA219 gated -> power invalid, never invented
        self.assertFalse(f.switches.valid)       # no switch driver (OD-051)

    def test_flight_software_runs_on_suite_data_and_its_state_is_telemetered(self):
        b = Bench()
        params = synthetic_flight_params(CANDIDATE_POLICIES[0])
        st = cs_fsw_bridge.start_flight_software(b.suite, 0, "/", params=params, store=MockPersistentStore(),
                                                 boot_checks_fn=lambda *a: [])
        self.assertFalse(st.refused)
        b.state = b.node.state_src = st
        b.run(3000)
        t = b.rx[-1]
        self.assertTrue(t.flags & P.F_FSW_RUNNING)
        self.assertEqual(t.state, st.fsw.state())
        self.assertEqual(t.fault, st.fsw.fault_mask())
        self.assertEqual(st.requests_drained, 0)
        # the fake bench has power gated, so the FSW must report the power fault (bit 2)
        self.assertTrue(t.fault & T.FAULT_POWER_INVALID)


class _FrameSuite:
    """Presents a cansat SensorFrame through the suite interface used by build_telemetry."""

    def __init__(self, frame):
        st = lambda s: P.ST_OK if s.valid else P.ST_READ_ERROR  # noqa: E731
        self.baro1 = types.SimpleNamespace(last=frame.baro, status=st(frame.baro))
        self.baro2 = types.SimpleNamespace(last=None, status=P.ST_NOT_PRESENT)
        self.imu = types.SimpleNamespace(last=frame.imu, status=st(frame.imu))
        self.power = types.SimpleNamespace(last=frame.power, status=st(frame.power))
        self.alt_m = None
        self.reference_auto = False
        self.baro_dup_suspect = False

    def power_gated(self):
        return False


class TelemetryTapHook(FlightSoftwareHook):
    """FlightSoftwareHook + telemetry after every tick, through a FlightLink."""

    def __init__(self, params, transport, ground=None):
        FlightSoftwareHook.__init__(self, params)
        self.link = L.FlightLink(transport, GROUND_MAC, 1, 0, PERIOD, 500, 1000, 2000)
        self.ground = ground
        self.sent_states = []
        self.rx = []

    def on_tick(self, frame, uptime_ms):
        cols = FlightSoftwareHook.on_tick(self, frame, uptime_ms)
        try:
            self.link.poll(uptime_ms)
            if self.fsw is not None and self.link.due(uptime_ms):
                t = build_telemetry(_FrameSuite(frame), uptime_ms, self.fsw.state(), self.fsw.fault_mask(),
                                    P.F_FSW_RUNNING, P.ST_DISABLED, 10 ** 9)
                if self.link.send_telemetry(uptime_ms, t):
                    self.sent_states.append(t.state)
            if self.ground is not None:
                self.rx += self.ground.poll(uptime_ms, uptime_ms)
        except Exception:
            pass
        return cols


def _sim(sc, hook):
    hook.set_store_faults(sc.store_faults)
    sink = MemoryLogSink()
    sim_run(sc, sink, hook)
    return sink.lines


class FswInTheLoopSimulation(unittest.TestCase):
    """All 17 SYNTHETIC scenarios: telemetry must not change a single FSW output line."""

    def test_dead_radio_never_changes_flight_software_behaviour(self):
        pol = CANDIDATE_POLICIES[0]
        for sc in all_synthetic_scenarios():
            ref = _sim(sc, FlightSoftwareHook(synthetic_flight_params(pol)))
            air, fr, gr = radio_pair()
            fr.send_raises = OSError("radio dead")
            fr.recv_raises = OSError("radio dead")
            tap = TelemetryTapHook(synthetic_flight_params(pol), fr)
            got = _sim(sc, tap)
            self.assertEqual(ref, got, sc.name)
            self.assertEqual(tap.link.stats.sent, 0)

    def test_ground_decodes_flight_states_and_detects_resets(self):
        pol = CANDIDATE_POLICIES[0]
        for sc in all_synthetic_scenarios():
            air, fr, gr = radio_pair()
            ground = L.GroundLink(gr, FLIGHT_MAC, 1000, 3000)
            tap = TelemetryTapHook(synthetic_flight_params(pol), fr, ground)
            ref = _sim(sc, FlightSoftwareHook(synthetic_flight_params(pol)))
            self.assertEqual(ref, _sim(sc, tap), sc.name)
            self.assertEqual([t.state for t in tap.rx], tap.sent_states, sc.name)
            self.assertGreater(len(tap.rx), 0)
            self.assertEqual(ground.stats.rejected_total(), 0)


if __name__ == "__main__":
    unittest.main()
