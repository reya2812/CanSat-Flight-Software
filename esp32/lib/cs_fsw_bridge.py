# cs_fsw_bridge.py - connects the bring-up sensor suite to the EXISTING
# MicroPython flight software (micropython/cansat) without changing it.
#
#   suite readings -> cansat.core.types.SensorFrame -> FlightSoftware.tick()
#   FlightSoftware.state() / fault_mask()           -> telemetry state / fault
#
# Starting the flight software ALWAYS goes through the existing boot checks
# (cansat.boot_checks.run_boot_checks). On hardware they currently REFUSE
# (pins TBD OD-054, flight parameters unapproved OD-057/OD-060), and this
# module has no approved FlightParams source or NVS PersistentStore to offer
# even if they passed, so on the board the result today is RefusedState.
# Nothing here actuates anything: actuator requests are drained and counted only.
from cansat.core import types as T
from cansat.core.flight_software import BootReport, FlightSoftware
from cs_flight import RefusedState


def _copy_baro(dst, r):
    if r is None:
        return
    dst.t_ms, dst.pressure_pa, dst.temp_c = r.t_ms, r.pressure_pa, r.temp_c
    dst.valid, dst.comm_ok, dst.data_ready = r.valid, r.comm_ok, r.data_ready


def _copy_imu(dst, r):
    if r is None:
        return
    dst.t_ms = r.t_ms
    dst.ax_g, dst.ay_g, dst.az_g = r.ax_g, r.ay_g, r.az_g
    dst.gx_dps, dst.gy_dps, dst.gz_dps = r.gx_dps, r.gy_dps, r.gz_dps
    dst.valid, dst.saturated, dst.comm_ok, dst.data_ready = r.valid, r.saturated, r.comm_ok, r.data_ready


def _copy_power(dst, r):
    if r is None:
        return
    dst.t_ms, dst.bus_v, dst.current_ma = r.t_ms, r.bus_v, r.current_ma
    dst.valid, dst.comm_ok, dst.data_ready = r.valid, r.comm_ok, r.data_ready


def to_sensor_frame(suite):
    """Suite readings -> cansat SensorFrame. Absent sensors stay at the
    type defaults (valid=False, comm_ok=False). Limit switches have no driver
    (roles/polarity TBD, OD-051), so switches stay invalid."""
    f = T.SensorFrame()
    _copy_baro(f.baro, suite.baro1.last)
    _copy_imu(f.imu, suite.imu.last)
    _copy_power(f.power, suite.power.last)
    return f


class FswState:
    running = True
    refused = False
    reasons = ()

    def __init__(self, fsw):
        self.fsw = fsw
        self.requests_drained = 0   # logged/counted only; never actuated

    def tick(self, suite, now, uptime_ms):
        self.fsw.tick(to_sensor_frame(suite), uptime_ms)
        while self.fsw.pop_request() is not None:
            self.requests_drained += 1

    def state(self):
        return self.fsw.state()

    def fault(self):
        return self.fsw.fault_mask()


def start_flight_software(suite, uptime_ms, package_root, params=None, store=None, target_hardware=True,
                          boot_checks_fn=None):
    """Return a state source: FswState if every gate passes, else RefusedState(reasons).

    Gates, in order: the existing boot checks (unchanged), then an approved
    parameter set and a persistent store must have been supplied."""
    if boot_checks_fn is None:
        from cansat.boot_checks import run_boot_checks as boot_checks_fn
    try:
        fails = list(boot_checks_fn(package_root, (), target_hardware))
    except Exception as e:
        fails = ["boot checks raised %r" % (e,)]
    if params is None:
        fails.append("no approved FlightParams source exists (OD-057, OD-060)")
    if store is None:
        fails.append("no PersistentStore supplied (NVS store needs cansat/hal_mp, not yet approved)")
    if fails:
        return RefusedState(fails)
    fsw = FlightSoftware(params, store)
    fsw.boot(BootReport(suite.baro1.init_ok, suite.imu.init_ok, suite.power.init_ok), uptime_ms)
    return FswState(fsw)
