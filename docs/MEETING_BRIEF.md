# Team Meeting Brief: Flight Software Inputs Needed

**Meeting:** 2026-11-18 (tonight). **From:** onboard/flight software. **Purpose:** to get the decisions that block the minimum viable flight software: sensing, flight-state logic, telemetry, logging and the ground station.
**Label key:** [PDR] · [DOC-CONFIRMED] · [HW-VERIFIED] · [TEAM DECISION] · [UNVERIFIED] · [RECOMMENDATION] · [ASSUMPTION] · [SIMULATED] · [TBD]
**Detail and evidence:** `OPEN_DECISIONS.md` (OD-xxx), `PHASE1_PROPOSAL.md` (§x).
**Rev 2 (2026-11-18):**
- The HC-12 link is marked not established (M1).
- Power is marked not finalised (M5).
- Shock measurement is a separate question (M8).
- The stuck-switch policy is a critical team decision with no recommendation (G3).

**Opening statement for the team** [RECOMMENDATION]:
- Software development starts now, using mocks. Nothing waits on these answers.
- Every answer tonight replaces a mock or a TBD later.
- Software will **not** pick thresholds, timings, pins or servo settings itself.
- No servo will be driven by software until the team signs off a safety review.
- Please say whether each answer is *decided*, *a guess*, or *tested*. Only a test result counts as hardware-verified.

**Role note** [PDR]:
- Slide 3 lists Krish Chhugani as "Project Manager, Electrical Power System". Krish also presented the power budget (slide 18), so bring Krish into the power questions.
- Slide 3 lists Aditya Jaitly for "Structural Design and CAD". Bring Aditya into the mass and volume questions.

Priority key: **P0** blocks the minimum viable software or the safety design · **P1** needed before hardware integration · **P2** later.

---

## 1. Haridas: structure, parachute, solar

### H1 (P0) Which servo does what? Are any servos on the drone instead of the CanSat?
- **Why software cares:** each servo is a separate actuator channel with its own interlock, safe start position and test procedure. A servo on the drone side is not controlled by our flight computer at all.
- **PDR says:**
  - [PDR] Parachute: "Latch using servo, deploy after safe distance from the drone" (slide 10). "Parachute deploys actively after release using a servo" (SR-4, slide 6).
  - [PDR] Drone: "servo-actuated locking pin" on the drone bracket; check "drone servo and PocketQube servo operation" (slide 9).
  - [PDR] The mass budget lists a 9 g servo under parachute **and** a 9 g servo under solar (slide 14).
- **Missing:** [TBD] the mapping for the 3 × SG90 (OD-050, OD-039).
- **Recommended default:** [ASSUMPTION, to be confirmed] servo A = drone pin (drone side), B = parachute latch (CanSat), C = solar latch *only if* there is one. Software builds one generic "actuator channel" and mocks all three.
- **Need:** a table of servo → mechanism → which board drives it → rest/safe position → owner.

### H2 (P0) Does the solar-panel deployment need a software signal, and can software observe it?
- **Why software cares:** this decides whether the PANEL DEPLOY state *commands* something or only *waits or observes*, and what moves the state machine on to DESCENT.
- **PDR says:**
  - [PDR] Spring-assisted, "0 mW", "no code needed" (slide 12). "Spring-Assisted — Passive, No electrical power" (slide 18).
  - [PDR] But the mass budget includes "servo: 9 g" for solar (slide 14).
- **Missing:** [TBD] whether there is a servo, and whether there is a sensor (for example the second limit switch) showing the panels are out (OD-037).
- **Recommended default:** [RECOMMENDATION] passive panels, no command. The state machine records PANEL DEPLOY as an *expected* phase, not a confirmed one, unless a sensor is added.
- **Need:** yes or no on the servo, and yes or no on a "panels deployed" sensor.

### H3 (P0) What is the physical release sequence, and when do the panels unlock?
- **Why software cares:** this sets the order of states and which event leads to which.
- **PDR says (conflicting, OD-038):**
  - [PDR] "solar panels unlock after detaching from the drone" (slide 19 text).
  - [PDR] The diagram and CONOPS place panel deployment *after* the chute opens (slides 8, 13, 19).
- **Missing:** [TBD] the real order, and what physically releases the panel latch.
- **Recommended default:** [ASSUMPTION] separate → parachute → panels, following the slide 19 diagram.
- **Need:** one agreed sequence, as a numbered list of physical steps.

### H4 (P0) Minimum delay after release before the parachute may open ("safe distance from the drone")
- **Why software cares:** this becomes the T_SEP_MIN interlock parameter (`PHASE1_PROPOSAL.md` §3.2). Software will not guess it.
- **PDR says:** [PDR] "deploy after safe distance from the drone" (slide 10). No number is given.
- **Missing:** [TBD] the value and its basis.
- **Recommended default:** none. The firmware has no default. Test scenarios use a labelled SYNTHETIC value.
- **Need:** a decision on *how* it will be set (for example from tethered-release or dummy-drop video), and who owns it.

### H5 (P1) Which descent time and mass are the design basis?
- **Why software cares:** they set scenario timing, the landing-detection window and the logging duration.
- **PDR says (conflicting, OD-031, OD-036):**
  - [PDR] "~20 s" (slides 8, 10).
  - [PDR] "28.8 s" (slide 10 table), "~30 s" (SR-5), "T = 28 s" (slide 18).
  - [PDR] Mass 500 g (slide 10) vs 428 g (slide 14).
  - [ASSUMPTION] 100 m ÷ 3 m/s = 33 s.
- **Need:** one descent-time figure and the expected flight mass with the new batteries.

### H6 (P1) Mass and volume with the new parts (with Aditya)
- **Why software cares:** indirect. A heavier CanSat descends faster, and the battery and board layout limits where connectors and the SD card can go.
- **PDR says:** [PDR] 428 g, "72g below 500g" (slide 14).
- **Finding:**
  - [ASSUMPTION] The 18650 change alone adds about +58 g, which is about 80 % of the margin.
  - [ASSUMPTION] The 428 g total seems to count solar as 41 g, not 41 × 2 (OD-035).
- **Need:** weighed parts and a CAD fit check (OD-018).

---

## 2. Mukund: sensors, telemetry, power (bring Krish in for power)

### M1 (P0) HC-12 settings: mode, UART baud, channel, TX power, SET-pin use
- **Why software cares:** the UART baud sets the largest packet we can send at 4 Hz (`PHASE1_PROPOSAL.md` §2.1). The software UART setup must match the module exactly.
- **PDR says:** [PDR] ESP-NOW (slides 16–17), superseded by the [TEAM DECISION] to use HC-12 (OD-010). Targets: ≥150 m range, ≤1.0 s link gap, 4 Hz.
- **Findings** (theoretical, [ASSUMPTION] from the HC-12 manual as recalled):
  - At 9600 baud (FU3, about 15 kbps air) the proposed ~72–123 B packet fits at 4 Hz with about 2× margin.
  - At 1200 or 2400 baud it does **not** fit.
  - The longest-range settings are the ones that cannot carry 4 Hz.
- **Important:** these numbers only check the UART wire. **The radio link is NOT established as feasible** (OD-061). Air-side overhead, latency, packet loss, interference, range, antenna placement and supply noise are all untested.
- **Recommended default:** [RECOMMENDATION] FU3 at 9600 (the factory default) **for bench work only**. Fix the ground-station and CanSat baud to match.
- **Need:**
  - the chosen settings;
  - an owner for the RF test plan (RF-01 … RF-07 in `PHASE1_PROPOSAL.md` §2.1);
  - the team's real acceptance criterion: [PDR] slide 20 says "100% packet reception", which may be unrealistic over RF;
  - whether other teams use HC-12 on the same channel.

### M2 (P0) Exact sensor boards and I2C addresses
- **Why software cares:** the drivers and the self-check must know what to expect. A wrong address shows up as "sensor missing".
- **PDR says:** [PDR] GY-91, BME280 and INA219 (slide 15), superseded by BMP280 + MPU6050 + INA219 [UNVERIFIED].
- **Missing:** [TBD] BMP280 at 0x76 or 0x77 (OD-056). An I2C scan result from the actual boards.
- **Recommended default:** [RECOMMENDATION] the self-check accepts the BMP280 at either address and reports which one it found.
- **Need:** an I2C scan printout. That is a 5-minute bench task.

### M3 (P0) Sampling rate vs telemetry rate, and the 4 Hz vs 1 Hz conflict
- **Why software cares:** release detection needs faster sampling than 4 Hz (`PHASE1_PROPOSAL.md` §2.2, §3.2). Telemetry can stay at 4 Hz.
- **PDR says (OD-030, OD-042):**
  - [PDR] Sampling of every sensor at 4 Hz and telemetry at 4 Hz (slide 19).
  - [PDR] The power table says "ESP-NOW at 1 Hz" next to "4Hz for entire duration" (slide 18).
- **Recommended default:** [RECOMMENDATION] telemetry at 4 Hz. Internal sampling faster, with the exact rate set after bench timing. Log to SD at the sampling rate.
- **Need:** confirm 4 Hz telemetry, and agree that "4 Hz sampling" in the PDR may be raised.

### M4 (P0) What does the single INA219 measure, and what happens to H%, SPC and SPV?
- **Why software cares:** this decides which telemetry fields exist (`PHASE1_PROPOSAL.md` §5).
- **PDR says:** [PDR] The packet includes H%, SPC, SPV and VBAT (slide 17). There is one INA219 (slide 18). The BME280 provided humidity (slide 15).
- **Missing:** [TBD]
  - The BMP280 has no humidity sensor, so H% cannot be measured (OD-013).
  - One INA219 measures one rail, so it cannot give both solar and battery readings (OD-014).
- **Recommended default:** [RECOMMENDATION] the INA219 measures the main battery or system rail. Drop H% from v1. SPC and SPV stay TBD until the solar electrical role is decided.
- **Need:** a decision for each field: keep, drop, or add hardware.

### M5 (P0) Power topology for the two cells, chargers, switches and three MT3608s (with Krish)
- **Why software cares:** this decides what battery voltage we monitor, whether a servo move can brown out the ESP32, and what "low battery" means.
- **PDR says:** [PDR] a single 9 V, 800 mAh battery → main switch → regulator (slide 18), superseded by 2 × 18650 1S [UNVERIFIED] (OD-017).
- **Findings** ([ASSUMPTION], `PHASE1_PROPOSAL.md` §2.3–2.4):
  - Three SG90s stalled together on one MT3608 from a 1S cell need about 3.2–4.0 A of input current. That is at or above the MT3608's switch limit and around the protection board's trip level.
  - The TP4056 boards are listed "with Current Protection". If DW01 chips are fitted, they cut off at about 2.4 V, but only for loads wired to OUT±.
- **Status:** **power architecture not finalised** (OD-063). These are risks to test, not decisions. Software will not assume any topology.
- **Ideas to discuss, not decisions** ([RECOMMENDATION]): keep the servos on a different boosted rail from the ESP32, radio and sensors, with a common ground. Software can sequence actuators so that no two move at once.
- **Need:**
  - a drawn power tree: which cell feeds which load, which MT3608 feeds what, where the INA219 sits, and both switches;
  - owners and dates for tests PT-01 … PT-09 (`PHASE1_PROPOSAL.md` §2.4a): board identification, single- and multi-servo rail tests, inrush, combined load with HC-12 TX, protection behaviour, thermal and endurance.

### M8 (P1) Do we need to *measure* the parachute-opening shock? (OD-062)
- **Why software cares:** this is a **separate requirement** from release and free-fall detection. Free-fall detection works near 0–1 g, where the MPU6050 range is plausibly adequate (performance still untested). Measuring a ~30 g opening peak is a different problem.
- **PDR says:** [PDR] 30 g appears only as the design load for the eye-bolt (slide 10). I found no PDR requirement to measure it.
- **Finding:** [ASSUMPTION] The MPU6050 clips at ±16 g per axis, so it cannot measure a peak above 16 g. It would also need sampling at around 1 kHz or more to catch a short shock at all.
- **Options if the peak must be measured:** a high-g accelerometer (for example ADXL375, H3LIS331DL or ADXL377), which is a hardware change; or a ground or drop test with a load cell on the tether, which may measure the attachment load more directly.
- **Need:** yes or no on measuring the shock. If yes: by what method, and who owns it.

### M6 (P1) SD logging hardware
- **Why software cares:** logging is part of the minimum viable software. The SD module's SPI pins and level-shifter behaviour decide whether it works at 3.3 V.
- **PDR says:** [PDR] "onboard flash memory backup logging" (slide 22) and "onboard logging" (slide 19), against the SD module in the baseline [UNVERIFIED] (OD-016).
- **Missing:** [TBD] Has the 16 GB card been bought? It is not on the invoice (OD-040). Is it FAT32-formatted?
- **Recommended default:** [RECOMMENDATION] flight data on SD; state and one-shot flags in ESP32 NVS flash.

### M7 (P1) Invoice mismatches to check (OD-040)
- [DOC-CONFIRMED] The 100 nF capacitors arrived as **0402 SMD**, which are very hard to hand-solder.
- [DOC-CONFIRMED] "JST PH 2.54mm 20-pin" headers were bought, not 2-pin JST-PH 2.0 pairs.
- [DOC-CONFIRMED] **Limit switches, buzzers, the SD card, solar panels and resistors are not on the invoice.** Have they been bought?

---

## 3. Gautam: systems and state machine

### G1 (P0) Definitions of the states and the transitions between them
- **Why software cares:** this is the core of the minimum viable software.
- **PDR says:** [PDR] Slide 19: POWER ON SELF-CHECK →(PASS) READY ON DRONE →(TAKEOFF) ASCENT →(SEPARATION) RELEASE DETECTED →(CONFIRMED) PARACHUTE DEPLOY →(CHUTE OPEN) PANEL DEPLOY →(PANELS OUT) DESCENT →(TOUCHDOWN) LANDED.
- **Missing:** [TBD] how each of these is detected:
  - "TAKEOFF": baro rise, or a GS command?
  - "CHUTE OPEN": accel spike, time, or nothing?
  - "PANELS OUT": no sensor exists.
  - "TOUCHDOWN": stable IMU + baro.
  - Is there a FAULT state? The PDR has none.
- **Recommended default:** [RECOMMENDATION]
  - Use the 8 PDR states exactly.
  - Represent faults as flags plus degraded modes, not as a separate state that could trap the flight.
  - Transitions with no sensor (PANELS OUT) are recorded as "assumed", with the reason shown.
- **Need:** the agreed source signal for each transition. The numeric values can come later.

### G2 (P0) How release detection combines its signals
- **Why software cares:** a false release could fire the parachute on the drone, and a missed release means no parachute.
- **PDR says:**
  - [PDR] "Mount switch opens + GY-91 acceleration change; BME280 descent … backup" (slide 19).
  - [PDR] "barometric altitude drop + IMU acceleration spike" (slide 22).
- **Challenge:** [ASSUMPTION] in free fall the accelerometer reads about **0 g**. That is a drop, not a spike (OD-041).
- **Recommended default:** [RECOMMENDATION] switch open **and** (free fall **or** baro descent) inside a window, as in the parameterised logic in `PHASE1_PROPOSAL.md` §3.2. No numbers are set until test data exists (§3.3).
- **Need:** agreement on the logic structure, and on what the second limit switch is for (OD-015).

### G3 (P0, CRITICAL) Safety interlocks and the stuck-switch case (OD-060; full analysis in `OPEN_DECISIONS.md` §H)
- **Why software cares:** this defines when an actuator request may *ever* be executed.
- **PDR says:** [PDR] "No parachute actuation while still mounted" (slide 19). The PDR does not say how "mounted" is judged when the sensors disagree.
- **The scenario:** the CanSat is released, but a mount switch is stuck closed, while the IMU shows free fall and the barometer shows descent.
  - If software **blocks** and the CanSat really is released: it falls ~100 m with no parachute.
  - If software **requests** and the CanSat is really still mounted: the parachute deploys under the drone and may tangle in the rotors.
  - [ASSUMPTION] "Still mounted but the sensors look like free fall" is realistic. A failed IMU read that returns zeros looks exactly like 0 g. A fast-descending drone also shows baro descent.
- **Candidate approaches** (no recommendation is made):
  - P-A strict switch veto;
  - P-B sensor override with stricter checks;
  - P-C 2-of-3 voting;
  - P-D redundant mount switches (needs a mechanical decision);
  - P-E external or uplink confirmation;
  - P-F mechanical lanyard release;
  - P-G delayed fallback.
- **Constraint for every option:** [ASSUMPTION] ignoring drag, a 100 m fall takes only about 4.5 s. Every confirmation window and delay eats into that time.
- **Software meanwhile:** the firmware has **no default policy**. Simulation runs every option side by side. A hardware build will not compile until the team records an approved choice. Physical actuation stays disabled at compile time (OD-059).
- **Need:**
  - a team decision (or a plan to gather the evidence listed in §H.4);
  - who signs off the safety approval;
  - an owner for the arming procedure.

### G4 (P0) Reset recovery policy
- **Why software cares:** [PDR] "restores the last saved state … prevents repeated deployment commands" (slide 19).
- **Missing:** [TBD] what to do if a reset happens *after* the parachute was requested but *before* we know whether it worked. Should the request be retried or not? And what if the record is corrupted?
- **Recommended default:** [RECOMMENDATION] never repeat a recorded one-shot request automatically. Re-check the switch and sensors after a reset. If the record is corrupted, restart in a safe, not-armed state and raise a fault.
- **Need:** a yes or no on retry-after-reset.

---

## 4. Shikhraj: integration and test

### S1 (P0) The drone release interface
- **Why software cares:** we need to know whether the CanSat is *told* about release or must *detect* it.
- **PDR says:** [PDR] a drone bracket with a "servo-actuated locking pin" and "gravity-assisted separation"; "release event and timestamp recorded in telemetry" (slide 9).
- **Missing:** [TBD] (OD-058)
  - Who triggers the pin: the drone pilot's RC channel, or a separate microcontroller?
  - Is the drone servo one of our 3 SG90s?
  - Is there any electrical link between the drone and the CanSat (for example a mount-switch cable)?
- **Recommended default:** [RECOMMENDATION] no electrical link. The CanSat detects release by itself.
- **Need:** a drawing of the release interface showing who presses what.

### S2 (P0) Which planned tests need software, and when?
- **PDR says:** [PDR] Bench test Nov 05, range test Nov 10, solar Nov 15, drop Nov 20, integrated drop Nov 25, fit check Nov 28 (slide 20).
- **Missing:** [TBD] Today is Nov 18 and no test results are in the repo, so the Nov 05–15 tests must be treated as not done (OD-046).
- **Software can provide:**
  - [RECOMMENDATION] a logging-only firmware build (sensors + SD + telemetry, **no actuators**) for the drop and drone tests. Those flights also produce the data needed to set the thresholds (`PHASE1_PROPOSAL.md` §3.3).
  - A ground-station logger for the range test.
- **Need:** an updated test schedule, and which test is the first one that needs flight software.

### S3 (P1) Test evidence format
- [RECOMMENDATION] Use the `docs/08` evidence-log fields (test ID, firmware version, hardware revision, setup, result, reviewer). Only these records can turn an item into [HW-VERIFIED].

---

## 5. One-page decision checklist (print this)

| ✓ | ID | Decision | Owner | Blocks |
|---|---|---|---|---|
| ☐ | H1 | Servo → mechanism → which board drives it → safe position | Haridas, Shikhraj | Actuator channels |
| ☐ | H2 | Solar: servo yes/no? "Panels deployed" sensor yes/no? | Haridas | PANEL DEPLOY state |
| ☐ | H3 | Physical sequence: separate → chute → panels? (PDR conflicts) | Haridas | State order |
| ☐ | H4 | Who owns T_SEP_MIN, and how will it be measured? | Haridas | Parachute interlock |
| ☐ | H5 | Design descent time (20 / 28.8 / 30 s?) and flight mass | Haridas, Aditya | Scenarios, landing logic |
| ☐ | M1 | HC-12 mode, baud, channel, power, SET pin; who runs the range test | Mukund | Telemetry |
| ☐ | M2 | I2C scan: BMP280 0x76/0x77, MPU6050 0x68, INA219 0x40 | Mukund | Drivers, self-check |
| ☐ | M3 | Telemetry 4 Hz confirmed; internal sampling may be faster | Mukund, Gautam | Scheduler |
| ☐ | M4 | INA219 rail; drop H%? SPC/SPV fate? | Mukund | Packet schema |
| ☐ | M1b | Owner and date for RF tests RF-01…07; real packet-loss acceptance criterion (link NOT yet feasible) | Mukund, Shikhraj | Telemetry sign-off |
| ☐ | M5 | Drawn power tree; owners for power tests PT-01…09 (power NOT finalised) | Mukund, Krish | Power monitor, servo safety |
| ☐ | M8 | Measure the opening shock: yes or no? If yes, how (high-g sensor or load-cell test)? | Mukund, Haridas | Possible hardware change |
| ☐ | M6 | SD card bought? FAT32? SPI module level-shifting OK at 3.3 V? | Mukund | Logging |
| ☐ | M7 | Parts not on invoice: switches, buzzers, SD card, solar, resistors | Mukund, Krish | Wiring |
| ☐ | G1 | Source signal for each state transition; faults as flags | Gautam | State machine |
| ☐ | G2 | Release logic structure; role of the 2nd limit switch | Gautam, Haridas | ReleaseDetector |
| ☐ | G3 | **CRITICAL:** stuck-switch policy (options P-A…P-G, OD-060 §H): decide, or agree on the evidence plan; name the safety approver; arming owner | Whole team | Interlock, hardware build |
| ☐ | G4 | Retry after reset: yes or no | Gautam | RecoveryManager |
| ☐ | S1 | Drone release interface: who triggers it, any electrical link | Shikhraj | Release design |
| ☐ | S2 | Updated test dates; first test needing software (logging-only build?) | Shikhraj | Schedule |
| ☐ | — | SR-7 is blank on slide 6: intended or missing? Which list is authoritative (slide 6 vs slide 21)? | Gautam / Krish | Traceability |
| ☐ | — | Re-affirm the deviations: Arduino C++ (not ESP-IDF), HC-12 (not ESP-NOW) | Team | DECISIONS.md |

**Record each answer as:** decided / estimate / tested (plus who and how). Only "tested" can become [HW-VERIFIED].
