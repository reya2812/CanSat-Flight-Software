# cs_espnow.py - ESP-NOW transport for cs_link (runs on the ESP32 only).
#
# The ONLY module that touches the radio. No router, no internet: Wi-Fi is
# put in station mode purely so ESP-NOW can use the radio; it never connects.
#
# API used (MicroPython `espnow` module, in the official ESP32_GENERIC
# firmware since v1.20; [ASSUMPTION] recalled from docs.micropython.org,
# verify on the board with esp32/apps/board_info.py):
#   network.WLAN(network.STA_IF).active(True) / .config(channel=..) / .config('mac')
#   espnow.ESPNow().active(True) / add_peer(mac) / send(mac, msg, False) / recv(0)
#   ESPNow.peers_table  {mac: [rssi, time_ms]}
# send(..., sync=False) returns immediately: delivery is confirmed only by the
# application-level ACK in cs_link (never by blocking here).


class TransportError(Exception):
    pass


class EspNowTransport:
    def __init__(self, channel, peers, network_mod=None, espnow_mod=None, disable_power_save=True):
        if network_mod is None:
            import network as network_mod  # noqa: F811 - board only
        if espnow_mod is None:
            import espnow as espnow_mod    # noqa: F811 - board only
        self._net = network_mod
        self._esp = espnow_mod
        self._channel = channel
        self._peers = [bytes(p) for p in peers]
        self._pm_off = disable_power_save
        self._sta = None
        self._e = None
        self.start()

    def start(self):
        sta = self._net.WLAN(self._net.STA_IF)
        sta.active(True)
        try:
            sta.disconnect()  # never join an access point (also stops auto-reconnect)
        except Exception:
            pass
        if self._channel is not None:
            sta.config(channel=self._channel)
        if self._pm_off:
            try:  # recommended for ESP-NOW receivers; not fatal if unsupported
                sta.config(pm=sta.PM_NONE)
            except Exception:
                pass
        self._sta = sta
        e = self._esp.ESPNow()
        e.active(True)
        for p in self._peers:
            try:
                e.add_peer(p)
            except OSError:
                pass  # already registered
        self._e = e

    def own_mac(self):
        return bytes(self._sta.config("mac"))

    def channel(self):
        try:
            return self._sta.config("channel")
        except Exception:
            return None

    # ---- cs_link transport interface ----
    def send(self, mac, data):
        return bool(self._e.send(mac, data, False))

    def recv(self):
        host, msg = self._e.recv(0)
        if msg is None:
            return None
        return bytes(host), bytes(msg)

    def rssi(self, mac):
        try:
            entry = self._e.peers_table.get(bytes(mac))
        except Exception:
            return None
        return entry[0] if entry else None

    def recover(self):
        """Re-initialise ESP-NOW and re-register peers. Bounded, non-blocking."""
        try:
            self._e.active(False)
        except Exception:
            pass
        self.start()

    def stats(self):
        try:
            return self._e.stats()  # (tx_pkts, tx_responses, tx_failures, rx_packets, rx_dropped)
        except Exception:
            return None
