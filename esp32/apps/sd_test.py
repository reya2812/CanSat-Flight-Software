# sd_test.py - bench tool: check the micro-SD card works (D-023 wiring:
# SCK 18, MISO 19, MOSI 23, CS 5, SPI at 4 MHz; 20 MHz gave CRC errors).
#
#     python3 -m mpremote connect <FLIGHT_PORT> run esp32/apps/sd_test.py
#
# Mounts the card, writes ONE test file (/sd/cs_sdtest.bin, 100 kB), unmounts,
# remounts, reads it back and compares every byte, deletes it and unmounts.
# Touches no other file, and refuses to run if the test file already exists.
# The card must be FAT32 (MicroPython cannot read exFAT).
import os, time, machine, vfs
F = "/sd/cs_sdtest.bin"
sd = machine.SDCard(slot=2, sck=machine.Pin(18), miso=machine.Pin(19), mosi=machine.Pin(23), cs=machine.Pin(5), freq=4000000)
mounted = False
try:
    vfs.mount(sd, "/sd"); mounted = True
    print("1. mounted read-write")
    if "cs_sdtest.bin" in os.listdir("/sd"):
        raise OSError("test file already exists; not touching it")
    N = 25
    def chunk(k):
        return bytes(((i * 7 + k * 13 + 3) & 0xFF) for i in range(4096))
    t = time.ticks_ms()
    with open(F, "wb") as f:
        for k in range(N):
            f.write(chunk(k))
    dt = time.ticks_diff(time.ticks_ms(), t)
    total = N * 4096
    print("2. wrote %d bytes in %d ms (%.0f kB/s)" % (total, dt, total / max(dt, 1)))
    vfs.umount("/sd"); mounted = False
    vfs.mount(sd, "/sd"); mounted = True
    print("3. unmounted and remounted")
    t = time.ticks_ms()
    bad = 0
    with open(F, "rb") as f:
        for k in range(N):
            if f.read(4096) != chunk(k):
                bad += 1
        extra = f.read(1)
    dt = time.ticks_diff(time.ticks_ms(), t)
    ok = bad == 0 and not extra and os.stat(F)[6] == total
    print("4. read back %d bytes in %d ms (%.0f kB/s)" % (total, dt, total / max(dt, 1)))
    print("5. verify: %s (%d of %d chunks wrong)" % ("MATCH" if ok else "MISMATCH", bad, N))
    os.remove(F)
    print("6. test file deleted; root now: %s" % (os.listdir("/sd") or "(empty)"))
    print("RESULT: %s" % ("SD card PASSED write/read-back" if ok else "SD card FAILED verify"))
except Exception as e:
    print("FAILED: %r" % (e,))
finally:
    if mounted:
        vfs.umount("/sd"); print("unmounted")
    sd.deinit()
