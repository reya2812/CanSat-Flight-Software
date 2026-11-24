# cs_telemetry.py - build a telemetry sample from the sensor suite (portable).
#
# Only readings that are valid AND fresh (age <= max_age_ms) are sent as
# values; everything else is sent as "missing" (validity bit clear) with the
# sensor's status code, so the ground station always sees WHY a value is absent.
# Readings may be the esp32 driver readings or the cansat.core.types samples
# (BaroSample / ImuSample / PowerSample): only shared attribute names are required.
import cs_proto as P


def _fresh(ch, uptime_ms, max_age_ms):
    r = ch.last
    if r is None or not r.valid:
        return None
    age = (uptime_ms - r.t_ms) & 0xFFFFFFFF
    return r if age <= max_age_ms else None


def build_telemetry(suite, uptime_ms, state, fault, flags, sd_status, max_age_ms):
    t = P.Telemetry()
    t.uptime_ms = uptime_ms
    t.state = state
    t.fault = fault
    t.status = [suite.baro1.status, suite.baro2.status, suite.imu.status, suite.power.status, sd_status]
    if suite.baro_dup_suspect:
        flags |= P.F_BARO_DUP_SUSPECT
    if suite.power_gated():
        flags |= P.F_POWER_GATED
    v = 0
    r = _fresh(suite.baro1, uptime_ms, max_age_ms)
    if r is not None:
        t.p1_pa, t.t1_c = r.pressure_pa, r.temp_c
        v |= P.V_BARO1
        if suite.alt_m is not None:
            t.alt_m = suite.alt_m
            v |= P.V_ALT
            if suite.reference_auto:
                flags |= P.F_ALT_REF_AUTO
    r = _fresh(suite.baro2, uptime_ms, max_age_ms)
    if r is not None:
        t.p2_pa, t.t2_c = r.pressure_pa, r.temp_c
        v |= P.V_BARO2
    r = _fresh(suite.imu, uptime_ms, max_age_ms)
    if r is not None:
        t.accel_g = (r.ax_g, r.ay_g, r.az_g)
        t.gyro_dps = (r.gx_dps, r.gy_dps, r.gz_dps)
        v |= P.V_ACCEL | P.V_GYRO
        if getattr(r, "temp_valid", False):   # cansat ImuSample has no temperature
            t.imu_temp_c = r.temp_c
            v |= P.V_IMU_TEMP
        if r.saturated:
            flags |= P.F_IMU_SATURATED
    r = suite.power.last
    if r is not None and r.comm_ok and ((uptime_ms - r.t_ms) & 0xFFFFFFFF) <= max_age_ms:
        # cs_ina219.PowerReading has separate bus/current validity; cansat PowerSample has one `valid`
        if getattr(r, "bus_valid", r.valid):
            t.bus_v = r.bus_v
            v |= P.V_BUS_V
        # the current field is defined together with the shunt voltage; without it, no current is sent
        if getattr(r, "current_valid", r.valid) and getattr(r, "shunt_mv", None) is not None:
            t.shunt_mv, t.current_ma = r.shunt_mv, r.current_ma
            v |= P.V_CURRENT
    t.valid = v
    t.flags = flags
    return t
