#!/usr/bin/env python3
"""scan_guards.py - build-time source scan for the MicroPython port (D-017).

Laptop tool (CPython). Exit status 0 = all rules pass, 1 = at least one rule
failed. Run from anywhere:   python3 tools/scan_guards.py [root]

WEAKER THAN THE C++ GUARDS (firmware/test/guards/run_guard_checks.sh compiles
deliberately broken builds and checks the compiler refuses them). This script
only reads text. It recognises the spellings listed in each rule; code that
reaches hardware another way (getattr, __import__, aliases, eval, exec) is not
detected, and nothing stops someone from not running it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)

MICROPYTHON_ONLY_MODULES = ("machine", "esp32", "esp", "network", "espnow", "micropython",
                            "utime", "uos", "neopixel", "onewire", "bluetooth")
CPYTHON_ONLY_MODULES = ("enum", "dataclasses", "typing", "abc")
HARDWARE_DIR = "cansat/hal_mp/"  # does not exist yet; drivers are paused until approved (module 4)


def _imports(code):
    s = code.strip()
    if s.startswith("import "):
        return [p.strip().split(" ")[0].split(".")[0] for p in s[7:].split(",")]
    if s.startswith("from "):
        return [s[5:].split(" ")[0].split(".")[0]]
    return []


def scan(root):
    sys.path.insert(0, root)
    try:
        from cansat import guards
    finally:
        sys.path.pop(0)

    files = {}
    for rel, full in guards.walk_files(root, ".py"):
        with open(full) as f:
            files[rel] = f.read()
    code = {rel: guards.code_lines(t) for rel, t in files.items()}
    results = []

    def rule(name, hits):
        results.append((name, hits))

    def hits_where(pred, check):
        out = []
        for rel, lines in code.items():
            if not pred(rel) or rel in guards.RULE_FILES:
                continue
            for n, c in lines:
                msg = check(rel, c)
                if msg:
                    out.append("%s:%d: %s" % (rel, n, msg))
        return out

    in_pkg = lambda rel: rel.startswith("cansat/")
    not_tests = lambda rel: not rel.startswith("tests/")

    # ---- actuator safety ----
    rule("no actuator output code: no PWM or DAC; digital outputs only for PIN_SD_CS or PIN_HC12_SET in cansat/hal_mp/; no actuator-pin references; no physical is_physical()",
         guards.actuator_violations(root))
    rule("build_flags.PHYSICAL_ACTUATORS_ENABLED is the literal False",
         [] if "PHYSICAL_ACTUATORS_ENABLED = False" in files.get("cansat/config/build_flags.py", "")
         else ["cansat/config/build_flags.py: PHYSICAL_ACTUATORS_ENABLED is not the literal False"])
    rule("only cansat/core/actuator_manager.py calls ActuatorDriver.apply()",
         hits_where(lambda r: not_tests(r) and r != "cansat/core/actuator_manager.py",
                    lambda r, c: ".apply(" in c and "call .apply(" or None))
    rule("no non-mock implementation of ConnectionAssessmentSource or ArmingSource",
         hits_where(lambda r: in_pkg(r) and not r.startswith("cansat/mock/") and r != "cansat/hal/interfaces.py",
                    lambda r, c: ("(ConnectionAssessmentSource)" in c or "(ArmingSource)" in c)
                    and "implements an unresolved source" or None))
    rule("no precompiled .mpy files in the source tree (they cannot be scanned)",
         guards.find_unscannable(root))

    # ---- portability / layering ----
    rule("no CPython-only modules (enum, dataclasses, typing, abc) in the package",
         hits_where(in_pkg, lambda r, c: any(m in CPYTHON_ONLY_MODULES for m in _imports(c))
                    and "imports " + ",".join(_imports(c)) or None))
    rule("MicroPython-only modules are imported only under " + HARDWARE_DIR,
         hits_where(lambda r: not r.startswith(HARDWARE_DIR),
                    lambda r, c: any(m in MICROPYTHON_ONLY_MODULES for m in _imports(c))
                    and "imports " + ",".join(_imports(c)) or None))
    rule("cansat/core does not import time (it uses the Clock interface)",
         hits_where(lambda r: r.startswith("cansat/core/"),
                    lambda r, c: "time" in _imports(c) and "imports time" or None))
    rule("no return-type annotations in the package (MicroPython portability)",
         hits_where(in_pkg, lambda r, c: c.strip().startswith("def ") and "->" in c and "annotation" or None))
    rule("flight_state_manager.py does not reference sensors or samples (C++ guard parity)",
         hits_where(lambda r: r == "cansat/core/flight_state_manager.py",
                    lambda r, c: any(k in c for k in ("Sample", "SensorFrame", "sensor_validator", "fmath", "ValidatedFrame"))
                    and "sensor reference in the state machine" or None))
    rule("flight pipeline does not reference the actuator path (C++ guard parity)",
         hits_where(lambda r: r in ("cansat/core/flight_state_manager.py", "cansat/core/flight_software.py",
                                    "cansat/core/event_detector.py", "cansat/core/sensor_validator.py",
                                    "cansat/core/recovery_manager.py"),
                    lambda r, c: any(k in c for k in ("ActuatorDriver", "ActuatorManager", "DeploymentInterlock"))
                    and "actuator path referenced" or None))
    def bad_get(r, c):
        if ".get()" not in c or r == "cansat/core/param.py":
            return None
        lhs = c.split("=", 1)[0] if "=" in c.split(".get()", 1)[0] else ""
        names = [n.strip() for n in lhs.split(",")]
        if ".get()[" in c or len(names) != 2 or names[0] in ("", "_"):
            return "Param.get() must be unpacked as `ok, value = p.get()` (or use require())"
        return None
    rule("Param.get() results are always unpacked and checked; never indexed", hits_where(in_pkg, bad_get))
    rule("simulator does not reference the actuator path (C++ guard parity)",
         hits_where(lambda r: r.startswith("cansat/sim/"),
                    lambda r, c: any(k in c for k in ("ActuatorDriver", "ActuatorManager", "DeploymentInterlock",
                                                      "actuator_manager", "deployment_interlock", "mock.actuators"))
                    and "actuator path referenced from the simulator" or None))
    flight_dirs = ("cansat/core/", "cansat/config/", "cansat/hal/")
    rule("flight code never imports the simulator, the mocks or ctypes",
         hits_where(lambda r: r.startswith(flight_dirs) or r in ("cansat/guards.py", "cansat/boot_checks.py"),
                    lambda r, c: "flight code imports laptop-only code"
                    if ((any(m in c for m in ("cansat.sim", "cansat.mock")) and "import" in c)
                        or "ctypes" in _imports(c)) else None))
    rule("no struct.Struct in the package (MicroPython struct has no Struct class)",
         hits_where(in_pkg, lambda r, c: "struct.Struct" in c and "struct.Struct (not in MicroPython)" or None))
    rule("no hardware driver package (" + HARDWARE_DIR + ") exists yet",
         [HARDWARE_DIR] if os.path.isdir(os.path.join(root, HARDWARE_DIR)) else [])

    # ---- configuration: no invented pins, values or defaults ----
    hw = code.get("cansat/config/hardware_config.py", [])
    pin_hits = []
    for n, c in hw:
        s = c.strip()
        if s.startswith("PIN_") and "=" in s and not s.startswith("PIN_TBD"):
            if s.split("=", 1)[1].strip() != "PIN_TBD":
                pin_hits.append("cansat/config/hardware_config.py:%d: %s" % (n, s))
        if s.startswith("HC12_UART_BAUD") and s.split("=", 1)[1].strip() != "0":
            pin_hits.append("cansat/config/hardware_config.py:%d: %s" % (n, s))
    rule("every pin in hardware_config.py is PIN_TBD and HC12_UART_BAUD is 0 (OD-054, OD-055)", pin_hits)
    rule("no Pin(<number>) anywhere (pins come only from hardware_config)",
         hits_where(lambda r: True, lambda r, c: "Pin(" in c and c.split("Pin(", 1)[1][:1].isdigit()
                    and "literal pin number" or None))
    rule("no SYNTHETIC_ values outside tests/ and cansat/sim/",
         hits_where(lambda r: not r.startswith("tests/") and not r.startswith("cansat/sim/"),
                    lambda r, c: "SYNTHETIC_" in c and "SYNTHETIC_ value" or None))
    rule("cansat/config never assigns a Param value (no defaults)",
         hits_where(lambda r: r.startswith("cansat/config/"),
                    lambda r, c: ".set(" in c and "Param.set() in config" or None))

    # ---- syntax (CPython parser; MicroPython parser NOT available here) ----
    syn = []
    for rel, text in files.items():
        try:
            compile(text, rel, "exec")
        except SyntaxError as e:
            syn.append("%s:%s: %s" % (rel, e.lineno, e.msg))
    rule("every .py file parses (CPython only; MicroPython parsing is UNVERIFIED)", syn)
    return results


def main(argv):
    root = os.path.abspath(argv[1]) if len(argv) > 1 else DEFAULT_ROOT
    results = scan(root)
    failed = 0
    for name, hits in results:
        if hits:
            failed += 1
            print("[FAIL] " + name)
            for h in hits:
                print("         " + h)
        else:
            print("[PASS] " + name)
    print("scan_guards: %d passed, %d failed  (weaker than the C++ compile-time guards; see README)"
          % (len(results) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
