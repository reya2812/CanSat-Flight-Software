# i2c_scan_standalone.py - minimal, self-contained I2C bus investigation for the flight ESP32.
#
#     mpremote connect <FLIGHT_PORT> run esp32/apps/i2c_scan_standalone.py
#
# Imports ONLY machine, time and sys: no project drivers, config or library.
# Nothing is written to any sensor register. An I2C scan sends each address
# with the write bit and ZERO data bytes, then releases the bus; that is the
# only bus traffic. No output pin is configured (pins are inputs or are driven
# open-drain by the I2C peripheral itself). Nothing is saved to the board.
#
# What it reports, kept separate:
#   1. line levels as plain inputs: no pull / internal pull-up / internal pull-down
#      (a line that stays HIGH with the internal pull-DOWN enabled has a real,
#      powered external pull-up; one that drops LOW was floating)
#   2. hardware I2C bus 0 and 1, at 100 kHz and 10 kHz: constructor error vs
#      scan error vs empty scan vs devices found, plus the pins MicroPython
#      reports it actually configured
#   3. software (bit-banged) I2C at the same rates
#   4. line levels again afterwards (did a scan leave a line stuck low?)
SDA = 21
SCL = 22
FREQS = (100000, 10000)
HW_IDS = (0, 1)

try:
    import machine
except ImportError:
    machine = None


def _levels(m, label, out):
    res = {}
    for pull_name, pull in (("no pull", None), ("pull-up", getattr(m.Pin, "PULL_UP", None)),
                            ("pull-down", getattr(m.Pin, "PULL_DOWN", None))):
        if pull_name != "no pull" and pull is None:
            continue
        try:
            a = m.Pin(SDA, m.Pin.IN, pull)
            b = m.Pin(SCL, m.Pin.IN, pull)
            _sleep_ms(5)
            res[pull_name] = (a.value(), b.value())
            out("  %-10s %-9s SDA(GPIO%d)=%d  SCL(GPIO%d)=%d" % (label, pull_name, SDA, a.value(), SCL, b.value()))
        except Exception as e:
            out("  %-10s %-9s ERROR %r" % (label, pull_name, e))
    _release(m)
    return res


def _release(m):
    try:
        m.Pin(SDA, m.Pin.IN)
        m.Pin(SCL, m.Pin.IN)
    except Exception:
        pass


def _sleep_ms(ms):
    import time
    f = getattr(time, "sleep_ms", None)
    if f:
        f(ms)
    else:
        time.sleep(ms / 1000.0)


def _scan(kind, make, out):
    """Return ('INIT_ERROR'|'SCAN_ERROR'|'EMPTY'|'FOUND', detail, addrs)."""
    try:
        bus = make()
    except Exception as e:
        out("  %-28s INIT_ERROR  %r" % (kind, e))
        return "INIT_ERROR", repr(e), []
    try:
        addrs = sorted(bus.scan())
    except Exception as e:
        out("  %-28s SCAN_ERROR  %r   (bus object: %s)" % (kind, e, _repr(bus)))
        return "SCAN_ERROR", repr(e), []
    if addrs:
        out("  %-28s FOUND %d     %s   (bus object: %s)" % (kind, len(addrs), " ".join("0x%02X" % a for a in addrs),
                                                         _repr(bus)))
        return "FOUND", "", addrs
    out("  %-28s EMPTY       no address ACKed   (bus object: %s)" % (kind, _repr(bus)))
    return "EMPTY", "", []


def _repr(bus):
    try:
        return repr(bus)
    except Exception:
        return "?"


def main(m=None, out=print):
    m = m if m is not None else machine
    results = []
    out("== Standalone I2C investigation (no project code; no register writes) ==")
    if m is None:
        out("RESULT: no `machine` module - run this on the ESP32 under MicroPython")
        return results
    try:
        import sys
        out("firmware: %s" % (sys.version,))
    except Exception:
        pass
    out("pins under test: SDA=GPIO%d  SCL=GPIO%d" % (SDA, SCL))
    out("[1] line levels before any I2C use")
    before = _levels(m, "before", out)
    out("[2] hardware I2C (machine.I2C)")
    for bid in HW_IDS:
        for f in FREQS:
            kind = "hw I2C(%d) %6d Hz" % (bid, f)
            st, detail, addrs = _scan(kind, lambda: m.I2C(bid, scl=m.Pin(SCL), sda=m.Pin(SDA), freq=f), out)
            results.append((kind, st, detail, addrs))
            _release(m)
    out("[3] software I2C (machine.SoftI2C)")
    soft = getattr(m, "SoftI2C", None)
    if soft is None:
        out("  machine.SoftI2C not available in this firmware")
    else:
        for f in FREQS:
            kind = "SoftI2C %6d Hz" % f
            st, detail, addrs = _scan(kind, lambda: soft(scl=m.Pin(SCL), sda=m.Pin(SDA), freq=f), out)
            results.append((kind, st, detail, addrs))
            _release(m)
    out("[4] line levels after all scans")
    after = _levels(m, "after", out)
    _summary(results, before, after, out)
    return results


def _summary(results, before, after, out):
    out("== SUMMARY ==")
    counts = {}
    for _, st, _, _ in results:
        counts[st] = counts.get(st, 0) + 1
    out("  scans: " + ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))
    found = sorted(set(a for r in results for a in r[3]))
    if found:
        out("  addresses seen on any scan: " + " ".join("0x%02X" % a for a in found))
    pd = before.get("pull-down")
    if pd is not None:
        for name, v in (("SDA", pd[0]), ("SCL", pd[1])):
            if v == 1:
                out("  %s stays HIGH against the internal pull-down: an external pull-up is present and powered" % name)
            else:
                out("  %s drops LOW with the internal pull-down: NO powered external pull-up seen on this line "
                    "(earlier HIGH readings were a floating input or the internal pull-up)" % name)
    np = before.get("no pull")
    if np is not None and (np[0] == 0 or np[1] == 0):
        out("  a line reads LOW with no pull before any scan: something holds it low")
    np_after = after.get("no pull")
    if np_after is not None and np is not None and np_after != np:
        out("  line levels changed after scanning: before %s, after %s" % (np, np_after))
    out("  Observations only. They narrow down where to measure; they do not by themselves prove a wiring fault.")


if __name__ == "__main__":
    main()
