# cs_diag.py - flight-board hardware diagnostic (logic; app wrapper: esp32/apps/flight_diag.py).
#
# Uses the SAME drivers as the flight node (cs_sensors / cs_bmp280 / cs_mpu /
# cs_ina219 / cs_sd), so a PASS here exercises the code that sends telemetry.
# bringup/esp32_hw_diag.py remains as an independent, simpler cross-check.
#
# Every result carries an EVIDENCE LEVEL, and the four levels are never mixed up:
#   (laptop) SOFTWARE TEST  - esp32/tests pass: logic only, says nothing about hardware
#   DETECTED                - something ACKed at the address on the I2C bus
#   IDENTIFIED              - its ID register holds a supported chip's value
#   PLAUSIBLE               - it returned readings inside physical limits
#   PHYSICALLY VALIDATED    - NEVER set by this program: needs the human checks
#                             in docs/10_esp32_espnow_bringup.md section 9
# No servo, buzzer, deployment, PWM or output-pin code is run.
import cs_proto as P
import cs_sd
from cs_sensors import SensorSuite
from cs_util import format_mac, sleep_ms, ticks_ms

PASS, FAIL, WARN, SKIP, INFO = "PASS", "FAIL", "WARN", "SKIP", "INFO"
EV_NONE = "-"
EV_DETECTED = "DETECTED"
EV_IDENTIFIED = "IDENTIFIED"
EV_PLAUSIBLE = "PLAUSIBLE"


class DiagReport:
    def __init__(self, out=print):
        self.rows = []
        self._out = out

    def add(self, status, name, evidence, detail):
        self.rows.append((status, name, evidence, detail))
        self._out("[%s] %-22s {%s} %s" % (status, name, evidence, detail))

    def note(self, text):
        self._out("        " + text)

    def status(self, name):
        return [r[0] for r in self.rows if r[1] == name]

    def evidence(self, name):
        return [r[2] for r in self.rows if r[1] == name]

    def counts(self):
        c = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0, INFO: 0}
        for r in self.rows:
            c[r[0]] += 1
        return c


def _guard(rep, name, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # isolation: one failing check never stops the rest
        rep.add(FAIL, name, EV_NONE, "unexpected error: %r" % (e,))
        return None


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def run_diag(machine_mod, os_mod, cfg, rc=None, out=print, sleep=sleep_ms, now_fn=ticks_ms, network_mod=None,
             espnow_present=None, sys_mod=None, samples=10, token="0", open_fn=None):
    rep = DiagReport(out)
    out("== CanSat FLIGHT-board diagnostic (bench check; NOT flight validation) ==")
    out("Pins are USER-REPORTED and UNVERIFIED (OD-077). Register maps are [ASSUMPTION] (recalled datasheets).")
    out("Not run: servos, buzzers, deployment, batteries/charging, radio range. No output pins are configured.")
    if machine_mod is None:
        rep.add(FAIL, "Platform", EV_NONE, "no `machine` module: run this on the ESP32 under MicroPython")
        return rep
    _guard(rep, "Board", _board, rep, machine_mod, os_mod, sys_mod)
    _guard(rep, "MAC", _mac, rep, network_mod, rc)
    if espnow_present is None:
        rep.add(SKIP, "ESP-NOW module", EV_NONE, "not checked")
    elif espnow_present:
        rep.add(PASS, "ESP-NOW module", EV_NONE, "`import espnow` works in this firmware (radio not activated)")
    else:
        rep.add(FAIL, "ESP-NOW module", EV_NONE, "`import espnow` failed: flash the official ESP32_GENERIC firmware")
    suite = _guard(rep, "I2C", _i2c_and_discover, rep, machine_mod, cfg, now_fn)
    if suite is not None and suite.scan:
        _guard(rep, "Sampling", _sample, rep, suite, samples, sleep, now_fn, cfg)
        _guard(rep, "IMU", _imu_eval, rep, suite)
        _guard(rep, "Barometers", _baro_eval, rep, suite, cfg)
        _guard(rep, "INA219", _ina_eval, rep, suite)
    else:
        for n in ("IMU", "Barometers", "INA219"):
            rep.add(SKIP, n, EV_NONE, "I2C bus unavailable or empty")
    _guard(rep, "SD card", _sd, rep, machine_mod, os_mod, cfg, token, open_fn)
    c = rep.counts()
    out("== SUMMARY: PASS=%d FAIL=%d WARN=%d SKIP=%d INFO=%d ==" % (c[PASS], c[FAIL], c[WARN], c[SKIP], c[INFO]))
    out("Evidence: DETECTED = answered on the bus; IDENTIFIED = ID register matched; PLAUSIBLE = readings within")
    out("physical limits. NOTHING here is PHYSICALLY VALIDATED: that needs the bench checklist (docs/10 section 9),")
    out("e.g. tilting the IMU, comparing pressure with a reference, and measuring the rail with a multimeter.")
    return rep


def _board(rep, machine_mod, os_mod, sys_mod):
    parts = []
    if sys_mod is not None:
        impl = getattr(sys_mod, "implementation", None)
        parts.append("impl=%s %s" % (getattr(impl, "name", "?"), getattr(impl, "version", "?")))
    try:
        u = os_mod.uname()
        parts.append("release=%s machine=%s" % (u.release, u.machine))
    except Exception:
        pass
    try:
        parts.append("cpu=%d MHz" % (machine_mod.freq() // 1000000))
    except Exception:
        pass
    rep.add(INFO, "Board", EV_NONE, ", ".join(parts) or "no details available")


def _mac(rep, network_mod, rc):
    if network_mod is None:
        rep.add(SKIP, "MAC", EV_NONE, "network module not available")
        return
    sta = network_mod.WLAN(network_mod.STA_IF)
    sta.active(True)
    mac = format_mac(bytes(sta.config("mac")))
    if rc is None or getattr(rc, "FLIGHT_MAC", None) is None:
        rep.add(INFO, "MAC", EV_NONE, "STA MAC %s (radio_config.FLIGHT_MAC not set yet)" % mac)
        return
    f = rc.FLIGHT_MAC.lower()
    g = (rc.GROUND_MAC or "").lower()
    if mac == f:
        rep.add(PASS, "MAC", EV_NONE, "STA MAC %s matches radio_config.FLIGHT_MAC" % mac)
    elif mac == g:
        rep.add(FAIL, "MAC", EV_NONE, "STA MAC %s is the GROUND board's MAC: wrong board" % mac)
    else:
        rep.add(WARN, "MAC", EV_NONE, "STA MAC %s does not match FLIGHT_MAC %s" % (mac, f))


def _i2c_and_discover(rep, machine_mod, cfg, now_fn):
    try:
        i2c = machine_mod.I2C(cfg.I2C_ID, scl=machine_mod.Pin(cfg.I2C_SCL), sda=machine_mod.Pin(cfg.I2C_SDA),
                              freq=cfg.I2C_FREQ_HZ)
    except Exception as e:
        rep.add(FAIL, "I2C init", EV_NONE, "SDA=GPIO%d SCL=GPIO%d: %r" % (cfg.I2C_SDA, cfg.I2C_SCL, e))
        return None
    suite = SensorSuite(cfg).discover(i2c, now_fn())
    hexs = " ".join("0x%02X" % a for a in suite.scan) or "(none)"
    if suite.scan_error:
        rep.add(FAIL, "I2C scan", EV_NONE, suite.scan_error)
    elif not suite.scan:
        rep.add(FAIL, "I2C scan", EV_NONE, "no device answered: check SDA/SCL, 3.3 V, GND and pull-ups")
    elif len(suite.scan) > 32:
        rep.add(FAIL, "I2C scan", EV_DETECTED, "%d addresses answered: bus shorted or pull-ups missing" % len(suite.scan))
    else:
        rep.add(PASS, "I2C scan", EV_DETECTED, "%d device(s): %s" % (len(suite.scan), hexs))
    known = {0x0C, 0x40, 0x68, 0x69, 0x76, 0x77, getattr(cfg, "INA219_ADDR", 0x40)}
    other = [a for a in suite.scan if a not in known]
    if other:
        rep.add(INFO, "Other I2C devices", EV_DETECTED, "not identified: " + " ".join("0x%02X" % a for a in other))
    if 0x0C in suite.scan:
        rep.add(INFO, "Magnetometer", EV_DETECTED, "a device answers at 0x0C (AK8963?) - not used")
    for ch in suite.channels() + tuple(suite.extra):
        if ch.driver is None:
            continue
        ev = EV_IDENTIFIED if getattr(ch.driver, "chip", None) else EV_DETECTED
        if ch.status == P.ST_UNKNOWN_CHIP:
            rep.add(WARN, "ID " + ch.label, EV_DETECTED, ch.error)
        elif not ch.init_ok:
            rep.add(FAIL, "ID " + ch.label, ev, "%s: %s" % (ch.name(), ch.error))
        else:
            extra = ""
            d = ch.driver
            if d.kind == "imu":
                extra = " WHO_AM_I=0x%02X, ranges read from chip +-%d g / +-%d dps%s" % (
                    d.who, d.accel_fs_g, d.gyro_fs_dps, " (SLEEP bit cleared)" if d.woke else "")
            elif d.kind == "baro":
                extra = " chip ID 0x%02X" % d.chip_id
            elif d.kind == "power":
                ev = EV_DETECTED  # INA219 has no ID register
                extra = " config=0x%04X%s" % (d.config, "" if d.config_is_default else " (NOT the power-on value)")
            rep.add(PASS if (d.kind != "power" or d.config_is_default) else WARN, "ID " + ch.label, ev,
                    ch.name() + extra)
    if suite.imu.driver is None:
        rep.add(FAIL, "ID imu", EV_NONE, "no device at 0x68/0x69 (MPU-family addresses)")
    if suite.baro1.driver is None:
        rep.add(FAIL, "ID baro1", EV_NONE, "no device at 0x76/0x77")
    if suite.power.driver is None:
        rep.add(FAIL, "ID power", EV_NONE, "no device at 0x%02X" % cfg.INA219_ADDR)
    for ch in suite.extra:
        rep.add(INFO, "Unused " + ch.label, EV_DETECTED, "%s answered but only one IMU is used" % ch.name())
    return suite


def _sample(rep, suite, samples, sleep, now_fn, cfg):
    suite.history = {"baro1": [], "baro2": [], "imu": [], "power": []}
    t0 = now_fn()
    for _ in range(samples):
        now = now_fn()
        suite.sample(now, (now - t0) & 0xFFFFFFFF)
        for ch in suite.channels():
            if ch.last is not None:
                suite.history[ch.label].append(ch.last)
        sleep(cfg.SENSOR_PERIOD_MS)
    rep.add(INFO, "Sampling", EV_NONE, "%d samples per sensor, %d ms apart" % (samples, cfg.SENSOR_PERIOD_MS))


def _imu_eval(rep, suite):
    ch = suite.imu
    if ch.driver is None or (not ch.init_ok and not suite.history["imu"]):
        rep.add(SKIP, "IMU data", EV_NONE, "no identified IMU")
        return
    rs = suite.history["imu"]
    ok = [r for r in rs if r.valid]
    if not ok:
        last = rs[-1] if rs else None
        rep.add(FAIL, "IMU data", EV_IDENTIFIED, "no valid sample (%s)" % (last.error if last else ch.error))
        return
    raws = [(r.ax_g, r.ay_g, r.az_g, r.gx_dps, r.gy_dps, r.gz_dps) for r in ok]
    stuck = len(ok) > 1 and all(x == raws[0] for x in raws)
    mag = _mean([(r.ax_g ** 2 + r.ay_g ** 2 + r.az_g ** 2) ** 0.5 for r in ok])
    gyro = [_mean([r.gx_dps for r in ok]), _mean([r.gy_dps for r in ok]), _mean([r.gz_dps for r in ok])]
    drdy = len([r for r in ok if r.data_ready])
    if stuck:
        rep.add(WARN, "IMU data", EV_IDENTIFIED, "%d/%d valid but ALL IDENTICAL (frozen output?)" % (len(ok), len(rs)))
    else:
        rep.add(PASS, "IMU data", EV_PLAUSIBLE, "%d/%d valid samples, values change between samples" % (len(ok), len(rs)))
    rep.note("mean |a| = %.3f g (about 1 g if stationary - a bench observation, not a pass criterion)" % mag)
    rep.note("mean gyro = %+.2f %+.2f %+.2f dps (near 0 if stationary; offsets are normal, uncalibrated)" % tuple(gyro))
    temps = [r.temp_c for r in ok if r.temp_valid]
    rep.note("die temperature = %s" % ("%.1f C" % _mean(temps) if temps else "invalid"))
    rep.note("DATA_RDY bit seen in %d/%d samples (bench check H-IMU-3)" % (drdy, len(ok)))
    if any(r.saturated for r in ok):
        rep.add(WARN, "IMU saturation", EV_PLAUSIBLE, "an accelerometer axis hit full scale")


def _baro_eval(rep, suite, cfg):
    for label in ("baro1", "baro2"):
        ch = getattr(suite, label)
        if ch.driver is None:
            if label == "baro1" or cfg.EXPECTED_BAROMETERS >= 2:
                rep.add(WARN if label == "baro2" else FAIL, label, EV_NONE, "not present")
            continue
        rs = suite.history[label]
        ok = [r for r in rs if r.valid]
        if not ok:
            last = rs[-1] if rs else None
            rep.add(FAIL, label, EV_IDENTIFIED if ch.driver.chip else EV_DETECTED,
                    "%s: no valid sample (%s)" % (ch.name(), last.error if last else ch.error))
            continue
        ps = [r.pressure_pa for r in ok]
        ts = [r.temp_c for r in ok]
        rep.add(PASS, label, EV_PLAUSIBLE, "%s: %d/%d valid, P %.1f Pa (spread %.1f Pa), T %.2f C" % (
            ch.name(), len(ok), len(rs), _mean(ps), max(ps) - min(ps), _mean(ts)))
    if suite.baro1.valid() and suite.baro2.valid():
        d = suite.baro1.last.pressure_pa - suite.baro2.last.pressure_pa
        rep.note("baro1 - baro2 = %.1f Pa (two sensors side by side should roughly agree; uncalibrated)" % d)
    if suite.alt_m is not None:
        rep.note("altitude vs %s reference %.1f Pa: %.2f m" % (
            "first-reading" if suite.reference_auto else "configured", suite.reference_pa, suite.alt_m))
    n = len(suite.baro_identified)
    if suite.baro_dup_suspect:
        rep.add(WARN, "Baro duplicates", EV_DETECTED,
                "expected %d BMP280s, identified %d at %s. Two devices at the SAME address cannot be told apart"
                % (cfg.EXPECTED_BAROMETERS, n, " ".join("0x%02X" % a for a in suite.baro_identified) or "-"))
        rep.note("on one bus: both answer together and data may be silently corrupted. Test each module ALONE,")
        rep.note("or change one module's SDO/address strap so they use 0x76 and 0x77.")
    else:
        rep.add(INFO, "Baro mapping", EV_IDENTIFIED, "%d BMP280-family devices at %s. Which is the GY-91's and which "
                "the standalone is NOT known to software: disconnect one to map them" % (
                    n, " ".join("0x%02X" % a for a in suite.baro_identified)))


def _ina_eval(rep, suite):
    ch = suite.power
    if ch.driver is None:
        rep.add(SKIP, "INA219 data", EV_NONE, "not present")
        return
    rs = suite.history["power"]
    last = rs[-1] if rs else ch.last
    if last is None or not last.comm_ok:
        rep.add(FAIL, "INA219 data", EV_DETECTED, "read failed: %s" % (last.error if last else ch.error))
        return
    raw = "raw bus %.3f V, raw shunt %.2f mV, CNVR=%d OVF=%d" % (
        last.raw_bus_v, last.raw_shunt_mv, 1 if last.data_ready else 0, 1 if last.overflow else 0)
    if ch.driver.gated():
        rep.add(INFO, "INA219 data", EV_DETECTED, "registers readable; values NOT used: no monitored circuit "
                "declared (INA219_BUS_CONNECTED / INA219_SHUNT_CONNECTED False). " + raw)
        return
    parts = []
    if last.bus_valid:
        parts.append("bus %.3f V" % last.bus_v)
    if last.current_valid:
        parts.append("current %.1f mA (shunt %.2f mV / %.3f ohm)" % (last.current_ma, last.shunt_mv,
                                                                     ch.driver.shunt_ohms))
    if last.status == P.ST_IMPLAUSIBLE:
        rep.add(WARN, "INA219 data", EV_DETECTED, last.error + "; " + raw)
    else:
        rep.add(PASS, "INA219 data", EV_PLAUSIBLE, ", ".join(parts) + " - compare with a multimeter (H-PWR-2)")


def _sd(rep, machine_mod, os_mod, cfg, token, open_fn):
    res = cs_sd.sd_selftest(machine_mod, os_mod, cfg, token, open_fn)
    if res.skipped:
        rep.add(SKIP, "SD card", EV_NONE, res.steps[0][2])
        return
    if res.ok:
        rep.add(PASS, "SD card", EV_PLAUSIBLE, "write / remount / read-back / verify / delete / unmount OK%s" % (
            ", %d KiB free" % res.free_kib if res.free_kib is not None else ""))
    else:
        f = res.failed_step()
        rep.add(FAIL, "SD card", EV_NONE if f and f[0] in ("driver", "init") else EV_DETECTED,
                "failed at '%s': %s" % (f[0], f[2]) if f else "failed")
    for name, ok, detail in res.steps:
        rep.note("%-8s %s %s" % (name, "ok " if ok else "ERR", detail))
