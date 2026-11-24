# flight_node.py - CanSat FLIGHT board: sensors -> (flight software) -> ESP-NOW telemetry.
#
# Run from the laptop (board must already hold /lib and the config files, see
# esp32/tools/deploy.py):
#     mpremote connect <PORT> run esp32/apps/flight_node.py
# Ctrl-C stops it. Deployed with --autorun it is copied as /main.py instead.
#
# Bring-up program. No actuator, servo, buzzer or deployment code exists here:
# no output pin is configured except what machine.I2C / the radio drive themselves.
import os
import sys

import machine

import cs_proto as P
import flight_config as FC
import radio_config as RC
from cs_espnow import EspNowTransport
from cs_flight import BringupState, FlightNode
from cs_link import FlightLink
from cs_sensors import SensorSuite
from cs_util import (ROLE_FLIGHT, MacError, check_node_identity, check_role_macs, format_mac, sleep_ms, ticks_add,
                     ticks_diff, ticks_ms)

try:
    from board_role import ROLE as BOARD_ROLE
except ImportError:
    BOARD_ROLE = None


def _summary(suite):
    print("I2C scan: %s" % (" ".join("0x%02X" % a for a in suite.scan) or "(nothing answered)"))
    if suite.scan_error:
        print("  " + suite.scan_error)
    for ch in suite.channels() + tuple(suite.extra):
        print("  %-6s %-16s %-12s %s" % (ch.label, ch.name(), P.ST_NAMES[ch.status], ch.error))
    if suite.baro_dup_suspect:
        print("  WARNING: %d barometer(s) identified at %s, %d expected. Two BMP280s strapped to the SAME"
              % (len(suite.baro_identified), suite.baro_identified, FC.EXPECTED_BAROMETERS))
        print("           address look like ONE device; check each module alone (docs/10 section 9).")


def _status_line(node, now):
    s = node.suite
    lk = node.link
    st = lk.stats
    b1 = s.baro1.last
    im = s.imu.last
    return ("up %6.1fs seq %d link %s acked=%d miss=%d late=%d txfail=%d rtt=%s rec=%d | b1 %s%s | b2 %s | imu %s%s | "
            "pwr %s | state %s%s" % (
                node.uptime.ms() / 1000.0, lk.next_seq, P.LINK_NAMES[lk.state(now)], st.acked, st.ack_missing,
                st.ack_late, st.send_errors, st.rtt_last_ms, st.recoveries,
                P.ST_NAMES[s.baro1.status], (" %.1fPa" % b1.pressure_pa) if b1 is not None and b1.valid else "",
                P.ST_NAMES[s.baro2.status],
                P.ST_NAMES[s.imu.status],
                (" |a|=%.2fg" % ((im.ax_g ** 2 + im.ay_g ** 2 + im.az_g ** 2) ** 0.5)) if im is not None and im.valid else "",
                P.ST_NAMES[s.power.status], P.state_name(node.state_src.state()),
                (" EXC sensors=%d state=%d link=%d" % (node.sensor_exceptions, node.state_exceptions, node.link_exceptions))
                if (node.sensor_exceptions or node.state_exceptions or node.link_exceptions) else ""))


def main():
    print("== CanSat FLIGHT node (bring-up telemetry over ESP-NOW; NOT flight-validated) ==")
    print("MicroPython %s" % (sys.version,))
    transport = None
    try:
        # radio up first (needed to read our MAC); nothing is sent before the identity check
        f_mac_cfg = getattr(RC, "FLIGHT_MAC", None)
        g_mac_cfg = getattr(RC, "GROUND_MAC", None)
        _, ground_mac = check_role_macs(f_mac_cfg, g_mac_cfg)
        transport = EspNowTransport(RC.ESPNOW_CHANNEL, [ground_mac])
        own, ground_mac = check_node_identity(ROLE_FLIGHT, BOARD_ROLE, transport.own_mac(), RC)
    except MacError as e:
        print("REFUSING TO START: %s" % e)
        return
    print("own MAC %s  ground MAC %s  channel %s" % (format_mac(own), format_mac(ground_mac), transport.channel()))

    i2c = machine.I2C(FC.I2C_ID, scl=machine.Pin(FC.I2C_SCL), sda=machine.Pin(FC.I2C_SDA), freq=FC.I2C_FREQ_HZ)
    now = ticks_ms()
    suite = SensorSuite(FC).discover(i2c, now)
    _summary(suite)

    state = BringupState()
    if FC.RUN_FLIGHT_SOFTWARE:
        try:
            from cs_fsw_bridge import start_flight_software
            state = start_flight_software(suite, 0, "/")
        except Exception as e:
            from cs_flight import RefusedState
            state = RefusedState(["flight software could not be loaded: %r" % (e,)])
        if state.refused:
            print("FLIGHT SOFTWARE REFUSED TO START (telemetry continues in bring-up mode):")
            for r in state.reasons:
                print("  " + r)

    boot_id = int.from_bytes(os.urandom(2), "little")
    link = FlightLink(transport, ground_mac, boot_id, ticks_ms(), RC.TELEMETRY_PERIOD_MS, RC.ACK_TIMEOUT_MS,
                      RC.LINK_DOWN_MS, RC.RECOVERY_INTERVAL_MS, RC.MAX_PENDING_ACKS, RC.MAX_RX_PER_POLL)
    node = FlightNode(suite, link, state, ticks_ms(), sd_status=P.ST_DISABLED)
    print("boot_id %04X; telemetry every %d ms. Ctrl-C to stop." % (boot_id, RC.TELEMETRY_PERIOD_MS))
    next_print = ticks_ms()
    try:
        while True:
            now = ticks_ms()
            node.step(now)
            if ticks_diff(now, next_print) >= 0:
                next_print = ticks_add(now, FC.STATUS_PRINT_MS)
                print(_status_line(node, now))
                if node.last_error:
                    print("  last error: " + node.last_error)
                    node.last_error = ""
            sleep_ms(FC.LOOP_SLEEP_MS)
    except KeyboardInterrupt:
        print("stopped by user")


main()
