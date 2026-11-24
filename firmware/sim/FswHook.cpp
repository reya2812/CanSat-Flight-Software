#include "FswHook.h"

#include <cstdio>

namespace cansat {
namespace sim {

FlightSoftwareHook::FlightSoftwareHook(const FlightParams& params) : params_(params) {}

std::string FlightSoftwareHook::extraHeader() const {
  return ",fsw_state,fsw_chute,fsw_faults,fsw_events,fsw_requests";
}

std::string FlightSoftwareHook::bannerLine() const {
  StuckSwitchPolicy p = StuckSwitchPolicy::Unset;
  params_.interlock.stuck_switch_policy.get(p);
  return std::string("# flight software in the loop (Phase 2 step 3). ACTUATOR LOGIC DISABLED: "
                     "requests are logged as NOT_EXECUTED. SYNTHETIC params; stuck-switch policy=") +
         toString(p);
}

std::string FlightSoftwareHook::onBoot(bool baro_ok, bool imu_ok, bool power_ok, uint32_t uptime_ms) {
  fsw_.reset(new FlightSoftware(params_, store_));
  BootReport r;
  r.baro_ok = baro_ok;
  r.imu_ok = imu_ok;
  r.power_ok = power_ok;
  fsw_->boot(r, uptime_ms);
  const RestoreResult& rr = fsw_->restore();
  if (stats_.states_entered.empty() || !rr.resumed) stats_.states_entered.push_back(fsw_->state());
  pending_ = drainEvents();
  if (rr.corrupt) ++stats_.corrupt_restarts;
  const std::string note = store_note_;
  store_note_.clear();
  return note + std::string("FSW_BOOT:") + (rr.resumed ? "resume=" : "start=") + toString(fsw_->state()) +
         (rr.corrupt ? "/record_corrupt" : "");
}

void FlightSoftwareHook::onReset() {
  fsw_.reset();
  for (const StoreFaultAtReset& f : store_faults_) {
    if (f.reset_index != resets_seen_) continue;
    if (f.kind == StoreFaultKind::CorruptRecord) store_.corrupt();
    if (f.kind == StoreFaultKind::EraseRecord) store_.erase();
    ++stats_.store_faults_applied;
    store_note_ += std::string("STORE_FAULT:") + toString(f.kind) + "/";
  }
  ++resets_seen_;
}

std::string FlightSoftwareHook::drainEvents() {
  std::string out;
  for (int i = 0; i < fsw_->eventCount(); ++i) {
    const Event& e = fsw_->eventAt(i);
    std::string tok;
    char buf[96];
    switch (e.type) {
      case EventType::StateChanged: {
        const FlightState to = static_cast<FlightState>(e.detail & 0xFFu);
        tok = std::string("->") + toString(to);
        stats_.states_entered.push_back(to);
        break;
      }
      case EventType::TransitionRejected:
        std::snprintf(buf, sizeof buf, "TransitionRejected:%s->%s(by %s)",
                      toString(static_cast<FlightState>((e.detail >> 16) & 0xFFu)),
                      toString(static_cast<FlightState>((e.detail >> 8) & 0xFFu)),
                      toString(static_cast<EventType>(e.detail & 0xFFu)));
        tok = buf;
        ++stats_.rejected_transitions;
        break;
      case EventType::RequestSuppressed:
        ++stats_.suppressed_requests;
        tok = "RequestSuppressed:ReleaseParachute(already requested before reset)";
        break;
      case EventType::ResetRecovered:
        ++stats_.resets_recovered;
        tok = std::string("ResetRecovered:") + toString(static_cast<FlightState>(e.detail));
        break;
      case EventType::ReleaseSensorsOnly:
        ++stats_.sensors_only_events;
        tok = "ReleaseSensorsOnly(switch still reads mounted)";
        break;
      case EventType::ReleaseConfirmed:
        ++stats_.release_confirmed;
        stats_.last_release_basis = e.detail;
        std::snprintf(buf, sizeof buf, "ReleaseConfirmed:basis=%u", static_cast<unsigned>(e.detail));
        tok = buf;
        break;
      case EventType::ChuteOpenDetected:
        tok = "ChuteOpenSensed";
        break;
      case EventType::ChuteOpenNotConfirmed:
        ++stats_.chute_not_confirmed_alarms;
        tok = "ChuteOpenNotConfirmed(ALARM: no opening sensed; state unchanged)";
        break;
      case EventType::TouchdownDetected:
        tok = (e.detail & kTouchdownMountReadsClosed) ? "TouchdownDetected(mount reads CLOSED)"
                                                      : "TouchdownDetected";
        break;
      case EventType::SensorFault:
      case EventType::SensorRecovered:
      case EventType::SelfCheckFail:
        std::snprintf(buf, sizeof buf, "%s:0x%X", toString(e.type), static_cast<unsigned>(e.detail));
        tok = buf;
        break;
      default:
        tok = toString(e.type);
        break;
    }
    if (!out.empty()) out += ";";
    out += tok;
  }
  return out;
}

std::string FlightSoftwareHook::onTick(const SensorFrame& frame, uint32_t uptime_ms) {
  if (!fsw_) return emptyColumns();
  fsw_->tick(frame, uptime_ms);
  std::string events = pending_;
  pending_.clear();
  const std::string now_events = drainEvents();
  if (!events.empty() && !now_events.empty()) events += ";";
  events += now_events;

  std::string requests;
  ActuatorRequest req;
  while (fsw_->popRequest(req)) {
    ++stats_.requests;
    if (!requests.empty()) requests += ";";
    requests += std::string("REQUEST:") + toString(req) + "(NOT_EXECUTED)";
  }
  stats_.final_state = fsw_->state();
  stats_.final_faults = fsw_->faultMask();
  stats_.final_chute = fsw_->chuteStatus();

  char buf[96];
  std::snprintf(buf, sizeof buf, ",%s,%s,0x%05X,", toString(fsw_->state()),
                toString(fsw_->chuteStatus()), static_cast<unsigned>(fsw_->faultMask()));
  if (!events.empty() || !requests.empty()) {
    char tl[40];
    std::snprintf(tl, sizeof tl, "uptime=%7u  ", uptime_ms);
    stats_.timeline.push_back(std::string(tl) + events + (requests.empty() ? "" : " | " + requests));
  }
  return std::string(buf) + events + "," + requests;
}

std::string formatFswStats(const FswStats& s) {
  std::string r = "# ----- flight software (SIMULATED; actuator logic disabled) -----\n# states:";
  for (FlightState st : s.states_entered) r += std::string(" ") + toString(st);
  char buf[512];
  std::snprintf(buf, sizeof buf,
                "\n# final=%s chute=%s panels=UNKNOWN(no sensor) faults=0x%05X requests(NOT executed)=%u "
                "suppressed=%u rejected_transitions=%u resets_recovered=%u sensors_only=%u "
                "release_confirmed=%u basis=%u chute_not_confirmed_alarms=%u store_faults=%u "
                "corrupt_restarts=%u\n",
                toString(s.final_state), toString(s.final_chute), static_cast<unsigned>(s.final_faults),
                s.requests, s.suppressed_requests, s.rejected_transitions, s.resets_recovered,
                s.sensors_only_events, s.release_confirmed, s.last_release_basis,
                s.chute_not_confirmed_alarms, s.store_faults_applied, s.corrupt_restarts);
  r += buf;
  r += "# flight-software timeline:\n";
  for (const std::string& l : s.timeline) r += "#   " + l + "\n";
  return r;
}

}  // namespace sim
}  // namespace cansat
