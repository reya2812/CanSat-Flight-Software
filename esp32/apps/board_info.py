# board_info.py - READ-ONLY board report: firmware, chip, MAC, ESP-NOW support.
#
#     mpremote connect <PORT> run esp32/apps/board_info.py
#
# Writes nothing to the board's filesystem, configures no pins, sends nothing
# over the radio. Turning the Wi-Fi station interface on is needed to read the
# MAC; it does not connect to anything.
import gc
import os
import sys

print("== CanSat board info (read-only) ==")
print("implementation:", sys.implementation)
print("version       :", sys.version)
try:
    u = os.uname()
    print("uname         : sysname=%s release=%s version=%s machine=%s" % (u.sysname, u.release, u.version, u.machine))
except Exception as e:
    print("uname         : unavailable (%r)" % (e,))
try:
    import machine
    print("cpu freq      : %d MHz" % (machine.freq() // 1000000))
    print("unique_id     : %s" % ":".join("%02x" % b for b in machine.unique_id()))
except Exception as e:
    print("machine       : unavailable (%r)" % (e,))
try:
    import esp
    print("flash size    : %d bytes" % esp.flash_size())
except Exception as e:
    print("flash size    : unavailable (%r)" % (e,))
try:
    gc.collect()
    print("heap free     : %d bytes" % gc.mem_free())
except Exception as e:
    print("heap free     : unavailable (%r)" % (e,))
mac = None
try:
    import network
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    mac = ":".join("%02x" % b for b in sta.config("mac"))
    print("STA MAC       : %s   <- put this in esp32/config/radio_config.py" % mac)
except Exception as e:
    print("STA MAC       : unavailable (%r)" % (e,))
try:
    import espnow
    print("espnow module : PRESENT (MAX_DATA_LEN=%s)" % getattr(espnow, "MAX_DATA_LEN", "?"))
except ImportError:
    print("espnow module : MISSING - flash the official ESP32_GENERIC firmware (v1.20 or later)")
try:
    from board_role import ROLE
    print("deployed role : %s" % ROLE)
except ImportError:
    print("deployed role : (none - not deployed with esp32/tools/deploy.py)")
try:
    import radio_config as RC
    f, g = RC.FLIGHT_MAC, RC.GROUND_MAC
    print("radio_config  : FLIGHT_MAC=%s GROUND_MAC=%s" % (f, g))
    if mac is not None:
        if f is not None and mac == f.lower():
            print("              : this board IS the configured FLIGHT board")
        elif g is not None and mac == g.lower():
            print("              : this board IS the configured GROUND board")
        else:
            print("              : this board matches NEITHER configured MAC")
except ImportError:
    print("radio_config  : (not on the board yet)")
