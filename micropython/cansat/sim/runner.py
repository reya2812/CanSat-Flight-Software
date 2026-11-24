# runner.py - executes a Scenario against the mock sensors and writes a CSV log.
# [SIMULATED] (port of firmware/sim/SimRunner.cpp; byte-identical output is the
# acceptance criterion). Never touches any actuator interface.
from cansat.mock import fault_injector as FI
from cansat.mock.sensors import MockBarometer, MockImu, MockPowerMonitor, MockSwitches
from cansat.mock.virtual_clock import VirtualClock
from cansat.core import types as T
from cansat.sim.flight_profile import FlightProfile

SIM_CSV_HEADER = ("truth_ms,boot,uptime_ms,segment,truth_alt_m,truth_vz_mps,truth_mounted,"
                  "baro_valid,p_pa,temp_c,"
                  "imu_valid,imu_sat,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,"
                  "pwr_valid,bus_v,i_ma,"
                  "sw_valid,sw1_raw,sw2_raw,"
                  "baro_comm_ok,baro_data_ready,imu_comm_ok,imu_data_ready,pwr_comm_ok,pwr_data_ready,"
                  "active_faults,events")


class SimSummary:
    def __init__(self, scenario):
        self.scenario = scenario
        self.ticks = self.sample_rows = self.booting_rows = 0
        self.baro_invalid = self.imu_invalid = self.imu_saturated = 0
        self.power_invalid = self.switch_invalid = self.resets = 0
        self.final_boot = 0
        self.log_write_failures = 0
        self.segment_sequence = []
        self.timeline = []


class SimHook:
    """Optional software-under-test plugged into the runner (flight software)."""

    def extra_header(self):
        raise NotImplementedError

    def banner_line(self):
        raise NotImplementedError

    def on_boot(self, baro_ok, imu_ok, power_ok, uptime_ms):
        raise NotImplementedError

    def on_reset(self):
        raise NotImplementedError

    def on_tick(self, frame, uptime_ms):
        raise NotImplementedError

    def empty_columns(self):
        raise NotImplementedError


def _in_tick(x, prev, now, first):
    return x <= now if first else (prev < x <= now)


def append_token(s, tok):
    tok = tok.replace(",", "/").replace(";", "/")
    return tok if not s else s + ";" + tok


def _active_fault_list(fi, t):
    s = ""
    for w in fi.windows():
        if FI.is_active(w, t):
            s = append_token(s, FI.target_name(w.target) + "." + FI.kind_name(w.kind))
    return s


def _b(v):
    return 1 if v else 0


def run(sc, out, hook=None):
    summ = SimSummary(sc.name)
    clock = VirtualClock()
    profile = FlightProfile(sc)
    faults = FI.FaultInjector()
    for w in sc.faults:
        faults.add(w)
    M32 = 0xFFFFFFFF
    baro = MockBarometer(clock, profile, faults, sc.noise, (sc.seed * 4 + 1) & M32)
    imu = MockImu(clock, profile, faults, sc.noise, (sc.seed * 4 + 2) & M32)
    power = MockPowerMonitor(clock, profile, faults, sc.noise, (sc.seed * 4 + 3) & M32)
    switches = MockSwitches(clock, profile, faults, sc.switch_closed_level_high[0], sc.switch_closed_level_high[1])

    def write(line):
        if not out.append(line):
            summ.log_write_failures += 1

    write("# SIMULATED - not hardware validation. All sensor values are SYNTHETIC.")
    write("# scenario: " + sc.name)
    write("# description: " + sc.description)
    write(hook.banner_line() if hook else "# no flight software or actuator is in the loop (Phase 2 step 2)")
    write(SIM_CSV_HEADER + (hook.extra_header() if hook else ""))

    def begin_all():
        b, i, p = baro.begin(), imu.begin(), power.begin()
        r = "BEGIN:baro=%s/imu=%s/power=%s" % ("ok" if b else "FAIL", "ok" if i else "FAIL", "ok" if p else "FAIL")
        if hook:
            h = hook.on_boot(b, i, p, clock.now_ms())
            if h:
                r += ";" + h
        return r

    end_ms = profile.total_ms() + sc.tail_ms
    tick = sc.tick_ms if sc.tick_ms > 0 else 1
    last_segment = -1
    was_booting = False
    prev = 0
    next_reset = 0
    t = 0
    while t <= end_ms:
        first = t == 0
        clock.advance_to(t)
        summ.ticks += 1
        events = ""
        if first:
            events = append_token(events, "BOOT:1")
            events = append_token(events, begin_all())
        truth = profile.truth_at(t)
        if truth.segment != last_segment:
            last_segment = truth.segment
            summ.segment_sequence.append(truth.label)
            events = append_token(events, "SEGMENT:" + truth.label)
        for m in sc.markers:
            if _in_tick(m.t_ms, prev, t, first):
                events = append_token(events, "MARK:" + m.text)
        for w in sc.faults:
            name = FI.target_name(w.target) + "." + FI.kind_name(w.kind)
            if _in_tick(w.start_ms, prev, t, first):
                events = append_token(events, "FAULT_ON:" + name)
            if not first and _in_tick(w.end_ms, prev, t, False):
                events = append_token(events, "FAULT_OFF:" + name)
        while next_reset < len(sc.resets_at_ms) and _in_tick(sc.resets_at_ms[next_reset], prev, t, first):
            clock.simulate_reset(sc.reboot_ms)
            if hook:
                hook.on_reset()
            summ.resets += 1
            events = append_token(events, "RESET:boot=%d" % clock.boot_count())
            next_reset += 1
        if was_booting and not clock.booting():
            events = append_token(events, "BOOT_COMPLETE:boot=%d" % clock.boot_count())
            events = append_token(events, begin_all())
        was_booting = clock.booting()

        row = "%d,%d,%d,%s,%.2f,%.2f,%d," % (t, clock.boot_count(), clock.now_ms(), truth.label,
                                             truth.alt_m, truth.vz_mps, _b(truth.mounted))
        faults_now = _active_fault_list(faults, t)
        if clock.booting():
            summ.booting_rows += 1
            row += "," * 23  # no readings while rebooting (23 empty fields)
            events = append_token(events, "BOOTING")
            extra = hook.empty_columns() if hook else ""
        else:
            summ.sample_rows += 1
            b, m, p, s = baro.read(), imu.read(), power.read(), switches.read()
            summ.baro_invalid += not b.valid
            summ.imu_invalid += not m.valid
            summ.imu_saturated += m.valid and m.saturated
            summ.power_invalid += not p.valid
            summ.switch_invalid += not s.valid
            row += ("%d,%.1f,%.2f,%d,%d,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%d,%.3f,%.1f,%d,%d,%d,"
                    "%d,%d,%d,%d,%d,%d," % (
                        _b(b.valid), b.pressure_pa, b.temp_c, _b(m.valid), _b(m.saturated),
                        m.ax_g, m.ay_g, m.az_g, m.gx_dps, m.gy_dps, m.gz_dps, _b(p.valid), p.bus_v,
                        p.current_ma, _b(s.valid), _b(s.raw[0]), _b(s.raw[1]),
                        _b(b.comm_ok), _b(b.data_ready), _b(m.comm_ok), _b(m.data_ready),
                        _b(p.comm_ok), _b(p.data_ready)))
            extra = ""
            if hook:
                frame = T.SensorFrame()
                frame.baro, frame.imu, frame.power, frame.switches = b, m, p, s
                extra = hook.on_tick(frame, clock.now_ms())
        row += faults_now + "," + events + extra
        write(row)
        if events and events != "BOOTING":
            summ.timeline.append("t=%7d ms  boot=%d  " % (t, clock.boot_count()) + events)
        prev = t
        t += tick
    summ.final_boot = clock.boot_count()
    out.flush()
    return summ


def format_summary(s):
    r = "# ===== SIMULATED run summary (not hardware validation; SYNTHETIC data) =====\n"
    r += "# scenario: " + s.scenario + "\n"
    r += ("# ticks=%d sample_rows=%d booting_rows=%d resets=%d final_boot=%d log_write_failures=%d\n"
          % (s.ticks, s.sample_rows, s.booting_rows, s.resets, s.final_boot, s.log_write_failures))
    r += ("# invalid samples: baro=%d imu=%d power=%d switches=%d | imu saturated=%d\n"
          % (s.baro_invalid, s.imu_invalid, s.power_invalid, s.switch_invalid, s.imu_saturated))
    r += "# segments:"
    for seg in s.segment_sequence:
        r += " " + seg
    r += "\n# event timeline:\n"
    for line in s.timeline:
        r += "#   " + line + "\n"
    return r
