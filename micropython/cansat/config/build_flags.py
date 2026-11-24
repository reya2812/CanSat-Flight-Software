# build_flags.py - build switches.  (port of include/config/BuildFlags.h)
#
# [TEAM DECISION] Physical actuation is disabled. No physical servo or buzzer
# output code exists in this port at all (D-017); the actuator interface has
# mock implementations only.
#
# WEAKER THAN C++: in C++, setting CANSAT_ENABLE_PHYSICAL_ACTUATORS=1 stops the
# build with #error. Python has no compile step. Here the equivalent is
# (a) boot_checks.run_boot_checks(), which refuses to start, and
# (b) tools/scan_guards.py, which fails the build. Editing this file to True
# makes both refuse; editing them out removes the protection.

# True only when running the flight software on the ESP32 (set by main.py on
# the board; laptop tests and simulation leave it False).
TARGET_HARDWARE = False

# Must stay False until OD-059 is closed by the team.
PHYSICAL_ACTUATORS_ENABLED = False

# Set True only when an approved flight-parameter source exists (OD-057, OD-060).
FLIGHT_PARAMS_APPROVED = False
