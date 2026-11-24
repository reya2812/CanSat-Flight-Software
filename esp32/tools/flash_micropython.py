#!/usr/bin/env python3
"""flash_micropython.py - ERASE and FLASH official MicroPython onto ONE ESP32 (laptop).

DRY RUN BY DEFAULT. Nothing is erased or written unless --execute is given
AND you type the confirmation phrase, which names the role and the last three
bytes of the MAC read from the board on that port:

    python3 esp32/tools/flash_micropython.py --port /dev/cu.usbserial-XXXX --role flight \\
        --firmware ~/Downloads/ESP32_GENERIC-<version>.bin               # dry run: checks + plan
    python3 esp32/tools/flash_micropython.py ... --execute               # asks: FLASH FLIGHT 12:34:56

Safety checks before anything is written:
  * the firmware file is an ESP32_GENERIC .bin of plausible size; its SHA-256
    is printed (compare with micropython.org) and checked if --sha256 is given;
  * the chip on the port is read with `esptool read-mac` (read-only) and must
    be an original ESP32 (not S2/S3/C3...);
  * the MAC must not be the OTHER role's MAC in radio_config.py, and must
    equal this role's MAC if one is configured;
  * if the other board was already flashed (board_records.jsonl), the
    firmware SHA-256 must match it (same version on both boards), unless
    --allow-different-firmware.
Afterwards an entry is appended to esp32/config/board_records.jsonl.
"""
import argparse
import os
import subprocess
import sys

import esp32tool_common as C

FLASH_OFFSET = "0x1000"   # original ESP32: bootloader at 0x1000 (S3/C3 use 0x0) [micropython.org instructions]
MIN_SIZE, MAX_SIZE = 512 * 1024, 4 * 1024 * 1024


def check_firmware(path, sha256=None):
    if not os.path.isfile(path):
        raise C.ToolError("firmware file not found: %s" % path)
    name = os.path.basename(path)
    if not name.endswith(".bin") or not name.startswith("ESP32_GENERIC-"):
        raise C.ToolError("expected the official ESP32_GENERIC-<version>.bin image, got %r. "
                          "Variants such as ESP32_GENERIC_S3 / _C3 / -SPIRAM / -OTA / -D2WD are for other "
                          "chips or layouts" % name)
    variant = name[len("ESP32_GENERIC-"):]
    if not variant[:1].isdigit() and not variant.startswith("v"):
        raise C.ToolError("%r is a board variant, not the plain ESP32_GENERIC image" % name)
    if "preview" in variant:
        raise C.ToolError("%r is a preview (nightly) build; use a stable release" % name)
    size = os.path.getsize(path)
    if not (MIN_SIZE <= size <= MAX_SIZE):
        raise C.ToolError("firmware size %d bytes is implausible for ESP32_GENERIC" % size)
    digest = C.sha256_file(path)
    if sha256 and sha256.lower() != digest:
        raise C.ToolError("SHA-256 mismatch: file %s, expected %s" % (digest, sha256.lower()))
    return name, size, digest


def check_same_firmware(role, digest, records):
    other = "ground" if role == "flight" else "flight"
    flashed = [r for r in records if r.get("event") == "flash" and r.get("role") == other]
    if flashed and flashed[-1].get("sha256") != digest:
        raise C.ToolError("the %s board was flashed with %s (sha256 %s...). Use the same firmware on both boards "
                          "or pass --allow-different-firmware" % (other, flashed[-1].get("firmware"),
                                                                  flashed[-1].get("sha256", "")[:12]))


def confirmation_phrase(role, mac):
    return "FLASH %s %s" % (role.upper(), C.cs_util.format_mac(mac)[-8:])


def plan(port, fw, baud, major):
    base = C.esptool_base() + ["--chip", "esp32", "--port", port, "--baud", str(baud)]
    return [base + [C.esptool_cmd("erase-flash", major)],
            base + [C.esptool_cmd("write-flash", major), "-z", FLASH_OFFSET, fw]]


def main(argv=None, run=subprocess.run, input_fn=input, records_path=C.RECORDS):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--role", required=True, choices=C.ROLES)
    ap.add_argument("--firmware", required=True)
    ap.add_argument("--sha256", help="expected SHA-256 of the firmware file (from micropython.org)")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--execute", action="store_true", help="actually erase and flash (asks for confirmation)")
    ap.add_argument("--allow-different-firmware", action="store_true")
    a = ap.parse_args(argv)
    try:
        name, size, digest = check_firmware(a.firmware, a.sha256)
        print("firmware : %s (%d bytes)\nsha256   : %s%s" % (name, size, digest,
                                                          "  (matches --sha256)" if a.sha256 else
                                                          "  <- compare with the value on micropython.org"))
        if not a.allow_different_firmware:
            check_same_firmware(a.role, digest, C.read_records(records_path))
        print("reading chip identity on %s (read-only; the board resets)..." % a.port)
        chip, mac, _ = C.read_identity(a.port, run)
        print("chip     : %s\nMAC      : %s" % (chip, C.cs_util.format_mac(mac)))
        if not C.is_classic_esp32(chip):
            raise C.ToolError("chip %r is not an original ESP32; ESP32_GENERIC is the wrong firmware" % chip)
        for w in C.check_board_role(a.role, mac, C.load_radio_config(), require_configured=False):
            print("WARNING  : " + w)
        major = C.esptool_major(run)
        cmds = plan(a.port, a.firmware, a.baud, major)
        print("\nplan for the %s board on %s:" % (a.role.upper(), a.port))
        for c in cmds:
            print("  " + " ".join(c))
        if not a.execute:
            print("\nDRY RUN: nothing was erased or written. Re-run with --execute to flash.")
            return 0
        phrase = confirmation_phrase(a.role, mac)
        print("\nThis ERASES ALL FLASH on the board with MAC %s." % C.cs_util.format_mac(mac))
        typed = input_fn("Type exactly '%s' to continue: " % phrase)
        if typed.strip() != phrase:
            print("confirmation did not match: aborted, nothing written")
            return 3
        # re-read the identity right before erasing: the port might now be a different board
        chip2, mac2, _ = C.read_identity(a.port, run)
        if mac2 != mac:
            raise C.ToolError("the board on %s changed (MAC now %s): aborted, nothing written"
                              % (a.port, C.cs_util.format_mac(mac2)))
        for c in cmds:
            print("running: " + " ".join(c))
            r = run(c)
            if r.returncode != 0:
                raise C.ToolError("command failed with exit %d; the board may be erased but not flashed. "
                                  "Fix the cause and re-run this tool." % r.returncode)
        C.append_record({"event": "flash", "role": a.role, "mac": C.cs_util.format_mac(mac), "chip": chip,
                         "port": a.port, "firmware": name, "sha256": digest}, records_path)
        print("\nflashed. Next: python3 esp32/tools/esp32_ports.py --mp-info %s" % a.port)
        return 0
    except C.ToolError as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
