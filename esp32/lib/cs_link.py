# cs_link.py - transport-agnostic link logic for both ends (portable).
#
# FlightLink: periodic telemetry, acknowledgement tracking, loss statistics,
#             link state and radio recovery. Never blocks: every call does a
#             bounded amount of work and returns.
# GroundLink: validation, duplicate / gap / late detection, acknowledgements,
#             health. Never blocks either.
#
# A transport provides (cs_espnow.EspNowTransport on the board, fakes in tests):
#   send(mac, data) -> bool       may raise OSError; False/exception = not queued
#   recv()          -> (mac, data) or None when nothing is waiting (non-blocking)
#   rssi(mac)       -> int dBm or None
#   recover()       -> re-initialise the radio (may raise)
#
# Time is passed in as `now` ticks (cs_util.ticks_ms()); differences use ticks_diff.
import cs_proto as P
from cs_util import ticks_add, ticks_diff


def _inc(d, key):
    d[key] = d.get(key, 0) + 1


class FlightLinkStats:
    def __init__(self):
        self.sent = 0            # frames handed to the transport successfully
        self.send_errors = 0     # transport refused or raised
        self.encode_errors = 0
        self.acked = 0
        self.ack_missing = 0     # no ack within ack_timeout_ms
        self.ack_late = 0        # ack arrived after it had been counted missing
        self.ack_unknown = 0     # ack for a sequence number never sent / other boot
        self.rx_rejected = {}    # reason -> count (malformed frames)
        self.rx_foreign = 0      # frames from a MAC other than the ground station
        self.rx_errors = 0       # transport recv raised
        self.recoveries = 0
        self.recover_errors = 0
        self.rtt_last_ms = None
        self.ground_rx_ok = None  # ground's own counters, from the last ack
        self.ground_lost = None


class FlightLink:
    RECENT = 8  # outcomes remembered for the DEGRADED decision

    def __init__(self, transport, ground_mac, boot_id, now, period_ms, ack_timeout_ms, link_down_ms,
                 recovery_interval_ms, max_pending=16, max_rx_per_poll=8):
        if ack_timeout_ms <= 0 or period_ms <= 0 or link_down_ms <= 0:
            raise ValueError("link timings must be positive")
        self._t = transport
        self._peer = bytes(ground_mac)
        self.boot_id = boot_id & 0xFFFF
        self._period = period_ms
        self._ack_timeout = ack_timeout_ms
        self._down_ms = link_down_ms
        self._recov_ms = recovery_interval_ms
        self._max_pending = max_pending
        self._max_rx = max_rx_per_poll
        self.next_seq = 0
        self._next_due = now
        self._start = now
        self._pending = {}      # seq -> sent ticks
        self._order = []        # seqs in send order (oldest first)
        self._expired = []      # recently expired seqs, for late-ack detection
        self._recent = []       # 1 = acked, 0 = missing
        self._last_ack = None   # ticks of the last valid ack
        self._last_recover = None
        self.recovering = False
        self.acked_seq = P.NO_SEQ
        self.last_ack_rssi = None
        self.stats = FlightLinkStats()

    # ---- state ----
    def state(self, now):
        if self._last_ack is None:
            return P.LINK_DOWN if ticks_diff(now, self._start) > self._down_ms and self.next_seq > 0 \
                else P.LINK_UNKNOWN
        if ticks_diff(now, self._last_ack) > self._down_ms:
            return P.LINK_DOWN
        return P.LINK_DEGRADED if 0 in self._recent else P.LINK_UP

    def ms_since_ack(self, now):
        return None if self._last_ack is None else ticks_diff(now, self._last_ack)

    def pending_count(self):
        return len(self._pending)

    def due(self, now):
        return ticks_diff(now, self._next_due) >= 0

    # ---- sending ----
    def send_telemetry(self, now, tlm):
        """Fill the link fields of `tlm`, encode and hand it to the transport.

        Returns True if the transport accepted the frame. Never raises: every
        failure is counted. Schedules the next send one period later (without
        bursting to catch up after a stall)."""
        nd = ticks_add(self._next_due, self._period)
        self._next_due = nd if ticks_diff(nd, now) > 0 else ticks_add(now, self._period)
        seq = self.next_seq
        self.next_seq = (seq + 1) & 0xFFFFFFFF
        tlm.boot_id = self.boot_id
        tlm.seq = seq
        tlm.link = self.state(now)
        tlm.acked_seq = self.acked_seq
        tlm.tx_fail = self.stats.send_errors
        tlm.ack_miss = self.stats.ack_missing
        if self.last_ack_rssi is not None:
            tlm.ack_rssi = self.last_ack_rssi
            tlm.valid |= P.V_ACK_RSSI
        if self.recovering:
            tlm.flags |= P.F_LINK_RECOVERING
        try:
            frame = P.encode_telemetry(tlm)
        except Exception:
            self.stats.encode_errors += 1
            return False
        try:
            ok = self._t.send(self._peer, frame)
        except Exception:
            ok = False
        if not ok:
            self.stats.send_errors += 1
            return False
        self.stats.sent += 1
        self._pending[seq] = now
        self._order.append(seq)
        while len(self._order) > self._max_pending:
            self._miss(self._order.pop(0))
        return True

    # ---- receiving / housekeeping ----
    def poll(self, now):
        """Process up to max_rx_per_poll received frames, expire unacknowledged
        frames and run recovery. Bounded work; never raises."""
        for _ in range(self._max_rx):
            try:
                item = self._t.recv()
            except Exception:
                self.stats.rx_errors += 1
                break
            if item is None:
                break
            mac, data = item
            if mac is None or data is None:
                break
            if bytes(mac) != self._peer:
                self.stats.rx_foreign += 1
                continue
            try:
                ack = P.decode_ack(data)
            except P.ProtocolError as e:
                _inc(self.stats.rx_rejected, e.reason)
                continue
            self._on_ack(now, ack)
        self._expire(now)
        self._maybe_recover(now)

    def _on_ack(self, now, ack):
        if ack.boot_id != self.boot_id:
            self.stats.ack_unknown += 1
            return
        seq = ack.ack_seq
        if seq in self._pending:
            sent = self._pending.pop(seq)
            self._order.remove(seq)
            self.stats.acked += 1
            self.stats.rtt_last_ms = ticks_diff(now, sent)
            self._remember(1)
        elif seq in self._expired:
            self._expired.remove(seq)
            self.stats.ack_late += 1   # the link is alive even if this one was slow
        else:
            self.stats.ack_unknown += 1
            return
        self._last_ack = now
        self.recovering = False
        self.acked_seq = seq
        self.stats.ground_rx_ok = ack.rx_ok
        self.stats.ground_lost = ack.lost
        try:
            r = self._t.rssi(self._peer)
        except Exception:
            r = None
        self.last_ack_rssi = r

    def _expire(self, now):
        while self._order:
            seq = self._order[0]
            if ticks_diff(now, self._pending[seq]) <= self._ack_timeout:
                break
            self._order.pop(0)
            self._miss(seq)

    def _miss(self, seq):
        self._pending.pop(seq, None)
        self.stats.ack_missing += 1
        self._remember(0)
        self._expired.append(seq)
        if len(self._expired) > 32:
            self._expired.pop(0)

    def _remember(self, outcome):
        self._recent.append(outcome)
        if len(self._recent) > self.RECENT:
            self._recent.pop(0)

    def _maybe_recover(self, now):
        if self.state(now) != P.LINK_DOWN:
            return
        if self._last_recover is not None and ticks_diff(now, self._last_recover) < self._recov_ms:
            return
        self._last_recover = now
        self.recovering = True
        self.stats.recoveries += 1
        try:
            self._t.recover()
        except Exception:
            self.stats.recover_errors += 1


# ---------------------------------------------------------------------------
GS_NO_DATA = 0
GS_OK = 1
GS_STALE = 2
GS_LOST = 3
GS_NAMES = ("NO_DATA", "OK", "STALE", "LOST")


class GroundLinkStats:
    def __init__(self):
        self.rx_ok = 0          # distinct valid telemetry frames this boot of the flight board
        self.rx_total_ok = 0    # across all flight-board boots
        self.duplicates = 0
        self.late = 0           # arrived out of order (was counted lost, then recovered)
        self.too_old = 0        # older than the duplicate window: cannot be classified, dropped
        self.lost = 0           # sequence gaps not (yet) filled
        self.rejected = {}      # reason -> count
        self.implausible = 0    # frames with at least one implausible field (frame kept)
        self.foreign = 0        # frames from other MACs
        self.rx_errors = 0
        self.reboots = 0        # boot_id changes seen
        self.acks_sent = 0
        self.ack_errors = 0

    def rejected_total(self):
        n = 0
        for v in self.rejected.values():
            n += v
        return n


class GroundLink:
    WINDOW = 128  # sequence numbers remembered for duplicate detection

    def __init__(self, transport, flight_mac, stale_ms, lost_ms, max_rx_per_poll=16):
        self._t = transport
        self._peer = bytes(flight_mac)
        self._stale = stale_ms
        self._lost_ms = lost_ms
        self._max_rx = max_rx_per_poll
        self.boot_id = None
        self._first = None
        self._highest = None
        self._seen = {}         # seq -> True (bounded to WINDOW below highest)
        self._last_rx = None
        self.last = None        # latest accepted (non-duplicate) Telemetry
        self.last_rssi = None
        self.stats = GroundLinkStats()

    def status(self, now):
        if self._last_rx is None:
            return GS_NO_DATA
        d = ticks_diff(now, self._last_rx)
        if d > self._lost_ms:
            return GS_LOST
        return GS_STALE if d > self._stale else GS_OK

    def ms_since_rx(self, now):
        return None if self._last_rx is None else ticks_diff(now, self._last_rx)

    def loss_percent(self):
        if self._highest is None:
            return None
        expected = self._highest - self._first + 1
        return 100.0 * self.stats.lost / expected if expected > 0 else 0.0

    def poll(self, now, uptime_ms=0):
        """Receive up to max_rx_per_poll frames. Returns the list of newly
        accepted Telemetry objects (duplicates excluded). Never raises."""
        out = []
        for _ in range(self._max_rx):
            try:
                item = self._t.recv()
            except Exception:
                self.stats.rx_errors += 1
                break
            if item is None:
                break
            mac, data = item
            if mac is None or data is None:
                break
            if bytes(mac) != self._peer:
                self.stats.foreign += 1
                continue
            try:
                t = P.decode_telemetry(data)
            except P.ProtocolError as e:
                _inc(self.stats.rejected, e.reason)
                continue
            if t.implausible:
                self.stats.implausible += 1
            try:
                rssi = self._t.rssi(self._peer)
            except Exception:
                rssi = None
            self.last_rssi = rssi
            if self._classify(t):
                self.last = t
                out.append(t)
            self._last_rx = now
            self._ack(t, uptime_ms, rssi)
        return out

    def _classify(self, t):
        """True if new (display it); False for duplicates / too old."""
        s = self.stats
        if t.boot_id != self.boot_id:
            if self.boot_id is not None:
                s.reboots += 1
            self.boot_id = t.boot_id
            self._first = t.seq
            self._highest = t.seq
            self._seen = {t.seq: True}
            s.rx_ok = 1
            s.rx_total_ok += 1
            s.lost = 0
            return True
        seq = t.seq
        if seq in self._seen:
            s.duplicates += 1
            return False
        if seq > self._highest:
            s.lost += seq - self._highest - 1
            self._highest = seq
        elif seq >= self._first and self._highest - seq < self.WINDOW:
            s.late += 1                  # a gap we had counted as lost has been filled
            if s.lost > 0:
                s.lost -= 1
        else:
            s.too_old += 1
            return False
        self._seen[seq] = True
        if len(self._seen) > self.WINDOW + 16:
            floor = self._highest - self.WINDOW
            for k in [k for k in self._seen if k < floor]:
                del self._seen[k]
        s.rx_ok += 1
        s.rx_total_ok += 1
        return True

    def _ack(self, t, uptime_ms, rssi):
        a = P.Ack(t.boot_id, t.seq, uptime_ms, self.stats.rx_ok, self.stats.lost,
                  self.stats.rejected_total(), rssi)
        try:
            ok = self._t.send(self._peer, P.encode_ack(a))
        except Exception:
            ok = False
        if ok:
            self.stats.acks_sent += 1
        else:
            self.stats.ack_errors += 1
