#!/usr/bin/env python3
"""esp32_ports.py - find the ESP32 boards' serial ports (laptop).

    python3 esp32/tools/esp32_ports.py                     # list ports (passive: opens nothing)
    python3 esp32/tools/esp32_ports.py --read-mac PORT     # chip type + MAC via esptool (read-only)
    python3 esp32/tools/esp32_ports.py --mp-info PORT      # MicroPython version/MAC/role (needs MicroPython)

--read-mac resets the board into its ROM bootloader and back; it does NOT
erase or write flash. Close any serial monitor on that port first.

Identifying which physical board is which: plug in ONE board, list, note the
port; plug in the second, list again. Then --read-mac each port and write the
MAC on a label stuck to the board.
"""
import argparse
import sys

import esp32tool_common as C


def list_ports():
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        print("pyserial is not installed (it comes with esptool: pip install esptool)")
        return 1
    ports = list(lp.comports())
    if not ports:
        print("no serial ports found")
        return 0
    print("%-32s %-11s %-12s %s" % ("device", "VID:PID", "serial", "description / bridge"))
    for p in sorted(ports, key=lambda x: x.device):
        vidpid = "%04X:%04X" % (p.vid, p.pid) if p.vid is not None else "-"
        bridge = C.USB_BRIDGES.get((p.vid, p.pid), "")
        hint = ""
        if sys.platform == "darwin" and p.device.startswith("/dev/tty."):
            hint = "  (use the /dev/cu.* twin on macOS)"
        print("%-32s %-11s %-12s %s%s%s" % (p.device, vidpid, p.serial_number or "-", p.description or "-",
                                             ("  <- " + bridge) if bridge else "", hint))
    print("\nPorts marked CP210x are the likely ESP32 boards (the board spec says CP2102).")
    print("Two boards with identical USB serial numbers are told apart only by port name or MAC.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--read-mac", metavar="PORT")
    ap.add_argument("--mp-info", metavar="PORT")
    a = ap.parse_args(argv)
    try:
        if a.read_mac:
            chip, mac, _ = C.read_identity(a.read_mac)
            print("port %s: chip %s, MAC %s" % (a.read_mac, chip, C.cs_util.format_mac(mac)))
            if not C.is_classic_esp32(chip):
                print("WARNING: this is not an original ESP32 (ESP32-WROOM-32): ESP32_GENERIC firmware is wrong for it")
            _say_role(mac)
            return 0
        if a.mp_info:
            d = C.mp_identity(a.mp_info)
            print("port %s: MicroPython %s, MAC %s, espnow %s, deployed role %s" % (
                a.mp_info, d["version"], C.cs_util.format_mac(d["mac"]), "yes" if d["espnow"] else "NO",
                d["role"] or "(none)"))
            _say_role(d["mac"])
            return 0
        return list_ports()
    except C.ToolError as e:
        print("ERROR: %s" % e)
        return 2


def _say_role(mac):
    try:
        macs = C.role_macs(C.load_radio_config())
    except C.ToolError as e:
        print("radio_config: %s" % e)
        return
    for role, m in macs.items():
        if m == mac:
            print("radio_config: this is the %s board" % role.upper())
            return
    print("radio_config: this MAC is not recorded for either role yet")


if __name__ == "__main__":
    sys.exit(main())
