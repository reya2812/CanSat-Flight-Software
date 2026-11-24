# Native (laptop) build, tests and simulation — zero-install: system C++ compiler only.
# PlatformIO (native + esp32dev envs) will be added once installation is approved.
#
#   make test          all unit tests (steps 1-3, interlock, recovery faults)
#   make check-guards  compile-time guard checks (unsafe configs must not compile)
#   make all-checks    both
#   make sim           run every SYNTHETIC scenario -> build/sim/*.csv  [SIMULATED]
#   make sim-one SCEN=nominal
#   make matrix        every scenario x every OD-060 policy with the state machine  [SIMULATED]

CXX ?= c++
CXXFLAGS := -std=c++17 -Wall -Wextra -Wpedantic -Werror \
            -Iinclude -Iinclude/config -Ilib/core -Ilib/hal -Ilib/hal_mock -Isim -Itest
BUILD := build

HEADERS := $(wildcard include/config/*.h lib/core/*.h lib/hal/*.h lib/hal_mock/*.h sim/*.h sim/scenarios/*.h test/*.h)
CORE_SRCS := lib/core/SensorValidator.cpp lib/core/EventDetector.cpp lib/core/RecoveryManager.cpp \
             lib/core/FlightStateManager.cpp lib/core/FlightSoftware.cpp \
             lib/core/DeploymentInterlock.cpp lib/core/ActuatorManager.cpp
SIM_SRCS := sim/FlightProfile.cpp sim/SimRunner.cpp sim/FswHook.cpp sim/scenarios/SyntheticScenarios.cpp \
            sim/scenarios/SyntheticFlightParams.cpp $(CORE_SRCS)

.PHONY: test check-guards all-checks sim sim-one matrix traces clean

$(BUILD)/test_step1: test/test_step1_config_types.cpp $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_step1_config_types.cpp -o $@

$(BUILD)/test_step2: test/test_step2_sim.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_step2_sim.cpp $(SIM_SRCS) -o $@

$(BUILD)/test_step3: test/test_step3_fsm.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_step3_fsm.cpp $(SIM_SRCS) -o $@

$(BUILD)/test_step3_review: test/test_step3_review.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_step3_review.cpp $(SIM_SRCS) -o $@

$(BUILD)/test_interlock: test/test_interlock.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_interlock.cpp $(SIM_SRCS) -o $@

$(BUILD)/test_recovery_faults: test/test_recovery_faults.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) test/test_recovery_faults.cpp $(SIM_SRCS) -o $@

$(BUILD)/sim_runner: sim/sim_main.cpp sim/TraceExporter.cpp $(SIM_SRCS) $(HEADERS)
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) sim/sim_main.cpp sim/TraceExporter.cpp $(SIM_SRCS) -o $@

test: $(BUILD)/test_step1 $(BUILD)/test_step2 $(BUILD)/test_step3 $(BUILD)/test_step3_review \
      $(BUILD)/test_interlock $(BUILD)/test_recovery_faults
	./$(BUILD)/test_step1
	./$(BUILD)/test_step2
	./$(BUILD)/test_step3
	./$(BUILD)/test_step3_review
	./$(BUILD)/test_interlock
	./$(BUILD)/test_recovery_faults

check-guards:
	CXX="$(CXX)" sh test/guards/run_guard_checks.sh

all-checks: test check-guards

sim: $(BUILD)/sim_runner
	./$(BUILD)/sim_runner run-all

sim-one: $(BUILD)/sim_runner
	./$(BUILD)/sim_runner run $(SCEN)

matrix: $(BUILD)/sim_runner
	./$(BUILD)/sim_runner matrix

# Parity traces for the MicroPython port (D-017) -> build/trace/  [SIMULATED]
traces: $(BUILD)/sim_runner
	./$(BUILD)/sim_runner trace-all

clean:
	rm -rf $(BUILD)
