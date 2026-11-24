# boot_checks.py - refuse to start when the build is not safe to run (D-017).
#
# Replaces the C++ compile-time guards (#error / static_assert), which Python
# cannot express. WEAKER than C++: these checks run at boot, so the flight
# software must call enforce_boot_checks() before anything else (main.py on
# the board, the simulator on the laptop), and anyone who edits or skips the
# call removes the protection. tools/scan_guards.py repeats the source rules
# at build time.
#
# Checks:
#   B1 build_flags.PHYSICAL_ACTUATORS_ENABLED is False (C++: #error).
#   B2 every registered actuator driver reports is_physical() False.
#   B3 no actuator output code in the package sources (guards.ACTUATOR_TOKENS,
#      physical is_physical()), and no unscannable .mpy files.
#   B5 a resolved SD-CS / HC-12-SET output pin does not share a GPIO with an
#      actuator pin (skipped while pins are TBD).
#   B4 hardware target only: every required pin/setting resolved
#      (C++: static_assert in HardwareConfig.h) and flight parameters approved
#      (C++: #error in FlightParams.h).
from cansat import guards
from cansat.config import build_flags, hardware_config


class BootRefused(Exception):
    pass


def run_boot_checks(package_root, actuator_drivers=(), target_hardware=None):
    """Return a list of failure strings (empty = safe to start).

    package_root: directory that contains the `cansat` package (the board's
    filesystem root, or micropython/ on the laptop).
    """
    if target_hardware is None:
        target_hardware = build_flags.TARGET_HARDWARE
    fails = []
    if build_flags.PHYSICAL_ACTUATORS_ENABLED is not False:
        fails.append("B1 PHYSICAL_ACTUATORS_ENABLED is not False (OD-059 not closed)")
    for d in actuator_drivers:
        try:
            phys = d.is_physical()
        except Exception as e:  # a driver that cannot answer is treated as physical
            phys = True
            fails.append("B2 actuator driver is_physical() raised " + repr(e))
        if phys is not False:
            fails.append("B2 physical actuator driver registered: " + type(d).__name__)
    for v in guards.actuator_violations(package_root):
        fails.append("B3 " + v)
    for m in guards.find_unscannable(package_root):
        fails.append("B3 unscannable precompiled module (cannot check for actuator code): " + m)
    for msg in output_pin_conflicts():
        fails.append("B5 " + msg)
    if target_hardware:
        for item in hardware_config.unresolved_items():
            fails.append("B4 unresolved hardware item: " + item)
        if build_flags.FLIGHT_PARAMS_APPROVED is not True:
            fails.append("B4 flight parameters not approved (OD-057) and stuck-switch policy undecided (OD-060)")
    return fails


def output_pin_conflicts():
    """B5: a resolved non-actuator output pin must not share a GPIO with an actuator
    pin or with the other allowed output. Unresolved (PIN_TBD) pins are skipped:
    nothing is assigned here."""
    hc = hardware_config
    tbd = hc.PIN_TBD
    act = [(n, getattr(hc, n)) for n in dir(hc)
           if n.startswith(guards.ACTUATOR_PIN_PREFIXES) and getattr(hc, n) != tbd]
    outs = [(n, getattr(hc, n)) for n in guards.ALLOWED_OUTPUT_PIN_NAMES if getattr(hc, n) != tbd]
    out = []
    for n, v in outs:
        for an, av in act:
            if v == av:
                out.append("output pin %s shares GPIO %d with actuator pin %s" % (n, v, an))
    if len(outs) == 2 and outs[0][1] == outs[1][1]:
        out.append("output pins %s and %s share GPIO %d" % (outs[0][0], outs[1][0], outs[0][1]))
    return out


def enforce_boot_checks(package_root, actuator_drivers=(), target_hardware=None):
    fails = run_boot_checks(package_root, actuator_drivers, target_hardware)
    if fails:
        raise BootRefused("boot refused:\n  " + "\n  ".join(fails))
