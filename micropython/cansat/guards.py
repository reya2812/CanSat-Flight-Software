# guards.py - source rules shared by boot_checks (on the board) and
# tools/scan_guards.py (laptop build). Portable: os.listdir/os.stat only
# (MicroPython has no os.path), plain substring matching (no regex).
#
# WEAKER THAN THE C++ GUARDS (D-017, stated in micropython/README.md):
#   - C++ stops the build with #error / static_assert; nothing can run.
#     Here the checks are code that runs; editing or skipping them removes them.
#   - Substring rules only recognise the spellings listed below. Code that
#     reaches hardware another way (getattr, __import__, aliases, eval) is
#     not detected.
#   - Precompiled .mpy files cannot be scanned; the boot check refuses to run
#     when it finds any (see find_unscannable).
#   - Digital outputs are recognised only by the Pin.OUT / Pin.OPEN_DRAIN
#     spellings. A numeric mode (Pin(x, 1)) or a mode passed through a variable
#     is NOT detected.
import os

# Files that define the rules themselves (they must name the forbidden tokens).
RULE_FILES = ("cansat/guards.py", "cansat/boot_checks.py", "tools/scan_guards.py")

# Always forbidden, everywhere: PWM (servo drive) and DAC outputs (D-017).
ALWAYS_FORBIDDEN_TOKENS = ("PWM", "machine.DAC", "DAC(")
# Digital outputs: forbidden except for named NON-actuator pins inside the
# hardware layer (module 4 review, item 2):
DIGITAL_OUTPUT_TOKENS = ("Pin.OUT", "Pin.OPEN_DRAIN")
OUTPUT_LAYER = "cansat/hal_mp/"
ALLOWED_OUTPUT_PIN_NAMES = ("PIN_SD_CS", "PIN_HC12_SET")  # SD chip select, HC-12 SET control
# Actuator pins may not be referenced by any code except hardware_config.py itself.
# If buzzer code is ever allowed, hardware_config.unresolved_items() must require
# the buzzer pins again (D-018).
ACTUATOR_PIN_PREFIXES = ("PIN_SERVO_", "PIN_BUZZER_")
CONFIG_FILE = "cansat/config/hardware_config.py"
# Kept for callers that list every token the rules look for.
ACTUATOR_TOKENS = ALWAYS_FORBIDDEN_TOKENS + DIGITAL_OUTPUT_TOKENS


def _is_dir(path):
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def walk_files(root, suffix):
    """Yield (relative_path, full_path) for files under root ending in suffix."""
    stack = [""]
    while stack:
        rel = stack.pop()
        full = root + "/" + rel if rel else root
        try:
            names = sorted(os.listdir(full))
        except OSError:
            continue
        for n in names:
            if n.startswith(".") or n == "__pycache__":
                continue
            r = rel + "/" + n if rel else n
            f = root + "/" + r
            if _is_dir(f):
                stack.append(r)
            elif n.endswith(suffix):
                yield r, f


def code_lines(text):
    """(line_number, code) pairs with '#' comments removed (naive: '#' inside
    strings also cuts the line, which can only hide text, never add it)."""
    out = []
    n = 0
    for line in text.split("\n"):
        n += 1
        i = line.find("#")
        code = line if i < 0 else line[:i]
        if code.strip():
            out.append((n, code))
    return out


def _read(path):
    with open(path) as f:
        return f.read()


def actuator_violations(root, include_tests=False):
    """Actuator-code findings under root as 'path:line: message' strings."""
    found = []
    for rel, full in walk_files(root, ".py"):
        if rel in RULE_FILES:
            continue
        in_tests = rel.startswith("tests/")
        if in_tests and not include_tests:
            continue
        lines = code_lines(_read(full))
        for n, code in lines:
            where = rel + ":" + str(n) + ": "
            for tok in ALWAYS_FORBIDDEN_TOKENS:
                if tok in code:
                    found.append(where + "actuator output token '" + tok + "'")
            if rel != CONFIG_FILE:
                for pre in ACTUATOR_PIN_PREFIXES:
                    if pre in code:
                        found.append(where + "references actuator pin " + pre + "*")
            for tok in DIGITAL_OUTPUT_TOKENS:
                if tok in code:
                    why = _output_not_allowed(rel, code)
                    if why:
                        found.append(where + "digital output '" + tok + "' " + why)
        if not in_tests:
            found.extend(_physical_driver(rel, lines))
    return found


def _output_not_allowed(rel, code):
    """None if this digital-output line is an allowed non-actuator output, else the reason.

    Allowed only when ALL hold: the file is in the hardware layer, the SAME line
    names exactly one allowed pin, and it has no literal pin number. Lines split
    across several lines are refused (the rule cannot see the pin).
    """
    if not rel.startswith(OUTPUT_LAYER):
        return "outside " + OUTPUT_LAYER
    named = [n for n in ALLOWED_OUTPUT_PIN_NAMES if n in code]
    if len(named) != 1:
        return "must name exactly one of " + ", ".join(ALLOWED_OUTPUT_PIN_NAMES) + " on the same line"
    if "Pin(" in code and code.split("Pin(", 1)[1][:1].isdigit():
        return "uses a literal pin number"
    return None


def _physical_driver(rel, lines):
    """A non-test `def is_physical` whose body returns True."""
    out = []
    in_def = False
    indent = 0
    for n, code in lines:
        stripped = code.lstrip()
        ind = len(code) - len(stripped)
        if stripped.startswith("def is_physical"):
            in_def, indent = True, ind
            continue
        if in_def:
            if ind <= indent:
                in_def = False
            elif stripped.startswith("return") and "True" in stripped:
                out.append(rel + ":" + str(n) + ": is_physical() returns True outside tests")
    return out


def find_unscannable(root):
    """Precompiled modules the source rules cannot inspect."""
    return [rel for rel, _ in walk_files(root, ".mpy")]
