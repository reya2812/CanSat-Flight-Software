# event_detector.py - turns validated sensor frames into flight events.
# (port of lib/core/EventDetector.h/.cpp; behaviour, comments and OD references there)
#
# The ONLY flight module that looks at sensor values. Every threshold/time
# comes from FlightParams (no defaults). If the params are incomplete the
# detector emits nothing except SelfCheckFail.
#
# Stuck-switch policy (OD-060, undecided - no default):
#   P-A StrictSwitchVeto: never confirm; emit ReleaseSensorsOnly (degraded).
#   P-B SensorOverride:   confirm only if neither IMU nor baro had a rejected
#                         sample within the last confirm_window_ms.
#   P-C Vote2of3:         confirm (free fall + baro = 2 of 3 indicators).
#   P-G DelayedFallback:  emit ReleaseSensorsOnly; confirm after fallback_delay_ms.
#
# Unsigned C++ time arithmetic is reproduced with u32_sub(); float arithmetic
# with f32() (see fmath.py for the one known difference: fused multiply-add).
from cansat.core import fmath
from cansat.core import types as T
from cansat.core.num import f32, u32_sub
from cansat.config import flight_params as FP

ONE_G = 1.0  # accelerometer reading at rest (physics, not a threshold)
BARO_HISTORY = 128  # [ASSUMPTION] sizing; must cover baro_window_ms (as C++)


def _v(param):
    return param.require()  # only called after params.is_complete()


class EventDetector:
    def __init__(self, params, out):
        self._out = out
        self._complete = params.is_complete()
        self._params_fail_emitted = False
        self._faults = 0
        if self._complete:
            r, t = params.release, params.transitions
            self._t_db = _v(r.switch_debounce_ms)
            self._open_high = [_v(r.switch1_open_is_high), _v(r.switch2_open_is_high)]
            self._vote = _v(r.switch_vote)
            self._a_ff = _v(r.freefall_accel_max_g)
            self._t_ff = _v(r.freefall_min_ms)
            self._dh_min = _v(r.baro_min_drop_m)
            self._w_b = _v(r.baro_window_ms)
            self._t_confirm = _v(r.confirm_window_ms)
            self._policy = _v(params.interlock.stuck_switch_policy)
            ok, fb = params.interlock.fallback_delay_ms.get()
            self._fallback = fb if ok else 0
            self._sc_samples = _v(t.selfcheck_samples)
            self._sc_need_power = _v(t.selfcheck_require_power)
            self._asc_gain = _v(t.ascent_min_gain_m)
            self._asc_ms = _v(t.ascent_confirm_ms)
            self._chute_g = _v(t.chute_open_accel_min_g)
            self._land_ms = _v(t.landed_window_ms)
            self._land_dalt = _v(t.landed_max_alt_change_m)
            self._land_tol = _v(t.landed_accel_tol_g)
            self._land_agl = _v(t.landed_max_alt_above_ground_m)
            self._desc_ms = _v(t.descent_confirm_ms)
        # ground reference
        self._has_ground = False
        self._ground_pa = 0.0
        self._has_local_ref = False
        self._local_ref_pa = 0.0
        # switches
        self._sw_known = [False, False]
        self._sw_stable = [False, False]
        self._sw_cand = [False, False]
        self._sw_cand_set = [False, False]
        self._sw_cand_since = [0, 0]
        self._mount_known = False
        self._mount_open = False
        # free fall
        self._below = False
        self._below_since = 0
        self._freefall = False
        self._imu_ever_rejected = False
        self._last_imu_reject = 0
        # baro
        self._hist_t = [0] * BARO_HISTORY
        self._hist_alt = [0.0] * BARO_HISTORY
        self._hist_n = 0
        self._hist_head = 0
        self._baro_desc = False
        self._alt_valid = False
        self._alt_now = 0.0
        self._baro_ever_rejected = False
        self._last_baro_reject = 0
        # self-check
        self._sc_count = 0
        self._sc_sum_pa = 0.0  # C++ double; Python float is a double on CPython
        self._sc_done = False
        # ascent
        self._asc_above = False
        self._asc_since = 0
        self._asc_done = False
        # release
        self._cand_active = False
        self._cand_emitted = False
        self._cand_t = 0
        self._uncorroborated_emitted = False
        self._sensors_only_emitted = False
        self._so_active = False
        self._so_since = 0
        self._confirmed = False
        # chute
        self._chute_done = False
        # descent confirmation
        self._desc_active = False
        self._desc_since = 0
        self._desc_done = False
        # landing
        self._unconfirmable_emitted = False
        self._stable = False
        self._stable_since = 0
        self._stable_ref_alt = 0.0
        self._touchdown_done = False

    # ---- accessors (diagnostics, recovery) ----
    def restore_ground_reference(self, pressure_pa):
        self._has_ground = True
        self._ground_pa = f32(pressure_pa)
        self._sc_done = True  # ground reference already captured in an earlier boot

    def has_ground_reference(self):
        return self._has_ground

    def ground_pressure_pa(self):
        return self._ground_pa

    def mount_open(self):
        return self._mount_open

    def freefall(self):
        return self._freefall

    def baro_descent(self):
        return self._baro_desc

    def release_latched(self):
        return self._confirmed

    def params_complete(self):
        return self._complete

    def fault_mask(self):
        return self._faults

    # ---- main entry ----
    def _emit(self, t, now, detail=0):
        self._out.on_event(T.Event(t, now, detail))

    def update(self, v, state, chute_requested):
        if not self._complete:
            if not self._params_fail_emitted:
                self._emit(T.EV_SELF_CHECK_FAIL, v.now_ms, T.FAULT_PARAMS_INCOMPLETE)
                self._params_fail_emitted = True
            return
        self._update_switches(v)
        self._update_freefall(v)
        self._update_baro(v)
        if state == T.STATE_POWER_ON_SELF_CHECK:
            self._self_check(v)
        elif state == T.STATE_READY_ON_DRONE:
            self._ascent(v)
        elif state == T.STATE_ASCENT or state == T.STATE_RELEASE_DETECTED:
            self._release(v)
        elif state == T.STATE_PARACHUTE_DEPLOY:
            self._chute(v, chute_requested)
            self._landing(v)  # an unsensed opening must still allow touchdown to be reported
        elif state == T.STATE_PANEL_DEPLOY:
            self._descent(v)
            self._landing(v)
        elif state == T.STATE_DESCENT:
            self._landing(v)

    def _update_switches(self, v):
        if v.switches_ok:
            for k in range(T.SWITCH_COUNT):
                level = v.raw.switches.raw[k]
                if not self._sw_cand_set[k] or level != self._sw_cand[k]:
                    self._sw_cand[k] = level
                    self._sw_cand_set[k] = True
                    self._sw_cand_since[k] = v.now_ms
                if u32_sub(v.now_ms, self._sw_cand_since[k]) >= self._t_db:
                    self._sw_stable[k] = self._sw_cand[k]
                    self._sw_known[k] = True
        open1 = self._sw_known[0] and self._sw_stable[0] == self._open_high[0]
        open2 = self._sw_known[1] and self._sw_stable[1] == self._open_high[1]
        vote = self._vote
        if vote == FP.SWITCH_VOTE_ANY:
            self._mount_known = self._sw_known[0] and self._sw_known[1]
            self._mount_open = open1 or open2
        elif vote == FP.SWITCH_VOTE_ALL:
            self._mount_known = self._sw_known[0] and self._sw_known[1]
            self._mount_open = open1 and open2
        elif vote == FP.SWITCH_VOTE_SW1_ONLY:
            self._mount_known = self._sw_known[0]
            self._mount_open = open1
        else:
            self._mount_known = False
            self._mount_open = False
        if not self._mount_known:
            self._mount_open = False

    def _mag(self, m):
        return fmath.ACCEL_MAG(m.ax_g, m.ay_g, m.az_g)

    def _update_freefall(self, v):
        if not v.imu_ok:
            self._below = False
            self._freefall = False
            self._imu_ever_rejected = True
            self._last_imu_reject = v.now_ms
            return
        if self._mag(v.raw.imu) < self._a_ff:
            if not self._below:
                self._below = True
                self._below_since = v.now_ms
            self._freefall = u32_sub(v.now_ms, self._below_since) >= self._t_ff
        else:
            self._below = False
            self._freefall = False

    def _update_baro(self, v):
        self._baro_desc = False
        self._alt_valid = False
        if not v.baro_ok:
            self._baro_ever_rejected = True
            self._last_baro_reject = v.now_ms
            return
        p = v.raw.baro.pressure_pa
        if self._has_ground:
            ref = self._ground_pa
        else:
            if not self._has_local_ref:
                self._has_local_ref = True
                self._local_ref_pa = p  # provisional reference: only altitude differences use it
            ref = self._local_ref_pa
        self._alt_now = fmath.altitude_above_reference(p, ref)
        self._alt_valid = True

        self._hist_t[self._hist_head] = v.now_ms
        self._hist_alt[self._hist_head] = self._alt_now
        self._hist_head = (self._hist_head + 1) % BARO_HISTORY
        if self._hist_n < BARO_HISTORY:
            self._hist_n += 1

        found = False
        alt_then = 0.0
        for i in range(self._hist_n):
            idx = (self._hist_head - 1 - i + BARO_HISTORY) % BARO_HISTORY
            if u32_sub(v.now_ms, self._hist_t[idx]) >= self._w_b:
                alt_then = self._hist_alt[idx]
                found = True
                break
        self._baro_desc = found and f32(alt_then - self._alt_now) >= self._dh_min

    def _self_check(self, v):
        if self._sc_done:
            return
        good = (v.baro_ok and v.imu_ok and v.switches_ok and self._mount_known and not self._mount_open and
                (not self._sc_need_power or v.power_ok))
        if not good:
            self._sc_count = 0
            self._sc_sum_pa = 0.0
            return
        self._sc_count += 1
        self._sc_sum_pa += v.raw.baro.pressure_pa
        if self._sc_count >= self._sc_samples:
            self._ground_pa = f32(self._sc_sum_pa / self._sc_count)
            self._has_ground = True
            self._sc_done = True
            self._emit(T.EV_SELF_CHECK_PASS, v.now_ms)

    def _ascent(self, v):
        if self._asc_done or not self._has_ground:
            return
        if self._alt_valid and self._alt_now >= self._asc_gain:
            if not self._asc_above:
                self._asc_above = True
                self._asc_since = v.now_ms
            if u32_sub(v.now_ms, self._asc_since) >= self._asc_ms:
                self._asc_done = True
                self._emit(T.EV_ASCENT_DETECTED, v.now_ms)
        else:
            self._asc_above = False

    def _release(self, v):
        if self._confirmed:
            return
        now = v.now_ms
        if self._mount_open and not self._cand_active and not self._cand_emitted:
            self._cand_active = True
            self._cand_emitted = True
            self._cand_t = now
            self._emit(T.EV_RELEASE_CANDIDATE, now)
        if self._cand_active and not self._mount_open:
            self._cand_active = False
            self._cand_emitted = False  # a later re-opening is a new candidate
            self._emit(T.EV_SWITCH_REVERTED, now)

        if self._mount_open:
            self._so_active = False
            if self._freefall or self._baro_desc:
                if self._freefall and self._baro_desc:
                    basis = T.BASIS_SWITCH_FREEFALL_BARO
                elif self._freefall:
                    basis = T.BASIS_SWITCH_AND_FREEFALL
                else:
                    basis = T.BASIS_SWITCH_AND_BARO
                self._confirmed = True
                self._emit(T.EV_RELEASE_CONFIRMED, now, basis)
                return
            if (self._cand_active and not self._uncorroborated_emitted and
                    u32_sub(now, self._cand_t) > self._t_confirm):
                self._uncorroborated_emitted = True
                self._emit(T.EV_RELEASE_UNCORROBORATED, now)
            return

        # Switch still reads "mounted" (or unknown): sensors-only evidence path (OD-060).
        if not (self._freefall and self._baro_desc):
            self._so_active = False
            return
        if not self._so_active:
            self._so_active = True
            self._so_since = now
        pol = self._policy
        if pol == FP.POLICY_SENSOR_OVERRIDE:
            imu_clean = not self._imu_ever_rejected or u32_sub(now, self._last_imu_reject) >= self._t_confirm
            baro_clean = not self._baro_ever_rejected or u32_sub(now, self._last_baro_reject) >= self._t_confirm
            accept = imu_clean and baro_clean
        elif pol == FP.POLICY_VOTE_2_OF_3:
            accept = True
        elif pol == FP.POLICY_DELAYED_FALLBACK:
            accept = u32_sub(now, self._so_since) >= self._fallback
        else:  # StrictSwitchVeto, Unset
            accept = False
        if not accept and not self._sensors_only_emitted:
            self._sensors_only_emitted = True
            self._emit(T.EV_RELEASE_SENSORS_ONLY, now, pol)
        if accept:
            self._confirmed = True
            self._emit(T.EV_RELEASE_CONFIRMED, now, T.BASIS_SENSORS_ONLY_POLICY)

    def _chute(self, v, chute_requested):
        if self._chute_done or not chute_requested or not v.imu_ok:
            return
        if v.raw.imu.saturated or self._mag(v.raw.imu) >= self._chute_g:
            self._chute_done = True
            self._emit(T.EV_CHUTE_OPEN_DETECTED, v.now_ms, 0)  # sensed opening only

    def _descent(self, v):
        if self._desc_done:
            return
        if not self._baro_desc:
            self._desc_active = False
            return
        if not self._desc_active:
            self._desc_active = True
            self._desc_since = v.now_ms
        if u32_sub(v.now_ms, self._desc_since) >= self._desc_ms:
            self._desc_done = True
            self._emit(T.EV_DESCENT_CONFIRMED, v.now_ms)

    def _landing(self, v):
        # TOUCHDOWN requires ALL of (OD-065): a ground reference from self-check,
        # altitude near it, altitude stable and |a| ~ 1 g for landed_window_ms, valid
        # baro and IMU throughout. Time alone never establishes touchdown.
        if self._touchdown_done:
            return
        if not self._has_ground:
            self._faults |= T.FAULT_LANDING_UNCONFIRMABLE
            if not self._unconfirmable_emitted:
                self._unconfirmable_emitted = True
                self._emit(T.EV_SENSOR_FAULT, v.now_ms, T.FAULT_LANDING_UNCONFIRMABLE)
            return
        if (not self._alt_valid or not v.imu_ok or
                abs(f32(self._mag(v.raw.imu) - ONE_G)) > self._land_tol or
                abs(self._alt_now) > self._land_agl):
            self._stable = False
            return
        if not self._stable or abs(f32(self._alt_now - self._stable_ref_alt)) > self._land_dalt:
            self._stable = True
            self._stable_since = v.now_ms
            self._stable_ref_alt = self._alt_now
        if u32_sub(v.now_ms, self._stable_since) >= self._land_ms:
            self._touchdown_done = True
            closed = self._mount_known and not self._mount_open
            if closed:
                self._faults |= T.FAULT_LANDED_MOUNT_CLOSED
            self._emit(T.EV_TOUCHDOWN_DETECTED, v.now_ms, T.TOUCHDOWN_MOUNT_READS_CLOSED if closed else 0)
