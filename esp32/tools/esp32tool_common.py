"""esp32tool_common.py - shared helpers for the laptop tools (CPython only).

Nothing in this module erases, flashes or writes to a board by itself; the
tools that do (flash_micropython.py, deploy.py) require explicit flags and,
for flashing, a typed confirmation that names the board's MAC.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ESP32_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(ESP32_DIR)
LIB_DIR = os.path.join(ESP32_DIR, "lib")
CONFIG_DIR = os.path.join(ESP32_DIR, "config")
APPS_DIR = os.path.join(ESP32_DIR, "apps")
RECORDS = os.path.join(CONFIG_DIR, "board_records.jsonl")

sys.path.insert(0, LIB_DIR)
import cs_util  # noqa: E402

ROLES = ("flight", "ground")

# USB-UART bridges commonly found on ESP32 dev boards (VID, PID) -> name
USB_BRIDGES = {(0x10C4, 0xEA60): "Silicon Labs CP210x (expected on these boards)",
               (0x1A86, 0x7523): "WCH CH340", (0x1A86, 0x55D4): "WCH CH9102",
               (0x0403, 0x6001): "FTDI FT232R", (0x0403, 0x6015): "FTDI FT231X"}


class ToolError(Exception):
    pass


def load_radio_config(path=None):
    """Execute esp32/config/radio_config.py in an isolated namespace."""
    path = path or os.path.join(CONFIG_DIR, "radio_config.py")
    ns = {}
    with open(path) as f:
        exec(compile(f.read(), path, "exec"), ns)
    return type("RadioConfig", (), {k: v for k, v in ns.items() if not k.startswith("__")})


def role_macs(rc):
    """{'flight': bytes|None, 'ground': bytes|None}; raises ToolError on malformed values."""
    out = {}
    for role, attr in (("flight", "FLIGHT_MAC"), ("ground", "GROUND_MAC")):
        v = getattr(rc, attr, None)
        try:
            out[role] = None if v is None else cs_util.parse_mac(v)
        except cs_util.MacError as e:
            raise ToolError("radio_config.%s: %s" % (attr, e))
    if out["flight"] is not None and out["flight"] == out["ground"]:
        raise ToolError("radio_config FLIGHT_MAC and GROUND_MAC are identical")
    return out


def check_board_role(role, board_mac, rc, require_configured):
    """Decide whether a board with `board_mac` may be treated as `role`.

    Returns a list of warnings; raises ToolError when the board is (or may be) the wrong one."""
    macs = role_macs(rc)
    other = "ground" if role == "flight" else "flight"
    warnings = []
    if macs[other] is not None and board_mac == macs[other]:
        raise ToolError("this board (%s) is the configured %s board, not the %s board"
                        % (cs_util.format_mac(board_mac), other.upper(), role.upper()))
    if macs[role] is None:
        if require_configured:
            raise ToolError("radio_config.%s_MAC is not set; record this board's MAC (%s) there first"
                            % (role.upper(), cs_util.format_mac(board_mac)))
        warnings.append("radio_config.%s_MAC is not set yet: the board's identity cannot be cross-checked. "
                        "Record %s after flashing." % (role.upper(), cs_util.format_mac(board_mac)))
    elif board_mac != macs[role]:
        raise ToolError("this board's MAC %s does not match radio_config.%s_MAC %s"
                        % (cs_util.format_mac(board_mac), role.upper(), cs_util.format_mac(macs[role])))
    return warnings


# ---------------------------------------------------------------------------
# esptool (read-only use here; flash_micropython.py adds erase/write)
# ---------------------------------------------------------------------------
def esptool_base():
    return [sys.executable, "-m", "esptool"]


def esptool_major(run=subprocess.run):
    try:
        r = run(esptool_base() + ["version"], capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    m = re.search(r"v?(\d+)\.\d+", (r.stdout or "") + (r.stderr or ""))
    return int(m.group(1)) if m else None


def esptool_cmd(name, major):
    """esptool v5 uses dashed sub-commands (read-mac); v4 used underscores (read_mac)."""
    return name if (major is None or major >= 5) else name.replace("-", "_")


def parse_esptool_identity(text):
    """(chip_description, mac_bytes) from `esptool read-mac` output (v4 or v5 wording)."""
    chip = None
    m = re.search(r"Chip (?:is|type:)\s*(.+)", text)
    if m:
        chip = m.group(1).strip()
    if chip is None:
        m = re.search(r"Detecting chip type\.\.\.\s*(\S+)", text)
        if m:
            chip = m.group(1).strip()
    macs = re.findall(r"^\s*(?:BASE )?MAC:\s*([0-9A-Fa-f:]{17})", text, re.M)
    if not macs:
        raise ToolError("could not find a MAC address in esptool output")
    return chip, cs_util.parse_mac(macs[0])


def is_classic_esp32(chip):
    """True for the original ESP32 (ESP32-D0WD..., ESP32-D0WDQ6, 'ESP32'), False for S2/S3/C3/C6/H2/P4."""
    if not chip:
        return False
    head = chip.strip().split()[0].upper()
    return head == "ESP32" or head.startswith("ESP32-D") or head.startswith("ESP32-U4") or head.startswith("ESP32-PICO")


def read_identity(port, run=subprocess.run):
    """READ-ONLY: `esptool read-mac`. Resets the board into its ROM bootloader and back;
    flash contents are not touched."""
    major = esptool_major(run)
    cmd = esptool_base() + ["--port", port, esptool_cmd("read-mac", major)]
    r = run(cmd, capture_output=True, text=True, timeout=60)
    text = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise ToolError("esptool could not talk to %s (exit %d). Is it the right port, and is no serial monitor "
                        "open? Some boards need BOOT held while connecting.\n%s" % (port, r.returncode, text[-800:]))
    chip, mac = parse_esptool_identity(text)
    return chip, mac, text


# ---------------------------------------------------------------------------
# mpremote (board must already run MicroPython)
# ---------------------------------------------------------------------------
MP_IDENTITY_SNIPPET = (
    "import network,sys\n"
    "s=network.WLAN(network.STA_IF);s.active(True)\n"
    "print('MAC=' + ':'.join('%02x' % b for b in s.config('mac')))\n"
    "print('VER=' + sys.version)\n"
    "try:\n import espnow;print('ESPNOW=1')\nexcept ImportError:\n print('ESPNOW=0')\n"
    "try:\n from board_role import ROLE;print('ROLE='+ROLE)\nexcept ImportError:\n print('ROLE=')\n")


def parse_mp_identity(text):
    d = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            d[k] = v
    if "MAC" not in d:
        raise ToolError("board did not report a MAC; is MicroPython running on it?\n" + text[-600:])
    return {"mac": cs_util.parse_mac(d["MAC"]), "version": d.get("VER", "?"), "espnow": d.get("ESPNOW") == "1",
            "role": d.get("ROLE") or None}


def mp_identity(port, run=subprocess.run):
    r = run(["mpremote", "connect", port, "exec", MP_IDENTITY_SNIPPET], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise ToolError("mpremote could not run code on %s (exit %d): %s" % (port, r.returncode,
                                                                          ((r.stdout or "") + (r.stderr or ""))[-600:]))
    return parse_mp_identity(r.stdout or "")


# ---------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def append_record(entry, path=RECORDS):
    entry = dict(entry)
    entry.setdefault("utc", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_records(path=RECORDS):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out
