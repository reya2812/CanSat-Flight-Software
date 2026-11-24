# cs_flight.py - flight-node loop body (portable; the board main loop and the
# laptop tests both call FlightNode.step()).
#
# Order per step: sensors (if due) -> state source tick (flight software, if
# running) -> link (poll ACKs, send telemetry if due). Each stage is isolated:
# an exception in one is counted and never prevents the others. In particular
# a radio/telemetry failure can never stop the state source from ticking.
import cs_proto as P
from cs_telemetry import build_telemetry
from cs_util import Uptime


class BringupState:
    """State source when the flight software is not running: state NO_FSW, fault 0."""
    running = False
    refused = False
    reasons = ()

    def tick(self, suite, now, uptime_ms):
        pass

    def state(self):
        return P.STATE_NO_FSW

    def fault(self):
        return 0


class RefusedState(BringupState):
    """The flight software was requested but refused to start (boot checks)."""
    refused = True

    def __init__(self, reasons):
        self.reasons = tuple(reasons)


class FlightNode:
    def __init__(self, suite, link, state_src, now, sd_status=P.ST_DISABLED, max_age_ms=None):
        self.suite = suite
        self.link = link
        self.state_src = state_src
        self.sd_status = sd_status
        self.uptime = Uptime(now)
        self.max_age_ms = max_age_ms if max_age_ms is not None else 4 * suite.cfg.SENSOR_PERIOD_MS
        self.sensor_exceptions = 0
        self.state_exceptions = 0
        self.link_exceptions = 0
        self.state_ticks = 0
        self.last_error = ""

    def step(self, now):
        up = self.uptime.update(now)
        sampled = False
        try:
            if self.suite.due(now):
                self.suite.sample(now, up)
                sampled = True
        except Exception as e:
            self.sensor_exceptions += 1
            self.last_error = "sensors: %r" % (e,)
        if sampled:
            try:
                self.state_src.tick(self.suite, now, up)
                self.state_ticks += 1
            except Exception as e:
                self.state_exceptions += 1
                self.last_error = "state: %r" % (e,)
        try:
            self.link.poll(now)
            if self.link.due(now):
                flags = 0
                if self.state_src.running:
                    flags |= P.F_FSW_RUNNING
                if self.state_src.refused:
                    flags |= P.F_FSW_REFUSED
                t = build_telemetry(self.suite, up, self.state_src.state(), self.state_src.fault(), flags,
                                    self.sd_status, self.max_age_ms)
                self.link.send_telemetry(now, t)
        except Exception as e:
            self.link_exceptions += 1
            self.last_error = "link: %r" % (e,)
        return up
