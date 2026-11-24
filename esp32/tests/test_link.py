# FlightLink / GroundLink: sequencing, ACKs, duplicates, gaps, timeouts,
# recovery. LOGIC ONLY with an in-memory radio (no ESP32, no RF).
import unittest

import fakes
from fakes import FLIGHT_MAC, GROUND_MAC, OTHER_MAC, radio_pair
import cs_link as L
import cs_proto as P
from cs_util import TICKS_PERIOD

PERIOD, ACK_TO, DOWN, RECOV = 250, 500, 1000, 2000


def tlm():
    t = P.Telemetry()
    t.valid = P.V_BARO1
    t.p1_pa, t.t1_c = 100000.0, 20.0
    return t


class Pair:
    def __init__(self, t0=0, boot_id=7):
        self.air, self.fr, self.gr = radio_pair()
        self.now = t0
        self.fl = L.FlightLink(self.fr, GROUND_MAC, boot_id, t0, PERIOD, ACK_TO, DOWN, RECOV)
        self.gl = L.GroundLink(self.gr, FLIGHT_MAC, stale_ms=1000, lost_ms=3000)
        self.received = []

    def step(self, ms=PERIOD):
        """flight sends if due, ground receives + acks, flight polls."""
        if self.fl.due(self.now):
            self.fl.send_telemetry(self.now, tlm())
        self.received += self.gl.poll(self.now, self.now)
        self.fl.poll(self.now)
        self.now = (self.now + ms) % TICKS_PERIOD

    def run(self, n, ms=PERIOD):
        for _ in range(n):
            self.step(ms)


class Nominal(unittest.TestCase):
    def test_sequence_ack_and_link_up(self):
        p = Pair()
        p.run(20)
        self.assertEqual([t.seq for t in p.received], list(range(20)))
        self.assertEqual(p.fl.stats.sent, 20)
        self.assertEqual(p.fl.stats.acked, 20)
        self.assertEqual(p.fl.stats.ack_missing, 0)
        self.assertEqual(p.fl.state(p.now), P.LINK_UP)
        self.assertEqual(p.gl.stats.lost, 0)
        self.assertEqual(p.gl.loss_percent(), 0.0)
        self.assertEqual(p.gl.status(p.now), L.GS_OK)
        self.assertEqual(p.fl.acked_seq, 19)
        self.assertEqual(p.received[-1].acked_seq, 18)     # telemetry reports the previous ack
        self.assertEqual(p.fl.last_ack_rssi, -55)

    def test_send_schedule_does_not_burst_after_a_stall(self):
        p = Pair()
        p.step()
        p.now += 10 * PERIOD          # main loop stalled for 10 periods
        p.step(1)
        p.step(1)
        self.assertEqual(p.fl.stats.sent, 2)   # one catch-up frame, not ten

    def test_works_across_tick_wraparound(self):
        p = Pair(t0=TICKS_PERIOD - 3 * PERIOD)
        p.run(12)
        self.assertEqual(p.fl.stats.acked, 12)
        self.assertEqual(p.fl.stats.ack_missing, 0)


class Loss(unittest.TestCase):
    def test_lost_telemetry_counted_as_gap_and_missing_ack(self):
        p = Pair()
        p.air.drop = lambda s, d, data: s == FLIGHT_MAC and P.decode_telemetry(data).seq in (3, 4)
        p.run(10)
        p.run(3)  # let timeouts expire
        self.assertEqual(p.gl.stats.lost, 2)
        self.assertEqual(p.fl.stats.ack_missing, 2)
        self.assertIn(p.fl.state(p.now), (P.LINK_DEGRADED, P.LINK_UP))
        self.assertAlmostEqual(p.gl.loss_percent(), 100.0 * 2 / 13)

    def test_lost_ack_counted_on_flight_side_only(self):
        p = Pair()
        p.air.drop = lambda s, d, data: s == GROUND_MAC and P.decode_ack(data).ack_seq == 5
        p.run(12)
        self.assertEqual(p.gl.stats.lost, 0)
        self.assertEqual(p.fl.stats.ack_missing, 1)
        self.assertEqual(p.fl.state(p.now), P.LINK_DEGRADED)  # a miss in the recent window
        p.run(10)
        self.assertEqual(p.fl.state(p.now), P.LINK_UP)        # window clean again

    def test_late_ack_after_timeout(self):
        p = Pair()
        held = []
        p.air.drop = lambda s, d, data: s == GROUND_MAC and P.decode_ack(data).ack_seq == 0 and not held.append(data)
        p.run(4)                                            # ack 0 held back past ACK_TO
        self.assertEqual(p.fl.stats.ack_missing, 1)
        p.fr.inbox.append((GROUND_MAC, held[0]))
        p.step()
        self.assertEqual(p.fl.stats.ack_late, 1)


class DuplicatesAndOrder(unittest.TestCase):
    def test_duplicate_frames_not_shown_twice_but_acked(self):
        p = Pair()
        p.air.duplicate = lambda s, d, data: s == FLIGHT_MAC
        p.run(5)
        self.assertEqual([t.seq for t in p.received], [0, 1, 2, 3, 4])
        self.assertEqual(p.gl.stats.duplicates, 5)
        self.assertEqual(p.gl.stats.acks_sent, 10)
        self.assertEqual(p.fl.stats.ack_unknown, 5)    # second ack for an already-acked seq

    def test_out_of_order_frame_fills_gap(self):
        p = Pair()
        held = []
        p.air.drop = lambda s, d, data: (s == FLIGHT_MAC and P.decode_telemetry(data).seq == 2
                                         and not held.append(data))
        p.run(5)
        self.assertEqual(p.gl.stats.lost, 1)
        p.gr.inbox.append((FLIGHT_MAC, held[0]))
        p.step()
        self.assertEqual(p.gl.stats.lost, 0)
        self.assertEqual(p.gl.stats.late, 1)
        self.assertIn(2, [t.seq for t in p.received])

    def test_reboot_of_flight_board_resets_sequence_tracking(self):
        p = Pair(boot_id=1)
        p.run(5)
        p.fl = L.FlightLink(p.fr, GROUND_MAC, 2, p.now, PERIOD, ACK_TO, DOWN, RECOV)
        p.run(3)
        self.assertEqual(p.gl.stats.reboots, 1)
        self.assertEqual(p.gl.stats.lost, 0)            # seq restart is not counted as loss
        self.assertEqual(p.gl.stats.duplicates, 0)
        self.assertEqual(p.gl.stats.rx_ok, 3)
        self.assertEqual(p.gl.stats.rx_total_ok, 8)

    def test_ack_for_other_boot_is_ignored(self):
        p = Pair(boot_id=5)
        p.fr.inbox.append((GROUND_MAC, P.encode_ack(P.Ack(boot_id=6, ack_seq=0))))
        p.run(1)
        self.assertEqual(p.fl.stats.ack_unknown, 1)


class Rejection(unittest.TestCase):
    def test_malformed_and_foreign_frames_rejected_and_counted(self):
        p = Pair()
        good = None
        p.run(2)
        good = p.air.log[0][2]
        bad_crc = bytearray(good)
        bad_crc[10] ^= 0xFF
        wrong_ver = bytearray(good)
        wrong_ver[2] = 7
        p.gr.inbox += [(FLIGHT_MAC, bytes(bad_crc)), (FLIGHT_MAC, bytes(wrong_ver)), (FLIGHT_MAC, b"garbage"),
                       (FLIGHT_MAC, b"garbage-garbage-garbage"), (OTHER_MAC, good)]
        before = len(p.received)
        p.gl.poll(p.now)
        self.assertEqual(len(p.received), before)
        self.assertEqual(p.gl.stats.rejected, {P.R_CRC: 1, P.R_VERSION: 1, P.R_SHORT: 1, P.R_MAGIC: 1})
        self.assertEqual(p.gl.stats.foreign, 1)

    def test_flight_side_rejects_malformed_acks(self):
        p = Pair()
        p.fr.inbox += [(GROUND_MAC, b"\x00" * 27), (OTHER_MAC, P.encode_ack(P.Ack(7, 0)))]
        p.fl.poll(0)
        self.assertEqual(p.fl.stats.rx_rejected, {P.R_MAGIC: 1})
        self.assertEqual(p.fl.stats.rx_foreign, 1)
        self.assertEqual(p.fl.stats.acked, 0)


class TimeoutAndRecovery(unittest.TestCase):
    def test_blackout_marks_link_down_and_triggers_bounded_recovery(self):
        p = Pair()
        p.run(8)
        self.assertEqual(p.fl.state(p.now), P.LINK_UP)
        p.air.blackout = True
        p.run(8)                                           # 2 s without any ack
        self.assertEqual(p.fl.state(p.now), P.LINK_DOWN)
        self.assertEqual(p.gl.status(p.now), L.GS_STALE)
        self.assertGreaterEqual(p.fr.recovers, 1)
        n = p.fr.recovers
        p.run(8)                                           # recovery rate-limited by RECOV
        self.assertLessEqual(p.fr.recovers - n, 2)
        self.assertEqual(p.gl.status(p.now), L.GS_LOST)
        p.air.blackout = False
        p.run(4)
        self.assertEqual(p.fl.state(p.now), P.LINK_DEGRADED)
        self.assertFalse(p.fl.recovering)
        self.assertEqual(p.gl.status(p.now), L.GS_OK)
        p.run(10)
        self.assertEqual(p.fl.state(p.now), P.LINK_UP)

    def test_recovering_flag_reported_in_telemetry(self):
        p = Pair()
        p.air.blackout = True
        p.run(6)
        p.air.blackout = False
        p.step()
        self.assertTrue(p.received[0].flags & P.F_LINK_RECOVERING)

    def test_no_ground_station_ever_goes_down(self):
        p = Pair()
        p.air.blackout = True
        self.assertEqual(p.fl.state(p.now), P.LINK_UNKNOWN)
        p.run(6)
        self.assertEqual(p.fl.state(p.now), P.LINK_DOWN)
        self.assertEqual(p.gl.status(p.now), L.GS_NO_DATA)

    def test_pending_table_is_bounded(self):
        p = Pair()
        p.air.blackout = True
        for _ in range(100):
            p.fl.send_telemetry(p.now, tlm())   # no time passes: nothing expires by timeout
        self.assertLessEqual(p.fl.pending_count(), 16)
        self.assertEqual(p.fl.stats.ack_missing, 84)


class TransportFaults(unittest.TestCase):
    def test_send_exceptions_and_false_are_counted_never_raised(self):
        p = Pair()
        p.fr.send_raises = OSError("ESP_ERR_ESPNOW_NO_MEM")
        p.run(3)
        p.fr.send_raises = None
        p.fr.send_returns = False
        p.run(2)
        self.assertEqual(p.fl.stats.send_errors, 5)
        self.assertEqual(p.fl.stats.sent, 0)
        p.fr.send_returns = True
        p.run(3)
        self.assertEqual(p.received[-1].tx_fail, 5)

    def test_recv_and_recover_exceptions_are_contained(self):
        p = Pair()
        p.fr.recv_raises = ValueError("boom")
        p.gr.recv_raises = OSError("boom")

        def bad_recover():
            raise OSError("reinit failed")
        p.fr.recover = bad_recover
        p.run(12)
        self.assertGreater(p.fl.stats.rx_errors, 0)
        self.assertGreater(p.gl.stats.rx_errors, 0)
        self.assertGreater(p.fl.stats.recover_errors, 0)

    def test_ack_send_failure_on_ground_is_counted(self):
        p = Pair()
        p.gr.send_raises = OSError("no mem")
        p.run(3)
        self.assertEqual(p.gl.stats.ack_errors, 3)
        self.assertEqual(len(p.received), 3)

    def test_bounded_receive_work_per_poll(self):
        p = Pair()
        frame = P.encode_ack(P.Ack(7, 999))
        p.fr.inbox += [(GROUND_MAC, frame)] * 50
        p.fl.poll(0)
        self.assertEqual(len(p.fr.inbox), 42)   # max_rx_per_poll = 8


if __name__ == "__main__":
    unittest.main()
