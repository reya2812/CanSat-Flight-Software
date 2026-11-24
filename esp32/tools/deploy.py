#!/usr/bin/env python3
"""deploy.py - copy the bring-up software to ONE board that already runs MicroPython (laptop).

    python3 esp32/tools/deploy.py --role flight --port /dev/cu.usbserial-XXXX [--autorun] [--with-fsw]
    python3 esp32/tools/deploy.py --role ground --port /dev/cu.usbserial-YYYY [--autorun]
    add --dry-run to print the plan without touching the board

Refuses unless radio_config.py holds valid, distinct FLIGHT_MAC and GROUND_MAC
and the board on --port reports exactly the MAC configured for --role.
Copies only files (no erase/flash). Writes /board_role.py on the board so the
node programs can refuse to run on the wrong board.
  --autorun   also install the node program as /main.py (runs at every power-up)
  --with-fsw  (flight only) also copy micropython/cansat (no mock/sim) for
              flight_config.RUN_FLIGHT_SOFTWARE; its boot checks still decide.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import esp32tool_common as C

COMMON_LIB = ("cs_util.py", "cs_proto.py", "cs_link.py", "cs_espnow.py")
ROLE_FILES = {
    "flight": {"lib": COMMON_LIB + ("cs_bmp280.py", "cs_mpu.py", "cs_ina219.py", "cs_sd.py", "cs_sensors.py",
                                    "cs_telemetry.py", "cs_flight.py", "cs_diag.py"),
               "config": ("radio_config.py", "flight_config.py"),
               "apps": ("flight_node.py", "flight_diag.py", "board_info.py"),
               "main": "flight_node.py"},
    "ground": {"lib": COMMON_LIB + ("cs_display.py",),
               "config": ("radio_config.py", "ground_config.py"),
               "apps": ("ground_node.py", "board_info.py"),
               "main": "ground_node.py"},
}
FSW_DIRS = ("config", "core", "hal")          # never mock/ or sim/ (laptop-only)
FSW_TOP = ("__init__.py", "boot_checks.py", "guards.py")


def fsw_files():
    root = os.path.join(C.REPO, "micropython", "cansat")
    out = [(os.path.join(root, f), "cansat/" + f) for f in FSW_TOP]
    for d in FSW_DIRS:
        for f in sorted(os.listdir(os.path.join(root, d))):
            if f.endswith(".py"):
                out.append((os.path.join(root, d, f), "cansat/%s/%s" % (d, f)))
    return out


def file_plan(role, autorun, with_fsw, role_file):
    spec = ROLE_FILES[role]
    pairs = [(os.path.join(C.LIB_DIR, f), "lib/" + f) for f in spec["lib"]]
    if with_fsw:
        if role != "flight":
            raise C.ToolError("--with-fsw applies to the flight board only")
        pairs.append((os.path.join(C.LIB_DIR, "cs_fsw_bridge.py"), "lib/cs_fsw_bridge.py"))
        pairs += fsw_files()
    pairs += [(os.path.join(C.CONFIG_DIR, f), f) for f in spec["config"]]
    pairs += [(os.path.join(C.APPS_DIR, f), f) for f in spec["apps"]]
    if autorun:
        pairs.append((os.path.join(C.APPS_DIR, spec["main"]), "main.py"))
    pairs.append((role_file, "board_role.py"))
    for src, _ in pairs:
        if not os.path.isfile(src):
            raise C.ToolError("missing source file %s" % src)
    return pairs


def mkdirs_snippet(pairs):
    dirs = sorted({os.path.dirname(dst) for _, dst in pairs if os.path.dirname(dst)})
    lines = ["import os"]
    for d in dirs:
        acc = ""
        for part in d.split("/"):
            acc = part if not acc else acc + "/" + part
            lines.append("try:\n os.mkdir(%r)\nexcept OSError:\n pass" % acc)
    return "\n".join(lines)


def mpremote_commands(port, pairs):
    cmd = ["mpremote", "connect", port, "exec", mkdirs_snippet(pairs)]
    for src, dst in pairs:
        cmd += ["+", "fs", "cp", src, ":" + dst]
    return [cmd]


def role_file_text(role, mac):
    return "# written by esp32/tools/deploy.py - identifies this board\nROLE = %r\nMAC = %r\n" % (
        role.upper(), C.cs_util.format_mac(mac))


def main(argv=None, run=subprocess.run):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", required=True, choices=C.ROLES)
    ap.add_argument("--port", required=True)
    ap.add_argument("--autorun", action="store_true")
    ap.add_argument("--with-fsw", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        rc = C.load_radio_config()
        try:
            C.cs_util.check_role_macs(rc.FLIGHT_MAC, rc.GROUND_MAC)
        except C.cs_util.MacError as e:
            raise C.ToolError(str(e))
        ident = C.mp_identity(a.port, run)
        print("board on %s: MicroPython %s, MAC %s, espnow %s, current role %s" % (
            a.port, ident["version"], C.cs_util.format_mac(ident["mac"]), "yes" if ident["espnow"] else "NO",
            ident["role"] or "(none)"))
        if not ident["espnow"]:
            raise C.ToolError("this firmware has no espnow module; flash the official ESP32_GENERIC image")
        C.check_board_role(a.role, ident["mac"], rc, require_configured=True)
        with tempfile.TemporaryDirectory() as tmp:
            rf = os.path.join(tmp, "board_role.py")
            with open(rf, "w") as f:
                f.write(role_file_text(a.role, ident["mac"]))
            pairs = file_plan(a.role, a.autorun, a.with_fsw, rf)
            cmds = mpremote_commands(a.port, pairs)
            print("copying %d files to the %s board:" % (len(pairs), a.role.upper()))
            for src, dst in pairs:
                print("  %-28s <- %s" % (":" + dst, os.path.relpath(src, C.REPO) if src.startswith(C.REPO) else src))
            if a.dry_run:
                print("DRY RUN: nothing copied")
                return 0
            for c in cmds:
                r = run(c)
                if r.returncode != 0:
                    raise C.ToolError("mpremote failed (exit %d)" % r.returncode)
        C.append_record({"event": "deploy", "role": a.role, "mac": C.cs_util.format_mac(ident["mac"]),
                         "port": a.port, "micropython": ident["version"], "autorun": a.autorun,
                         "with_fsw": a.with_fsw})
        print("deployed. Run: mpremote connect %s run esp32/apps/%s" % (a.port, ROLE_FILES[a.role]["main"]))
        return 0
    except C.ToolError as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
