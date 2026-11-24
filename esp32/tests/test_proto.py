# Protocol v1: serialization, deserialization, validation. LOGIC ONLY (laptop).
import struct
import unittest

import fakes  # noqa: F401 - sets sys.path
import cs_proto as P


def full_sample():
    t = P.Telemetry()
    t.boot_id, t.seq, t.uptime_ms, t.state, t.link = 0xBEEF, 41, 123456, 3, P.LINK_UP
    t.fault, t.flags = 0x7FFFF, P.F_FSW_RUNNING | P.F_ALT_REF_AUTO
    t.status = [P.ST_OK, P.ST_OK, P.ST_OK, P.ST_OK, P.ST_DISABLED]
    t.p1_pa, t.t1_c, t.p2_pa, t.t2_c, t.alt_m = 100653.27, 25.08, 100650.1, 24.9, 12.34
    t.accel_g, t.gyro_dps, t.imu_temp_c = (0.012, -0.98, 1.001), (1.5, -2.0, 250.0), 30.12
    t.bus_v, t.shunt_mv, t.current_ma = 3.712, 12.34, 123.4
    t.acked_seq, t.tx_fail, t.ack_miss, t.ack_rssi = 40, 2, 3, -61
    t.valid = P.V_ALL
    return t


class Crc(unittest.TestCase):
    def test_crc16_ccitt_false_check_value(self):
        self.assertEqual(P.crc16_ccitt(b"123456789"), 0x29B1)


class Telemetry(unittest.TestCase):
    def test_round_trip_all_fields(self):
        d = P.decode_telemetry(P.encode_telemetry(full_sample()))
        self.assertEqual((d.boot_id, d.seq, d.uptime_ms, d.state, d.link), (0xBEEF, 41, 123456, 3, P.LINK_UP))
        self.assertEqual(d.fault, 0x7FFFF)  # bits 16-18 survive (OD-072: the uint16 proposal would lose them)
        self.assertEqual(d.valid, P.V_ALL)
        self.assertAlmostEqual(d.p1_pa, 100653.3, places=1)
        self.assertAlmostEqual(d.t1_c, 25.08, places=2)
        self.assertAlmostEqual(d.alt_m, 12.34, places=2)
        self.assertEqual(d.accel_g, (0.012, -0.98, 1.001))
        self.assertEqual(d.gyro_dps, (1.5, -2.0, 250.0))
        self.assertAlmostEqual(d.bus_v, 3.712, places=3)
        self.assertAlmostEqual(d.current_ma, 123.4, places=3)
        self.assertAlmostEqual(d.shunt_mv, 12.34, places=2)
        self.assertEqual((d.acked_seq, d.tx_fail, d.ack_miss, d.ack_rssi), (40, 2, 3, -61))
        self.assertEqual(d.implausible, [])

    def test_frame_is_deterministic_and_fits_espnow(self):
        a = P.encode_telemetry(full_sample())
        self.assertEqual(a, P.encode_telemetry(full_sample()))
        self.assertEqual(len(a), P.TLM_LEN)
        self.assertLessEqual(P.TLM_LEN, P.ESPNOW_MAX_PAYLOAD)
        self.assertLessEqual(P.ACK_LEN, P.ESPNOW_MAX_PAYLOAD)

    def test_missing_values_are_zero_with_validity_cleared(self):
        t = P.Telemetry()
        t.valid = P.V_ALL       # claims everything, but no values were filled in
        d = P.decode_telemetry(P.encode_telemetry(t))
        self.assertEqual(d.valid, 0)
        self.assertIsNone(d.p1_pa)
        self.assertIsNone(d.accel_g)

    def test_unrepresentable_values_are_invalidated_not_clamped(self):
        t = full_sample()
        t.accel_g = (40.0, 0.0, 0.0)          # > 32.767 g does not fit int16 milli-g
        t.t1_c = float("nan")
        t.current_ma = float("inf")
        d = P.decode_telemetry(P.encode_telemetry(t))
        self.assertFalse(d.has(P.V_ACCEL))
        self.assertFalse(d.has(P.V_BARO1))
        self.assertFalse(d.has(P.V_CURRENT))
        self.assertTrue(d.has(P.V_GYRO))
        self.assertIsNone(d.accel_g)

    def test_implausible_sensor_value_is_flagged_but_frame_kept(self):
        t = full_sample()
        t.p1_pa = 5000.0                      # below the BMP280 range
        t.imu_temp_c = 150.0
        d = P.decode_telemetry(P.encode_telemetry(t))
        self.assertIn("baro1", d.implausible)
        self.assertIn("imu_temp", d.implausible)
        self.assertFalse(d.has(P.V_BARO1))
        self.assertIsNone(d.p1_pa)
        self.assertTrue(d.has(P.V_BARO2))     # other sensors unaffected
        self.assertTrue(d.has(P.V_ACCEL))


class Rejection(unittest.TestCase):
    def reject(self, data, reason):
        with self.assertRaises(P.ProtocolError) as cm:
            P.decode_telemetry(data)
        self.assertEqual(cm.exception.reason, reason)

    def test_short_and_non_bytes(self):
        self.reject(b"", P.R_SHORT)
        self.reject(b"CS\x01", P.R_SHORT)
        self.reject("not bytes", P.R_SHORT)

    def test_bad_magic(self):
        f = bytearray(P.encode_telemetry(full_sample()))
        f[0] = ord("X")
        self.reject(bytes(f), P.R_MAGIC)

    def test_wrong_protocol_version_rejected_before_crc(self):
        f = bytearray(P.encode_telemetry(full_sample()))
        f[2] = 2
        self.reject(bytes(f), P.R_VERSION)

    def test_unknown_type(self):
        f = bytearray(P.encode_telemetry(full_sample()))
        f[3] = 9
        self.reject(bytes(f), P.R_TYPE)

    def test_wrong_length(self):
        f = P.encode_telemetry(full_sample())
        self.reject(f[:-3] + f[-2:], P.R_LENGTH)
        self.reject(f + b"\x00", P.R_LENGTH)

    def test_every_single_bit_flip_is_rejected(self):
        f = P.encode_telemetry(full_sample())
        for i in range(len(f)):
            for bit in range(8):
                g = bytearray(f)
                g[i] ^= 1 << bit
                with self.assertRaises(P.ProtocolError):
                    P.decode_telemetry(bytes(g))

    def _recrc(self, body_mutator):
        f = bytearray(P.encode_telemetry(full_sample()))
        body_mutator(f)
        f[-2:] = struct.pack("<H", P.crc16_ccitt(bytes(f[:-2])))
        return bytes(f)

    def test_invalid_state_code_with_good_crc(self):
        off = P.HDR_LEN + 8
        self.reject(self._recrc(lambda f: f.__setitem__(off, 99)), P.R_FIELD)

    def test_invalid_status_code_with_good_crc(self):
        off = P.HDR_LEN + 18
        self.reject(self._recrc(lambda f: f.__setitem__(off, 200)), P.R_FIELD)

    def test_undefined_validity_bits_with_good_crc(self):
        off = P.HDR_LEN + 10
        self.reject(self._recrc(lambda f: f.__setitem__(off + 1, 0x80)), P.R_FIELD)

    def test_ack_is_not_telemetry_and_vice_versa(self):
        a = P.encode_ack(P.Ack(1, 2))
        self.reject(a, P.R_TYPE)
        with self.assertRaises(P.ProtocolError):
            P.decode_ack(P.encode_telemetry(full_sample()))


class AckFrames(unittest.TestCase):
    def test_round_trip(self):
        a = P.decode_ack(P.encode_ack(P.Ack(0x1234, 77, 5000, 70, 7, 3, -70)))
        self.assertEqual((a.boot_id, a.ack_seq, a.gs_uptime_ms, a.rx_ok, a.lost, a.rejected, a.rssi),
                         (0x1234, 77, 5000, 70, 7, 3, -70))

    def test_unknown_rssi(self):
        self.assertIsNone(P.decode_ack(P.encode_ack(P.Ack(1, 1))).rssi)


if __name__ == "__main__":
    unittest.main()
