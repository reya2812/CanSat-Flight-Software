# ground_node.py - CanSat GROUND board: receive ESP-NOW telemetry, validate,
# acknowledge, and print it on the USB serial console. No router, no internet,
# no laptop-side server: open the serial console (mpremote / Thonny / screen).
#
#     mpremote connect <PORT> run esp32/apps/ground_node.py
#
# The ground node sends ONLY acknowledgements. There is no command uplink:
# nothing it sends can change the flight board's state or actuate anything.
import ground_config as GC
import radio_config as RC
from cs_display import CSV_HEADER, csv_line, render
from cs_espnow import EspNowTransport
from cs_link import GroundLink
from cs_util import (ROLE_GROUND, MacError, Uptime, check_node_identity, check_role_macs, format_mac, sleep_ms,
                     ticks_add, ticks_diff, ticks_ms)

try:
    from board_role import ROLE as BOARD_ROLE
except ImportError:
    BOARD_ROLE = None


def main():
    print("== CanSat GROUND station (ESP-NOW receiver; bring-up) ==")
    try:
        flight_mac, _ = check_role_macs(getattr(RC, "FLIGHT_MAC", None), getattr(RC, "GROUND_MAC", None))
        transport = EspNowTransport(RC.ESPNOW_CHANNEL, [flight_mac])
        own, flight_mac = check_node_identity(ROLE_GROUND, BOARD_ROLE, transport.own_mac(), RC)
    except MacError as e:
        print("REFUSING TO START: %s" % e)
        return
    print("own MAC %s  flight MAC %s  channel %s" % (format_mac(own), format_mac(flight_mac), transport.channel()))
    link = GroundLink(transport, flight_mac, RC.GROUND_STALE_MS, RC.GROUND_LOST_MS, RC.MAX_RX_PER_POLL)
    up = Uptime(ticks_ms())
    if GC.CSV_OUTPUT:
        print(CSV_HEADER)
    next_draw = ticks_ms()
    try:
        while True:
            now = ticks_ms()
            ms = up.update(now)
            for t in link.poll(now, ms):
                if GC.CSV_OUTPUT:
                    print(csv_line(t))
            if ticks_diff(now, next_draw) >= 0:
                next_draw = ticks_add(now, GC.DISPLAY_PERIOD_MS)
                if GC.DISPLAY_ANSI_CLEAR:
                    print("\x1b[2J\x1b[H", end="")
                print(render(link, now, ms))
                print("")
            sleep_ms(GC.LOOP_SLEEP_MS)
    except KeyboardInterrupt:
        print("stopped by user")


main()
