# cs_util.py - small portable helpers shared by both boards (MicroPython + CPython).
#
# No MicroPython-only imports at module level: on the board `time` provides
# ticks_ms/ticks_diff/ticks_add; on the laptop a CPython emulation with the
# ESP32 port's tick period (2^30 ms, see micropython/cansat/core/clock.py) is used.
import time

TICKS_PERIOD = 1 << 30
_HALF = TICKS_PERIOD // 2

if hasattr(time, "ticks_ms"):
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
else:  # CPython emulation (laptop tests)
    def ticks_ms():
        return int(time.monotonic() * 1000) & (TICKS_PERIOD - 1)

    def ticks_diff(a, b):
        d = (a - b) & (TICKS_PERIOD - 1)
        return d - TICKS_PERIOD if d >= _HALF else d

    def ticks_add(a, delta):
        return (a + delta) & (TICKS_PERIOD - 1)


def sleep_ms(ms):
    f = getattr(time, "sleep_ms", None)
    if f:
        f(ms)
    else:
        time.sleep(ms / 1000.0)


class Uptime:
    """uint32 milliseconds since construction, accumulated from tick differences.

    update() must be called at least every TICKS_PERIOD/2 ms (~6 days) or a
    period is lost; the node main loops call it every iteration.
    """

    def __init__(self, now_ticks):
        self._last = now_ticks
        self._ms = 0

    def update(self, now_ticks):
        d = ticks_diff(now_ticks, self._last)
        if d > 0:
            self._ms = (self._ms + d) & 0xFFFFFFFF
            self._last = now_ticks
        return self._ms

    def ms(self):
        return self._ms


# ---------------------------------------------------------------------------
# MAC addresses
# ---------------------------------------------------------------------------
class MacError(ValueError):
    pass


def parse_mac(text):
    """'aa:bb:cc:dd:ee:ff' (or '-' separated) -> 6 bytes. Rejects broadcast,
    multicast and all-zero addresses: none of them can be an ESP-NOW unicast peer."""
    if not isinstance(text, str):
        raise MacError("MAC must be a string like 'aa:bb:cc:dd:ee:ff', got %r" % (text,))
    parts = text.strip().replace("-", ":").split(":")
    if len(parts) != 6:
        raise MacError("MAC must have 6 bytes: %r" % (text,))
    try:
        b = bytes(int(p, 16) for p in parts)
    except ValueError:
        raise MacError("MAC has a non-hex byte: %r" % (text,))
    for p in parts:
        if len(p) != 2:
            raise MacError("each MAC byte must be 2 hex digits: %r" % (text,))
    if b == b"\xff" * 6:
        raise MacError("broadcast MAC is not a valid peer: %r" % (text,))
    if b == b"\x00" * 6:
        raise MacError("all-zero MAC is not a valid peer: %r" % (text,))
    if b[0] & 0x01:
        raise MacError("multicast MAC (first byte odd) is not a valid peer: %r" % (text,))
    return b


def format_mac(b):
    return ":".join("%02x" % x for x in b)


def check_role_macs(flight_mac_text, ground_mac_text):
    """Return (flight_bytes, ground_bytes) or raise MacError with a fix-it message."""
    if flight_mac_text is None or ground_mac_text is None:
        raise MacError("radio_config.FLIGHT_MAC and GROUND_MAC must both be set "
                       "(read each board's MAC with esp32/apps/board_info.py)")
    f = parse_mac(flight_mac_text)
    g = parse_mac(ground_mac_text)
    if f == g:
        raise MacError("FLIGHT_MAC and GROUND_MAC are identical (%s): the same board was recorded twice"
                       % format_mac(f))
    return f, g


ROLE_FLIGHT = "FLIGHT"
ROLE_GROUND = "GROUND"


def check_node_identity(role, board_role, own_mac, radio_config):
    """Refuse to run the wrong program on the wrong board.

    role:        what this program is (ROLE_FLIGHT / ROLE_GROUND)
    board_role:  ROLE written to the board by esp32/tools/deploy.py (None if absent)
    own_mac:     6 bytes read from this board's radio
    Returns (own_bytes, peer_bytes); raises MacError with the reason."""
    if role not in (ROLE_FLIGHT, ROLE_GROUND):
        raise MacError("unknown role %r" % (role,))
    if board_role != role:
        raise MacError("this board is deployed as %r, but this program is the %s node "
                       "(re-deploy with esp32/tools/deploy.py --role %s if that is intended)"
                       % (board_role, role, role.lower()))
    f, g = check_role_macs(getattr(radio_config, "FLIGHT_MAC", None), getattr(radio_config, "GROUND_MAC", None))
    own_expected, peer = (f, g) if role == ROLE_FLIGHT else (g, f)
    own = bytes(own_mac)
    if own != own_expected:
        other = "GROUND" if role == ROLE_FLIGHT else "FLIGHT"
        hint = (" - this is the %s board!" % other) if own == peer else ""
        raise MacError("this board's MAC is %s but radio_config lists %s for %s%s"
                       % (format_mac(own), format_mac(own_expected), role, hint))
    return own, peer


def clamp_u16(v):
    return 0xFFFF if v > 0xFFFF else (0 if v < 0 else v)
