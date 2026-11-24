// sim_main.cpp — command-line simulation runner (laptop only). [SIMULATED]
//
//   sim_runner list
//   sim_runner run <scenario> [--out <file.csv>]   sensors only (Step 2)
//   sim_runner run-all [--dir <dir>]               sensors only, every scenario
//   sim_runner run-fsw <scenario> <A|B|C|G>        flight software in the loop (Step 3)
//   sim_runner matrix                              every scenario x every OD-060 policy
//   sim_runner trace <scenario> <A|B|C|G>          parity trace for the MicroPython port (D-017)
//   sim_runner trace-all                           parity traces, every scenario x every policy
//
// Writes CSV logs under build/sim/ and prints summaries to stdout.
// Actuator logic is disabled: requests are only logged as NOT_EXECUTED.
#include <cstdio>
#include <cstring>
#include <string>
#include <sys/stat.h>

#include "FileLogSink.h"
#include "FswHook.h"
#include "SimRunner.h"
#include "TraceExporter.h"
#include "scenarios/SyntheticFlightParams.h"
#include "scenarios/SyntheticScenarios.h"

using namespace cansat;
using namespace cansat::sim;

namespace {

int usage() {
  std::printf(
      "usage: sim_runner list | run <scenario> [--out file] | run-all [--dir dir] |\n"
      "                  run-fsw <scenario> <A|B|C|G> | matrix |\n"
      "                  trace <scenario> <A|B|C|G> | trace-all\n");
  return 2;
}

void mkdirs(const std::string& dir) {
  mkdir("build", 0755);
  mkdir("build/sim", 0755);
  mkdir(dir.c_str(), 0755);
}

bool parsePolicy(const std::string& s, StuckSwitchPolicy& out) {
  if (s == "A") out = StuckSwitchPolicy::StrictSwitchVeto;
  else if (s == "B") out = StuckSwitchPolicy::SensorOverride;
  else if (s == "C") out = StuckSwitchPolicy::Vote2of3;
  else if (s == "G") out = StuckSwitchPolicy::DelayedFallback;
  else return false;
  return true;
}

int runOne(const Scenario& sc, const std::string& path) {
  FileLogSink sink(path.c_str());
  if (!sink.ok()) {
    std::printf("cannot open %s\n", path.c_str());
    return 1;
  }
  SimRunner runner;
  const SimSummary s = runner.run(sc, sink);
  std::printf("%s", formatSummary(s).c_str());
  std::printf("# full CSV log: %s\n\n", path.c_str());
  return s.log_write_failures == 0 ? 0 : 1;
}

int runFsw(const Scenario& sc, StuckSwitchPolicy pol, bool verbose, FswStats* out_stats) {
  const std::string dir = "build/sim/fsw";
  mkdirs(dir);
  const std::string path = dir + "/" + sc.name + "__" + toString(pol) + ".csv";
  FileLogSink sink(path.c_str());
  if (!sink.ok()) {
    std::printf("cannot open %s\n", path.c_str());
    return 1;
  }
  FlightSoftwareHook hook(syntheticFlightParams(pol));
  hook.setStoreFaults(sc.store_faults);
  SimRunner runner;
  const SimSummary s = runner.run(sc, sink, &hook);
  if (verbose) {
    std::printf("%s", formatSummary(s).c_str());
    std::printf("%s", formatFswStats(hook.stats()).c_str());
    std::printf("# full CSV log: %s\n\n", path.c_str());
  }
  if (out_stats) *out_stats = hook.stats();
  return s.log_write_failures == 0 ? 0 : 1;
}

// Parity trace (TraceExporter.h) plus the matching CSV, under build/trace/.
int runTrace(const Scenario& sc, StuckSwitchPolicy pol) {
  mkdir("build", 0755);
  mkdir("build/trace", 0755);
  const std::string base = "build/trace/" + sc.name + "__" + toString(pol);
  FileLogSink trace((base + ".trace").c_str());
  FileLogSink csv((base + ".csv").c_str());
  if (!trace.ok() || !csv.ok()) {
    std::printf("cannot open %s.*\n", base.c_str());
    return 1;
  }
  trace.append(traceHeader(sc.name, toString(pol)).c_str());
  FlightSoftwareHook inner(syntheticFlightParams(pol));
  inner.setStoreFaults(sc.store_faults);
  TraceHook hook(inner, trace, sc.store_faults);
  SimRunner runner;
  const SimSummary s = runner.run(sc, csv, &hook);
  trace.flush();
  std::printf("%s.trace\n", base.c_str());
  return (s.log_write_failures == 0 && hook.writeFailures() == 0) ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) return usage();
  const std::string cmd = argv[1];
  if (cmd == "list") {
    for (const Scenario& sc : everySyntheticScenario()) {
      std::printf("%-30s %s\n", sc.name.c_str(), sc.description.c_str());
    }
    return 0;
  }
  if (cmd == "run" && argc >= 3) {
    Scenario sc;
    if (!findSyntheticScenario(argv[2], sc)) {
      std::printf("unknown scenario: %s (try: sim_runner list)\n", argv[2]);
      return 2;
    }
    std::string out = "build/sim/" + sc.name + ".csv";
    if (argc >= 5 && std::strcmp(argv[3], "--out") == 0) {
      out = argv[4];
    } else {
      mkdirs("build/sim");
    }
    return runOne(sc, out);
  }
  if (cmd == "run-all") {
    std::string dir = "build/sim";
    if (argc >= 4 && std::strcmp(argv[2], "--dir") == 0) dir = argv[3];
    mkdirs(dir);
    int rc = 0;
    for (const Scenario& sc : everySyntheticScenario()) {
      if (runOne(sc, dir + "/" + sc.name + ".csv") != 0) rc = 1;
    }
    return rc;
  }
  if (cmd == "run-fsw" && argc >= 4) {
    Scenario sc;
    StuckSwitchPolicy pol;
    if (!findSyntheticScenario(argv[2], sc) || !parsePolicy(argv[3], pol)) return usage();
    return runFsw(sc, pol, true, nullptr);
  }
  if (cmd == "trace" && argc >= 4) {
    Scenario sc;
    StuckSwitchPolicy pol;
    if (!findSyntheticScenario(argv[2], sc) || !parsePolicy(argv[3], pol)) return usage();
    return runTrace(sc, pol);
  }
  if (cmd == "trace-all") {
    int rc = 0;
    for (const Scenario& sc : everySyntheticScenario()) {
      for (StuckSwitchPolicy pol : candidatePolicies()) {
        if (runTrace(sc, pol) != 0) rc = 1;
      }
    }
    return rc;
  }
  if (cmd == "matrix") {
    std::printf("# SIMULATED - not hardware validation. SYNTHETIC scenarios and parameters.\n");
    std::printf("# Actuator logic disabled: 'requests' are logged only, never executed.\n");
    std::printf("# Scenarios marked HAZARD document current behaviour (OD-069); not approved behaviour.\n");
    std::printf("%-30s %-22s %-18s %-27s %8s %12s %6s\n", "scenario", "policy", "final_state",
                "chute_status", "requests", "sensors_only", "basis");
    int rc = 0;
    for (const Scenario& sc : everySyntheticScenario()) {
      for (StuckSwitchPolicy pol : candidatePolicies()) {
        FswStats st;
        if (runFsw(sc, pol, false, &st) != 0) rc = 1;
        std::printf("%-30s %-22s %-18s %-27s %8u %12u %6u\n", sc.name.c_str(), toString(pol),
                    toString(st.final_state), toString(st.final_chute), st.requests,
                    st.sensors_only_events, st.last_release_basis);
      }
    }
    std::printf("# logs: build/sim/fsw/<scenario>__<policy>.csv\n");
    return rc;
  }
  return usage();
}
