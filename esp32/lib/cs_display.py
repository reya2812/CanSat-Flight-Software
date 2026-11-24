# cs_display.py - ground-station serial console rendering (portable, pure text).
import cs_link as L
import cs_proto as P


def _f(v, fmt, missing="--"):
    return missing if v is None else fmt % v


def _st(code):
    return P.ST_NAMES[code] if 0 <= code < len(P.ST_NAMES) else "?%d" % code


def render(link, now, gs_uptime_ms=0):
    """Multi-line status block for the serial console."""
    s = link.stats
    t = link.last
    status = link.status(now)
    since = link.ms_since_rx(now)
    loss = link.loss_percent()
    lines = []
    lines.append("=== CanSat ground station  up %ds ===  LINK %s  last rx %s  loss %s" % (
        gs_uptime_ms // 1000, L.GS_NAMES[status], _f(None if since is None else since / 1000.0, "%.1fs ago"),
        _f(loss, "%.1f%%")))
    lines.append("rx ok=%d lost=%d dup=%d late=%d rejected=%d %s implausible=%d foreign=%d reboots=%d "
                 "acks=%d ack_err=%d rssi=%s" % (
                     s.rx_ok, s.lost, s.duplicates, s.late, s.rejected_total(), _fmt_rejects(s.rejected),
                     s.implausible, s.foreign, s.reboots, s.acks_sent, s.ack_errors, _f(link.last_rssi, "%d dBm")))
    if t is None:
        lines.append("(no valid telemetry received yet)")
        return "\n".join(lines)
    lines.append("pkt %d  boot %04X  flight uptime %.1fs  STATE %s  flight-link %s" % (
        t.seq, t.boot_id, t.uptime_ms / 1000.0, P.state_name(t.state), P.LINK_NAMES[t.link]))
    lines.append("flags: %s   fault: %s" % (" ".join(P.flag_names(t.flags)) or "-",
                                            ("0x%05X" % t.fault) if t.flags & P.F_FSW_RUNNING else "n/a (FSW not running)"))
    lines.append("baro1 [%s]  P %s  T %s  ALT %s" % (
        _st(t.status[0]), _f(t.p1_pa, "%.1f Pa"), _f(t.t1_c, "%.2f C"), _f(t.alt_m, "%.2f m")))
    lines.append("baro2 [%s]  P %s  T %s" % (_st(t.status[1]), _f(t.p2_pa, "%.1f Pa"), _f(t.t2_c, "%.2f C")))
    a = t.accel_g
    g = t.gyro_dps
    lines.append("imu   [%s]  acc g %s  gyro dps %s  T %s" % (
        _st(t.status[2]), "--" if a is None else "%+.3f %+.3f %+.3f" % a,
        "--" if g is None else "%+.1f %+.1f %+.1f" % g, _f(t.imu_temp_c, "%.1f C")))
    lines.append("power [%s]  bus %s  current %s   sd [%s]" % (
        _st(t.status[3]), _f(t.bus_v, "%.3f V"), _f(t.current_ma, "%.1f mA"), _st(t.status[4])))
    lines.append("flight tx: acked_seq=%s tx_fail=%d ack_miss=%d ack_rssi=%s" % (
        "none" if t.acked_seq == P.NO_SEQ else str(t.acked_seq), t.tx_fail, t.ack_miss, _f(t.ack_rssi, "%d dBm")))
    if t.implausible:
        lines.append("WARNING implausible fields dropped: " + ", ".join(t.implausible))
    return "\n".join(lines)


def _fmt_rejects(d):
    if not d:
        return ""
    return "(" + " ".join("%s=%d" % (k, d[k]) for k in sorted(d)) + ")"


CSV_HEADER = ("TLM,seq,boot_id,uptime_ms,state,link,valid,flags,fault,st_b1,st_b2,st_imu,st_pow,st_sd,"
              "p1_pa,t1_c,p2_pa,t2_c,alt_m,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,imu_t_c,bus_v,current_ma,"
              "acked_seq,tx_fail,ack_miss,ack_rssi")


def csv_line(t):
    def c(v):
        return "" if v is None else str(v)
    a = t.accel_g or (None, None, None)
    g = t.gyro_dps or (None, None, None)
    vals = [t.seq, t.boot_id, t.uptime_ms, t.state, t.link, t.valid, t.flags, t.fault] + list(t.status) + [
        t.p1_pa, t.t1_c, t.p2_pa, t.t2_c, t.alt_m, a[0], a[1], a[2], g[0], g[1], g[2], t.imu_temp_c, t.bus_v,
        t.current_ma, t.acked_seq, t.tx_fail, t.ack_miss, t.ack_rssi]
    return "TLM," + ",".join(c(v) for v in vals)
