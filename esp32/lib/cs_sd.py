# cs_sd.py - micro-SD bench self-test: init, mount, write, unmount, remount,
# read back, verify, delete, unmount. NOT flight logging (none exists yet).
#
# Gated by flight_config.SD_SUPPLY_CONFIRMED (default False): while False
# nothing touches the card. The ONLY file written is TEST_FILE, which is
# removed again; no other file on the card is opened, changed or deleted.
# `machine` and `os` are injected so the sequence is testable on the laptop.
import cs_proto as P

TEST_FILE = "cansat_sd_selftest.tmp"


class SdResult:
    def __init__(self):
        self.status = P.ST_NOT_PRESENT
        self.ok = False
        self.skipped = False
        self.steps = []      # (step, ok, detail)
        self.free_kib = None

    def step(self, name, ok, detail=""):
        self.steps.append((name, ok, detail))
        return ok

    def failed_step(self):
        for s in self.steps:
            if not s[1]:
                return s
        return None


def sd_selftest(machine_mod, os_mod, cfg, token="0", open_fn=None):
    if open_fn is None:
        open_fn = open
    res = SdResult()
    if getattr(cfg, "SD_SUPPLY_CONFIRMED", False) is not True:
        res.status = P.ST_DISABLED
        res.skipped = True
        res.step("gate", True, "SD_SUPPLY_CONFIRMED is False: card not touched. Confirm the module's "
                               "supply and 3.3 V logic compatibility first")
        return res
    if machine_mod is None or not hasattr(machine_mod, "SDCard"):
        res.status = P.ST_INIT_FAILED
        res.step("driver", False, "this firmware has no machine.SDCard")
        return res
    mp = cfg.SD_MOUNT_POINT
    path = mp + "/" + TEST_FILE
    payload = ("CANSAT SD SELF-TEST token=%s\n" % token) + "0123456789ABCDEF" * 32 + "\nEND\n"
    sd = None
    mounted = False
    try:
        try:
            sd = machine_mod.SDCard(slot=cfg.SD_SLOT, sck=machine_mod.Pin(cfg.SD_SCK),
                                    miso=machine_mod.Pin(cfg.SD_MISO), mosi=machine_mod.Pin(cfg.SD_MOSI),
                                    cs=machine_mod.Pin(cfg.SD_CS))
        except Exception as e:
            res.status = P.ST_INIT_FAILED
            res.step("init", False, "SDCard() failed: %r (wiring/supply/card inserted?)" % (e,))
            return res
        res.step("init", True, "SPI slot %d SCK=%d MISO=%d MOSI=%d CS=%d" % (
            cfg.SD_SLOT, cfg.SD_SCK, cfg.SD_MISO, cfg.SD_MOSI, cfg.SD_CS))
        try:
            os_mod.mount(sd, mp)
            mounted = True
        except Exception as e:
            res.status = P.ST_NOT_PRESENT
            res.step("mount", False, "%r (no card, not FAT-formatted, or SPI fault)" % (e,))
            return res
        res.step("mount", True, mp)
        try:
            st = os_mod.statvfs(mp)
            res.free_kib = st[0] * st[3] // 1024
        except Exception:
            pass
        try:
            with open_fn(path, "w") as f:
                n = f.write(payload)
            if n is not None and n != len(payload):
                raise OSError("short write %d/%d" % (n, len(payload)))
        except Exception as e:
            res.status = P.ST_READ_ERROR
            res.step("write", False, "%r (card write-protected or full?)" % (e,))
            return res
        res.step("write", True, "%d bytes to %s" % (len(payload), path))
        try:  # unmount + remount so the read-back comes from the card, not a cache
            os_mod.umount(mp)
            mounted = False
            os_mod.mount(sd, mp)
            mounted = True
        except Exception as e:
            res.status = P.ST_READ_ERROR
            res.step("remount", False, repr(e))
            return res
        res.step("remount", True)
        try:
            with open_fn(path, "r") as f:
                back = f.read()
        except Exception as e:
            res.status = P.ST_READ_ERROR
            res.step("read", False, repr(e))
            return res
        res.step("read", True, "%d bytes" % len(back))
        if back != payload:
            res.status = P.ST_IMPLAUSIBLE
            res.step("verify", False, "read-back differs from what was written (%d vs %d bytes)"
                     % (len(back), len(payload)))
            return res
        res.step("verify", True, "contents identical")
        try:
            os_mod.remove(path)
            res.step("cleanup", True, "test file removed")
        except Exception as e:
            res.step("cleanup", False, "could not remove %s: %r" % (path, e))
            res.status = P.ST_READ_ERROR
            return res
        res.status = P.ST_OK
        res.ok = True
        return res
    finally:
        if mounted:
            try:
                os_mod.umount(mp)
                res.step("unmount", True)
            except Exception as e:
                res.step("unmount", False, repr(e))
                res.ok = False
        if sd is not None:
            try:
                sd.deinit()
            except Exception:
                pass
