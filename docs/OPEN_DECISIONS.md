# Open Decisions and Conflict Log

**Created:** 2026-11-18 (Phase 1). This is a running log: append to it and do not delete entries. When an item is closed, record who decided it, when, and what evidence was used.

**Label key (exactly one per statement):** [PDR] · [DOC-CONFIRMED] · [HW-VERIFIED] · [TEAM DECISION] · [UNVERIFIED] · [RECOMMENDATION] · [ASSUMPTION] · [SIMULATED] · [TBD]

**Slide numbering:** [DOC-CONFIRMED] The PDF page number matches the slide footer number for every slide (`references/CanSat_PDR.pdf`, 24 pages, checked with `pdftotext` per page). "Slide N" in this file means PDF page N.

**Nothing in this repository is [HW-VERIFIED].** [TBD] No teammate has reported a physical test result to the software lead yet.

---

## A. Terminology conflict in existing project documents (OD-000)

| Where | Wording used | Problem |
|---|---|---|
| `CLAUDE.md` heading | "Confirmed baseline" | [DOC-CONFIRMED] The heading says "confirmed", but the hardware was reported by the team and has not been physically checked. |
| `docs/03_hardware_specification.md` §1–3 | "User-confirmed baseline", "Confirmed system configuration" | [DOC-CONFIRMED] The file itself says (line 199) that it is "not proof that every component has been received, installed or tested". |
| `README.md` | "Current baseline" bullets with no qualifier | [DOC-CONFIRMED] These bullets read as settled facts. |
| `docs/02_system_requirements.md` SW-04 | "User-confirmed radio component baseline" | [DOC-CONFIRMED] Same issue. |

- [RECOMMENDATION] From now on, read "confirmed" in the older documents as [TEAM DECISION] for software or tool choices and [UNVERIFIED] for hardware. Only a reported physical test can earn [HW-VERIFIED].
- [TBD] Whether to edit the older documents. They have **not** been changed. That needs your approval.

## B. Stale or contradictory statements in existing project documents (OD-001)

[DOC-CONFIRMED] These documents contradict each other. None of them was edited.

| Item | Version 1 | Version 2 | Status |
|---|---|---|---|
| MCU family | `DECISIONS.md` D-002: "Target ESP32-S3 board family"; `hardware/pinout.md`: "ESP32-S3 GPIO" column | `DECISIONS.md` D-006/D-009: ESP32 DevKit | [TBD] D-002 looks superseded, but it is not marked that way. `hardware/pinout.md` still says ESP32-S3. |
| Radio | `DECISIONS.md` D-008: "Leave radio technology undecided" | D-010: HC-12 is the working baseline | [TBD] D-008 is not marked as superseded. |
| Sensors in architecture | `docs/04` lists "GY-91", "BME280"; `docs/04` telemetry says "ESP-NOW transmission" | `docs/03`: BMP280 + MPU6050 + INA219, HC-12 | [TBD] `docs/04` is stale. |
| Fault table | `docs/07`: "ESP-NOW send failure" | HC-12 baseline | [TBD] Stale. |
| Servo role | `hardware/pinout.md`: "Servo signal → Parachute latch servo" | `docs/03` §5: "Do not assume one servo per function" | [TBD] The pinout file assumes an assignment that nobody has decided. |
| Folders | `README.md` folder map lists `src/`, `tests/`, `simulator/`, `data/` | [DOC-CONFIRMED] Those folders do not exist on disk. | [TBD] |
| Development environment | `DECISIONS.md` D-003: Arduino C++ "must be reconciled with PDR page 19" | [PDR] Slide 19: "ESP-IDF (C/C++) in VS Code" | See OD-011. |

## C. Repository state (OD-002)

**Inspection on 2026-11-18, read-only.** Commands run: `git rev-parse`, `git status --porcelain`, `git diff --cached --name-only`, `git ls-files`, `git branch`, `git log`, `git remote -v`, `ls`, `stat`, `du`. Nothing was initialised, staged, committed or modified.

| Fact | Evidence |
|---|---|
| The project has **no `.git` of its own**, and none exists in any subfolder | [DOC-CONFIRMED] `ls -la .git` → "No such file"; `find . -name .git` → none |
| The enclosing repository is `/Users/reya/.git`, i.e. your **home directory** | [DOC-CONFIRMED] `git rev-parse --show-toplevel` → `/Users/reya` |
| It has **no commits**, branch `master`, and **no remotes** | [DOC-CONFIRMED] "does not have any commits yet"; `git remote -v` is empty |
| `.git` was created 2026-05-25 and is **5.1 GB** | [DOC-CONFIRMED] `stat`, `du -sh` |
| **909 files are staged**, all under `Desktop/drone_slam_ws/`, with status `AD` (added to the index, then deleted from disk) | [DOC-CONFIRMED] `git status --porcelain`. `Desktop/drone_slam_ws` no longer exists on disk |
| **Nothing from the CanSat project is staged or tracked** | [DOC-CONFIRMED] `git ls-files` and `git diff --cached` contain no CanSat paths. The project shows only as untracked: `?? Desktop/CanSat-Flight-Software/` |
| 133 other home-directory entries are untracked, **including `.ssh/`, `.claude.json`, `.gitconfig` and `.config/`** | [DOC-CONFIRMED] `git status --porcelain` |

**Risks** ([ASSUMPTION]):
1. Running `git add .` or `git commit -a` from anywhere under the home folder could commit unrelated projects, **including SSH keys and app credentials**. That is a serious problem if a remote is ever added.
2. The 5.1 GB of staged objects may be the **only remaining copy** of the deleted `drone_slam_ws` files. Deleting or resetting `/Users/reya/.git` could destroy them. **Do not touch the home repository without deciding about that data first.**
3. Tools (including this agent) currently see `/Users/reya` as the "project root". That makes mistakes more likely.

**Options for giving CanSat its own repository** (none executed):

| Option | What it does | Effect on the home repo | Safety |
|---|---|---|---|
| **R1** `git init` inside `CanSat-Flight-Software/` (nested repo) | Git uses the nearest `.git`, so all git commands inside the project go to the new repo | **None.** The home repo still lists the folder as one untracked entry (a nested repo is never added unless someone explicitly adds it) | [RECOMMENDATION] Safest: nothing outside the project folder is touched, and it is fully reversible (delete the new `.git`) |
| R2 = R1 + add `Desktop/CanSat-Flight-Software/` to `/Users/reya/.git/info/exclude` | Hides the folder from the home repo's status | Edits one local metadata file of the home repo (not tracked content) | Low risk, but it does modify the home repo. Optional |
| R3 Move the project to a folder outside the home repo | — | None | [ASSUMPTION] Not possible on this Mac: everything you own sits under `/Users/reya`, which is inside the home repo |
| R4 Clean up the home repo (unstage, remove, or move `/Users/reya/.git`) | Removes the root cause | **Destructive or hard to reverse.** May lose the `drone_slam_ws` data | Not recommended now. A separate decision for you, after recovering anything needed from the staged objects |

- [RECOMMENDATION] R1 now. Optionally R2. Treat R4 as a separate task, later and outside this project.
- [TBD] **Needs your explicit approval before anything is run.**
- **After R1** ([RECOMMENDATION]): verify with `git rev-parse --show-toplevel` (it should print the project path). Then make a first commit containing only the project files. Check `git status` before committing.

---

## D. PDR-versus-baseline conflicts

| ID | Topic | PDR version | Current team baseline | Status |
|---|---|---|---|---|
| OD-010 | Radio | [PDR] ESP-NOW 2.4 GHz, selected 27/30 (slide 16); "sent via connectionless ESP-NOW" (slide 17); risk mitigation "connectionless ESP-NOW" (slide 22) | [TEAM DECISION] HC-12 433 MHz SI4463 UART, one module at each end (`docs/03` §2) | Deviation from the PDR. [TBD] The PDR range target (≥150 m, slide 16) and link-gap target (≤1.0 s, slide 17) still apply and must be re-verified for the HC-12. |
| OD-011 | Firmware environment | [PDR] "ESP-IDF (C/C++) in VS Code" (slide 19) | [TEAM DECISION] Arduino C++ on ESP32. A teammate's MicroPython suggestion was not adopted. | Deviation from the PDR. [RECOMMENDATION] Record it in `DECISIONS.md` as a deviation (proposed text in `PHASE1_PROPOSAL.md` §8).  **RESOLVED (Rev 6): superseded by D-017, MicroPython.** Earlier text kept for history. |
| OD-012 | IMU | [PDR] GY-91 (MPU9250 + pressure) (slides 6, 15) | [UNVERIFIED] MPU6050 / GY-521, 0x68 | The PDR's IMU had a magnetometer and an onboard barometer. The MPU6050 has neither. [TBD] Ask whether any requirement depends on the magnetometer. None is stated in the PDR. |
| OD-013 | Pressure / temperature / humidity | [PDR] BME280 for temperature and humidity, GY-91 for pressure (slide 15); packet includes `H%` (slide 17); acronyms list "H% Relative Humidity" (slide 4) | [UNVERIFIED] BMP280: pressure + temperature only. [DOC-CONFIRMED] The BMP280 has no humidity sensor (it is the BME280 without humidity, per `docs/03` and the part name). | **The baseline cannot measure `H%`.** [TBD] Choose: (a) drop `H%` from the packet; (b) keep the field and always mark it invalid; (c) add a humidity sensor (hardware change). |
| OD-014 | Solar telemetry vs one INA219 | [PDR] The packet has `SPC` (solar panel current), `SPV` (solar panel voltage) and `VBAT` (slide 17). The block diagram shows one INA219 (slide 18). | [UNVERIFIED] One INA219 (0x40, 0.1 Ω). | One INA219 measures **one** high-side current plus one bus voltage. It cannot produce solar and battery readings at the same time. [TBD] Choose: (a) the INA219 measures the battery/main rail only, and SPC/SPV are dropped; (b) the INA219 measures a solar panel, and VBAT comes from an ESP32 ADC divider; (c) add a second INA219 (it would need a different I2C address); (d) solar fields stay TBD. Also, the panels' electrical role is undefined (`docs/03` §8). |
| OD-015 | Mount switch count | [PDR] "Mount switch opens" (slide 19), singular; "Mount switch closed" in the READY ON DRONE state; "limit-switch state triggers" (slide 22) | [UNVERIFIED] Two lever micro limit switches | [TBD] What is the second switch for: redundant mount sensing (2-of-2 or 1-of-2 logic), a parachute-latch position sensor, a solar-panel-deployed sensor, or a mechanism end stop? This changes the release logic. |
| OD-016 | Onboard logging medium | [PDR] "onboard logging" (slide 19); "onboard flash memory backup logging" (slide 22) | [UNVERIFIED] SPI Micro-SD module + 16 GB card. [DOC-CONFIRMED] The card is **not** on the invoice (see OD-040). | [RECOMMENDATION] Log flight data to SD and keep the small persistent state (state, one-shot flags) in ESP32 NVS flash. That fits both descriptions, but it is still a decision for the team. [TBD] |
| OD-017 | Battery | [PDR] iPowerUS IP9V-800, "9 V, 800 mAh", 32 g, 7,200 mWh nominal (slides 14, 18) | [UNVERIFIED] 2 × 18650 1S 2500 mAh, ~45 g each (`docs/03`); 2 × TP4056+DW01; 3 × MT3608 | [TBD] The topology is undecided. The PDR power budget, mass budget and example packet (`SPV` = "9V") all assume the 9 V battery. |
| OD-018 | Mass and volume budget | [PDR] Total 428 g; "72g below 500g" (slide 14); 2P, 50 × 50 × 100 mm (slides 6, 13) | [UNVERIFIED] Added or changed parts: 2 × 18650 (~90 g vs 32 g), holders, 2 × TP4056, 3 × MT3608, HC-12, SD module, 2 buzzers, 2 limit switches, possibly a third servo | See `PHASE1_PROPOSAL.md` §2.6. [ASSUMPTION] The battery change alone adds about +58 g, which uses roughly 80 % of the 72 g margin before holders, converters, the radio or the SD module are counted. [TBD] The CAD and mass owner must re-run the budget with weighed parts. |
| OD-019 | Sensors listed in SR-3 | [PDR] "GY-91 + INA219 + BME280" (slide 6, SR-3 derived value) | [UNVERIFIED] BMP280 + MPU6050 + INA219 | [ASSUMPTION] The "≥ 2 sensors" intent is still met with 3 sensors. The derived value in SR-3 is out of date. |
| OD-020 | Telemetry framing | [PDR] Telemetry goes "directly to the GCS receiver MAC address" (slide 17) | [TEAM DECISION] HC-12 is transparent UART with no MAC addressing | [RECOMMENDATION] Use a versioned frame with a CRC (`PHASE1_PROPOSAL.md` §5). HC-12 modules on the same channel all hear each other, so other teams on the same channel are a risk. [TBD] Channel allocation. |

## E. PDR-internal inconsistencies

| ID | Topic | Version A | Version B (and C) | Notes |
|---|---|---|---|---|
| OD-030 | Telemetry rate | [PDR] "≥ 4 Hz" (slide 6, SR-3); "4 Hz rate" (slide 17); "ESP-NOW telemetry at 4 Hz" (slide 19); "100% packet reception at 4 Hz" (slide 20) | [PDR] Power-table row label "Radio (ESP-NOW at 1 Hz)", while the duty column of the same row says "4Hz for entire duration" (slide 18) | [TBD] Which rate is required? [RECOMMENDATION] Treat 4 Hz as the requirement. Four other slides say 4 Hz, and the power table seems to have a label error. Still, Mukund should confirm. |
| OD-031 | Descent time | [PDR] "~20 s" (CONOPS step 7, slide 8); "≈ 20 s from 100 m" (slide 10 bullet) | [PDR] "Descent time (s) 28.8s" (slide 10 table); "~30 s descent" (SR-5, slide 6); "T = 28 seconds" (slide 18) | [ASSUMPTION] Simple check: 100 m ÷ 3 m/s = 33.3 s at constant speed, so neither 20 s nor 28.8 s follows directly from the stated numbers. 20 s would need 5 m/s. 28.8 s might include an unstated free-fall or opening phase. [TBD] Which value is the design basis? It affects the scenario timing and the landing-detection timeout. |
| OD-032 | SR-7 | [PDR] Row "SR-7" exists on slide 6 with **blank** requirement, source and target. Confirmed visually on the rendered slide. | — | [TBD] Is SR-7 intentionally empty, deleted, or missing content? It is recorded as blank in TRACEABILITY. Nothing was invented for it. |
| OD-033 | Two requirement lists | [PDR] Slide 6: SR-1 … SR-7 (7 rows, SR-7 blank) | [PDR] Slide 21: compliance items #1 … #6 | Differences: (1) Slide 21 #5 combines size and mass. That corresponds to SR-1 (2P size) and SR-6 (mass/size). (2) Slide 21 #6 "Descent rate ≈ 3 m/s; telemetry live (not post-landing download)" has no single SR. Its parts appear in SR-4/SR-5 (3 m/s) and SR-3 (live telemetry). (3) SR-5 ("Operates from release (100 m AGL) to ground recovery, ~30 s descent") has no compliance row. (4) SR-6 "Fits drone release mechanism" has no compliance row. (5) SR-4 says "actively … using a servo". Slide 21 #4 only says "Parachute deploys". (6) SR-2 says "deploy outward once airborne". Slide 21 #2 says "demonstrated in flight". [TBD] Which list is authoritative? |
| OD-034 | Compliance #5 self-contradiction | [PDR] Slide 21 #5 marked **"Comply"** | [PDR] The same row's note: "Final CanSat dimensions and mass not yet verified." | [TBD] It cannot be "Comply" and also unverified. The baseline change (OD-017/018) makes it more doubtful. |
| OD-035 | Mass budget arithmetic | [PDR] Slide 14 "Solar panels + mechanism: 41 x 2"; "TOTAL 428 … Component subtotal + approximately 10% growth reserve" | [ASSUMPTION] Calculation: with solar = 82 g, subtotal = 160+82+94+27+32+35 = 430 g, and ×1.10 = 473 g. With solar = 41 g, subtotal = 389 g, and ×1.10 = 427.9 ≈ **428 g**. | So the 428 g total uses **41 g** for solar, not 41 × 2. The slide's own breakdown (≈10 g + 22 g + 9 g = 41 g) also covers both panels. [TBD] Ask for a correction. If 82 g was intended, the total is 473 g and the margin is 27 g. |
| OD-036 | Mass used for the descent calculation | [PDR] "Total mass (g) 500g" (slide 10) | [PDR] Budget total 428 g (slide 14) | [ASSUMPTION] Using the ceiling mass is conservative for descent rate, because v ∝ √m. If the real mass exceeds 500 g, then v ≈ 3.0 × √(m/500) m/s. |
| OD-037 | Servo in solar mechanism | [PDR] Solar mechanism selected: "Spring Assisted … 0 mW draw … no code needed" (slide 12); block diagram: "Spring-Assisted — Passive, No electrical power for actuation" (slide 18) | [PDR] Mass budget solar line includes "servo: 9 g" (slide 14) | [TBD] Is there a servo on the solar-panel latch or not? This decides whether software must send a panel command (Haridas). |
| OD-038 | When the panels deploy | [PDR] "spring-assisted solar panels unlock after detaching from the drone" (slide 19 bullet) | [PDR] State diagram: PARACHUTE DEPLOY → (CHUTE OPEN) → PANEL DEPLOY (slide 19 figure); CONOPS: "Solar panels deploy after canopy opens" (slide 8); slide 13: "1. PocketQube separates 2. Parachute opens 3. Panel latches release" | [TBD] Version A means deploy at separation. Versions B and C mean deploy after the chute opens. What triggers the panel latch, and is it observable by software? |
| OD-039 | Drone-side vs CanSat-side servo | [PDR] "servo-actuated locking pin" on the drone bracket; "Verify … drone servo and PocketQube servo operation" (slide 9) | [PDR] Mass budget: servo in parachute line (9 g) and servo in solar line (9 g) (slide 14) | [ASSUMPTION] There may be three servo roles: drone pin, parachute latch, and solar latch. That would explain 3 × SG90, but nobody has confirmed it (OD-050). Also, who commands the drone-side servo, and which MCU? |
| OD-041 | Release detection wording | [PDR] "Mount switch opens + GY-91 acceleration change; BME280 descent provides backup confirmation" (slide 19) | [PDR] "limit-switch state triggers with a multi-sensor software check (barometric altitude drop + IMU acceleration **spike**)" (slide 22) | [ASSUMPTION] In physics terms, a released body in free fall reads about 0 g of specific force on an accelerometer. That is a *drop* in magnitude, not a spike. A spike would come from the release jolt or from parachute opening. See `PHASE1_PROPOSAL.md` §3. |
| OD-042 | Sampling vs telemetry rate | [PDR] "GY-91 at 4 Hz, BME280 at 4 Hz, INA219 at 4 Hz" (slide 19), i.e. sampling = telemetry = 4 Hz | — | [RECOMMENDATION] Sample faster internally than telemetry is sent. At 4 Hz, a sample comes every 250 ms, so a short release or opening transient can fall entirely between samples. [TBD] This is a design-rate decision (Mukund and Gautam). |
| OD-043 | Example packet units | [PDR] Example: `001, 00:01:23.4 , 342 , 85.4, 24.5, 0.98atm, 80%, 100uA, 9V, 82%, DESCENT` (slide 17) | [PDR] Acronyms: "VBAT Battery Voltage" (slide 4) | [ASSUMPTION] Matching values to fields: `SPV`=9V (a 4 V solar panel cannot output 9 V; this looks like the 9 V battery), and `VBAT`=82% (a percentage, not a voltage). Values carry text units (atm, %, uA), and STATE is text. [TBD] Field meanings. |
| OD-044 | Power budget duration | [PDR] Energy computed "With T = 28 seconds" (slide 18) | [PDR] The mission includes ground check, mount, ascent and hold before release (slide 8), and telemetry starts at "power-on" (slide 17) | [ASSUMPTION] The budget covers only the descent. Powered time before release (pad + ascent + hold) and after landing (recovery buzzer) is missing. With 2 × 18650 this probably isn't a capacity problem, but it is undocumented. [TBD] |
| OD-045 | Scoring rationale oddities | [PDR] Slide 7: "Ease of build & test" gives Concept B 5 "since it needs mechanical and software integration"; slide 12: "Complexity" gives spring 3 "(no code needed)" and servo 4 | — | [ASSUMPTION] The scores seem inverted relative to their rationale. Low priority. Recorded only for completeness. |
| OD-046 | Test schedule | [PDR] Bench Nov 05, Range Nov 10, Solar Nov 15, Drop Nov 20, Integrated 100 m drop Nov 25, Drone fit check Nov 28 (slide 20) | — | [TBD] Today is 2026-11-18. No results for the Nov 05–15 tests are in the repo, so they must be treated as not done. Also, the fit check (Nov 28) comes *after* the integrated drop (Nov 25). |
| OD-047 | Team roles | [PDR] Slide 3 org chart: Haridas = "Ground Station and Data Analysis"; Gautam = "Aerodynamics and Descent"; Aditya = "Structural Design and CAD"; Shikhraj = "Payload"; Krish Chhugani = "Project Manager, Electrical Power System" | [PDR] Slide 2 presenter split: Haridas = Structure, Solar Panel & Parachute; Mukund = Sensors, Telemetry & Power; Gautam = Systems Overview; Shikhraj = Integration & Test. [TEAM DECISION] Meeting brief uses your mapping (Haridas, Mukund, Gautam, Shikhraj). | [RECOMMENDATION] Invite Krish (EPS owner on slide 3, presenter of the power budget) to the power questions, and Aditya to the mass and volume questions. |

## F. Procurement evidence vs team-reported list (OD-040)

[DOC-CONFIRMED] Read from `references/components_invoice_photo.png` (Probots invoice, 22 line items + shipping, "Items in Total 58.00"). An invoice line shows only that an item was listed or bought. It never shows installation or operation.

| Team-reported item (`docs/03`) | Invoice line | Note |
|---|---|---|
| ESP32 DevKit, 30-pin, CP2102, Type-C ×2 | #1 "ESP-WROOM-32 ESP-32S Development Board 30-Pin WiFi + Bluetooth with CP2102 & Type-C" ×2 | Matches. The exact board vendor/revision is still TBD. |
| HC-12 ×2 | #2 "HC12 Long Range Wireless RF Transceiver Module 433Mhz SI4463" ×2 | Matches. |
| BMP280, MPU6050/GY-521, INA219 | #3, #4 "…GY521", #10 "INA219 … CJMCU-219" | Matches. The INA219 breakout variant is CJMCU-219. |
| SG90 ×3, 18650 2500 mAh ×2, holders ×2, TP4056 ×2, MT3608 ×3, toggle switch ×2 | #5, #6, #7, #8 "…with Current Protection – Type C", #11 "MT3608 … 2-24V to 5-28V 2A", #9 "6 Pin Toggle Switch 3A 250V" | Matches. |
| 470 µF **16 V** ×5 | #12 "470uF **50V**" ×5 | Voltage differs. A higher rating is harmless, but the capacitor is physically larger. |
| 100 nF ceramic, **through-hole** ×10 | #13 "TCC0402X7R104M500AT … **0402 SMD/SMT**" ×10 | 0402 is a ~1 × 0.5 mm surface-mount part, which is very hard to hand-solder on perfboard. Flag to Mukund/Krish. |
| JST-PH 2.0, 2-pin pairs with wire ×5 | #14 "20 Pin JST PH **2.54mm** Top Entry Header (Straight)" ×5 | Description mismatch: JST-PH is 2.0 mm pitch. Check what actually arrived. |
| MB102, Micro-SD SPI module, breadboards ×3, jumpers, headers, USB-C ×2 | #15, #16, #17, #18–20, #21, #22 | Matches. |
| **Micro limit switches ×2, active buzzers ×2, 16 GB micro-SD card, solar panels ×2, resistor kit, LEDs, enclosure** | **Not on this invoice** | [UNVERIFIED] These come only from the team list. Ask whether they have been bought and received. |

## G. Hardware-assignment decisions (summary; details in MEETING_BRIEF.md)

| ID | Decision needed | Owner (likely) | Status |
|---|---|---|---|
| OD-050 | Servo → mechanism mapping; which servos are on the CanSat vs the drone | Haridas, Shikhraj | [TBD] |
| OD-051 | Limit-switch roles, NO/NC wiring, pull-ups, logic polarity | Haridas, Gautam | [TBD] |
| OD-052 | Buzzer roles and driver transistor | Mukund | [TBD] |
| OD-053 | Power topology for both cells, chargers, switches and MT3608s; INA219 placement | Mukund / Krish | [TBD] |
| OD-054 | GPIO allocation (constraints in `PHASE1_PROPOSAL.md` §2.5) | Mukund + software | [TBD] |
| OD-055 | HC-12 mode, UART baud, air rate, channel, TX power, SET-pin usage | Mukund | [TBD] |
| OD-056 | Exact BMP280 address (0x76/0x77) | Mukund | [TBD] |
| OD-057 | Flight thresholds, debounce, delays, deployment timings | Gautam (with test data) | [TBD] The firmware holds no default values. |
| OD-058 | Who triggers release from the drone, and whether the drone tells the CanSat | Shikhraj | [TBD] |
| OD-059 | Physical actuator enable: safety review, arming procedure | Whole team | [TBD] The compile-time default is **disabled**. |
| OD-060 | **Stuck mount switch vs sensor evidence: may the parachute be requested?** (see §H) | **Whole team; safety approval required** | [TBD] **CRITICAL, undecided.** No default policy exists in the firmware. |
| OD-061 | HC-12 link feasibility | Mukund, Shikhraj | [TBD] **Not established.** Only the UART byte rate has been calculated. The RF test plan (`PHASE1_PROPOSAL.md` §2.1, RF-01…RF-07) has not been run. The PDR acceptance criterion "100% packet reception" needs reconfirming. |
| OD-062 | Is a *measured* parachute-opening shock required? If so, with what hardware? | Mukund, Haridas | [TBD] The PDR gives 30 g only as a design load (slide 10). The MPU6050 (±16 g, clips) is suitable for free-fall detection, not for measuring that peak. See `PHASE1_PROPOSAL.md` §2.2. |
| OD-064 | **Provisional state-machine behaviours introduced in Phase 2 step 3 (software structure, no values) — need Gautam/team confirmation** | Gautam, team | [TBD] See list below. |
| OD-065 | **Landing confirmation and abnormal LANDED paths** (review 2026-11-18) | Gautam, team | [TBD] Provisional software behaviour implemented; needs approval. See details below. |
| OD-066 | **What sensor health can realistically be verified with the current hardware** | Mukund, software | [TBD] Software uses several kinds of evidence; drivers and bench data needed. See details below. |
| OD-067 | **Behaviour when the parachute-request flag cannot be persisted** | Gautam, team | [TBD] Undecided policy, no default: RequestAnyway vs WithholdUntilPersisted. See details below. |
| OD-063 | Power architecture | Mukund, Krish | [TBD] **Not finalised.** Risks PR-1…PR-9 and tests PT-01…PT-09 are in `PHASE1_PROPOSAL.md` §2.4a. No power-management decision has been taken. |
| OD-068 | **Limit-switch hardware questions SW-Q1…SW-Q5 (unresolved dependencies)** | Haridas, Mukund, Gautam | [TBD] **Answers not available.** Software must not assume any answer. See §I. |
| OD-069 | **Recovery when the persisted record is corrupt or absent mid-flight** | Gautam, team; safety approval | [TBD] **Hazard; no approach selected.** Current behaviour (R-A) documented by HAZARD tests. See §I. |
| OD-070 | **Downstream deployment interlock (mock-only implementation, proposed rules)** | Whole team; safety approval | [TBD] [PROPOSED] Implemented for simulation only; physical execution disabled. Gate rules need approval. See §I. |
| OD-071 | **Hardware watchdog (`machine.WDT`) for the MicroPython flight software: enable or not, timeout, what feeds it** | Whole team; safety approval | [TBD] Not enabled by software. See §J. |
| OD-072 | **Fault reporting for the MicroPython port: unhandled exceptions, and telemetry fault-field width** | Software, Mukund | [TBD] No port-only fault bit exists (bit 31 was proposed in module 1 and withdrawn). The proposed telemetry `fault` field is uint16 (PHASE1_PROPOSAL §5 row 7), but C++ fault bits already reach bit 18, so bits 16-18 would be lost. See §K. |
| OD-073 | **Must buzzer pins be resolved before a hardware boot?** | Software, Mukund | [TBD] Kept for C++ parity; no safety reason while no buzzer code exists. See §K.  **RESOLVED (Rev 8) by D-018:** not required until buzzer code exists. |
| OD-074 | **Precompiled `.mpy` files vs the boot-time source scan** | Software | [TBD] Currently refused. Integrity-manifest option described in §K; not implemented.  **Deferred (Rev 8)** until RAM requires precompilation. |
| OD-075 | **Float-boundary risk in barometric-descent detection (C++ vs MicroPython)** | Software, Gautam | [TBD] Closest SYNTHETIC drop was 0.0041 m from `baro_min_drop_m`; C++/Python altitude can differ by up to ~0.0053 m per value. No decision flipped in the 68 parity runs. See §K. |
| OD-076 | **IMU hardware switched to a GY-91 (user-reported 2026-11-19)** | Software, Mukund, team | [TBD] The physical IMU is now a GY-91. The flight baseline (D-007/D-011, `CLAUDE.md`, flight code) is still MPU6050 and is NOT changed. Open: which chip is fitted (MPU-6500/9250/other, by WHO_AM_I from `bringup/esp32_hw_diag.py`); the GY-91's on-board BMP280 alongside the standalone BMP280 (possible shared I2C address); whether the magnetometer is used; and what the flight software must change (identity checks, ranges, validator limits). |
| OD-077 | **User-reported bring-up pins (2026-11-19), unverified** | Mukund + software | [TBD] I2C SDA GPIO21, SCL GPIO22; SPI SCK GPIO18, MISO GPIO19, MOSI GPIO23, SD CS GPIO13 (moved to GPIO5 on 2026-11-24, D-023; SD VCC from VIN 5 V). Used only in `bringup/esp32_hw_diag.py`. NOT in the flight `hardware_config.py` (all pins still TBD, OD-054) until the wiring is verified and approved. HC-12 not wired (unavailable). |
| OD-078 | **Radio switched to ESP-NOW (user-directed 2026-11-24, D-020): link performance not established** | Mukund, Shikhraj, software | [TBD] Implemented in `esp32/` and tested in software only ([SIMULATED] in-memory radio). Not measured: range against the [PDR] 150 m line-of-sight target (slide 16), link gap ≤ 1.0 s (slide 17), 2.4 GHz attenuation through the enclosure and near the drone, interference from other teams' 2.4 GHz equipment, and the ESP32 dev-board PCB antenna's orientation. OD-061 (HC-12 feasibility) is moot while D-020 stands; the HC-12 modules stay unused. The Wi-Fi channel (1) is a [BENCH DEFAULT]. |
| OD-079 | **Telemetry schema v1 (binary, 78-byte frame + 27-byte ACK) needs team approval** | Software, Mukund, team | [TBD] [PROPOSED] Specified in `docs/10_esp32_espnow_bringup.md` §4, implemented in `esp32/lib/cs_proto.py`. Differs from the PHASE1 §5 CSV proposal (which assumed HC-12 transparent UART). Fault field is uint32, which keeps C++ fault bits 16-18 (addresses the width half of OD-072). Not yet carried: `team` id, latched event bits, switch bits, actuator decision bits, `H%`/SPC/SPV (OD-013/OD-014). Rate 4 Hz per [PDR], OD-030 still open. **2026-11-24: approved by the user (software lead) for initial bench testing, provisionally, pending team sign-off.** |
| OD-080 | **How to run the flight software on the real board: `cansat/hal_mp/` and approved pins** | Software lead, team; safety approval | [TBD] The existing guards forbid `cansat/hal_mp/`, assigned pins in `hardware_config.py`, and a hardware boot with unapproved parameters (scan_guards, boot check B4). These guards were NOT changed. `esp32/lib/cs_fsw_bridge.py` connects the bring-up drivers to `FlightSoftware` and is tested on the laptop against all 17 SYNTHETIC scenarios; on the board it currently returns "refused". Needed to proceed: approval to create `cansat/hal_mp/` (or move the esp32 drivers there), an NVS `PersistentStore`, approved pins (OD-054), and approved parameters (OD-057, OD-060). |
| OD-081 | **IMU freshness bit (`data_ready`) on the GY-91** | Software | [TBD] The driver reports INT_STATUS.DATA_RDY_INT. [ASSUMPTION] It is set without enabling the data-ready interrupt. The diagnostic prints how often it was seen (checklist H-IMU-3). If it never sets, the flight software's validator would reject every IMU sample as not fresh; bring-up telemetry does not depend on it. |
| OD-082 | **Which BMP280 is which, and which feeds altitude** | Mukund, software | [TBD] Software cannot tell the GY-91's BMP280 from the standalone breakout. Two at the same address are indistinguishable from one; the suite then raises `BARO_DUP_SUSPECT`. `flight_config.BARO_PRIMARY_ADDR` selects the altitude source (default: lowest address). The altitude reference defaults to the first valid reading after boot (no sea-level value assumed). |

**OD-064 details** — [RECOMMENDATION] provisional behaviours, implemented so the software can run; each is configurable or easy to change, none is a decision:
1. Transitions are strictly the slide-19 chain. Consequence ([SIMULATED]): if ASCENT is never detected (e.g. barometer failed on the pad), release logic is never armed and no parachute request is ever made.
2. TAKEOFF = altitude gain over the self-check ground reference sustained for a time (`ascent_min_gain_m`, `ascent_confirm_ms`, no values).
3. CHUTE OPEN = |a| ≥ `chute_open_accel_min_g` (or saturation) after the request. **Rev 4:** `chute_open_timeout_ms` now only raises an alarm (`ChuteOpenNotConfirmed`, `kFaultChuteOpenNotSensed`, status OPENING_NOT_SENSED). The state stays PARACHUTE_DEPLOY. *(Superseded: earlier a timeout moved to PANEL_DEPLOY.)*
4. **Rev 4:** PANEL_DEPLOY → DESCENT requires `DescentConfirmed` (sustained barometric descent for `descent_confirm_ms`). Panel deployment itself has no sensor and is reported as UNKNOWN, never as done. *(Superseded: earlier a fixed dwell time moved to DESCENT; `panel_deploy_wait_ms` was removed.)*
5. TOUCHDOWN: see OD-065. [SIMULATED] With SYNTHETIC tolerances, the `noisy` scenario never confirms descent or touchdown and ends in PANEL_DEPLOY.
6. Self-check requires baro, IMU and switches healthy with the mount closed (power optional via `selfcheck_require_power`). A sensor that fails `begin()` keeps the CanSat in POWER_ON_SELF_CHECK for that boot ([SIMULATED] `imu_not_detected`). Whether the mission may arm with a missing sensor is still open (docs/07).
7. Reset recovery: in-flight states resume; the separation timer restarts at boot (delays, never advances, a pending request); a recorded parachute request is never re-issued ([PDR] slide 19 "prevents repeated deployment commands"). Retry-after-reset (G4) remains a team question.
8. Persistence failure: **Rev 4:** now an explicit undecided policy, OD-067.

**OD-065 details: landing confirmation (review item 1 and 4)** — [RECOMMENDATION] provisional, implemented, needs approval.

*Root cause of the false LANDED* ([SIMULATED], `mounted_drone_falling`, P-B/C/G, before Rev 4). Three assumptions were chained:
1. The chute timeout moved PARACHUTE_DEPLOY → PANEL_DEPLOY although no opening was sensed.
2. A fixed panel dwell moved PANEL_DEPLOY → DESCENT.
3. TOUCHDOWN only checked stability (altitude steady, |a| ≈ 1 g). A CanSat hanging on a hovering drone at 64 m, with its switches reading *mounted*, satisfied it.

*Correction (Rev 4):*
- **No state is left by time alone.** Tested by restoring every state and ticking for one simulated hour with no events.
- **Touchdown now requires all of:**
  - a self-check ground reference (without one, `kFaultLandingUnconfirmable` is raised and touchdown is never assumed);
  - altitude within `landed_max_alt_above_ground_m` of that reference;
  - stability and |a| ≈ 1 g for `landed_window_ms`;
  - valid barometer and IMU throughout the window.
- **A mount switch reading closed at touchdown** is reported (`kFaultLandedMountClosed`) but does not block. Otherwise a stuck switch would also block landing.
- **Two abnormal, flagged transitions are added:** PARACHUTE_DEPLOY → LANDED and PANEL_DEPLOY → LANDED, on a *confirmed* touchdown only. Without them, a CanSat whose opening was never sensed could never report LANDED, and the later recovery buzzer could never be triggered. The chute status (e.g. OPENING_NOT_SENSED) is kept and reported. **Needs team approval:** it changes the slide-19 transition set.
- [SIMULATED] Result: `mounted_drone_falling` now ends in PARACHUTE_DEPLOY with OPENING_NOT_SENSED under P-B/C/G. It never reaches LANDED. Healthy scenarios still land.

*Remaining limits:*
- [ASSUMPTION] Barometric drift over a flight could move the ground reference by more than the band, and then touchdown would never be confirmed. Bench drift data is needed.
- If the drone *lands* with the CanSat still attached, LANDED would be reported, with the mount-closed flag.
- RELEASE_DETECTED / ASCENT → LANDED is still not permitted. Under P-A with a stuck switch, a CanSat that really fell would stay in ASCENT.

**OD-066 details: sensor health beyond numerical values (review item 3)**

The all-zero rule alone was weak: a fault producing *plausible* values passes it. Rev 4 adds several kinds of evidence to the validator. All are implemented in software and tested with mocks. None is [HW-VERIFIED], and no physical driver exists.

| Evidence | MPU6050 | BMP280 | INA219 | Status |
|---|---|---|---|---|
| Bus transaction succeeded (I2C ACK, expected byte count) | yes | yes | yes | [ASSUMPTION] Achievable with Arduino `Wire` return codes. Software: `comm_ok` → `kRejectComm` |
| Chip identity at boot | `WHO_AM_I` register | chip-ID register | none (config read-back only) | [ASSUMPTION] Register values recalled from datasheets, unverified. Software: part of `BootReport.*_ok` |
| New-data status per sample | `INT_STATUS.DATA_RDY` | status register (measuring / im_update) | bus-voltage register `CNVR` (and `OVF` overflow) | [ASSUMPTION] Recalled. Software: `data_ready` → `kRejectNotFresh` |
| Timestamp advance and age | yes | yes | yes | Implemented (`kRejectStaleRepeat`, `kRejectStaleAge`) |
| Stuck output (N identical samples) | yes | possible later | possible later | Implemented for the IMU only (`imu_stuck_identical_samples`, no default). [ASSUMPTION] Relies on real sensor noise; bench data must confirm noise is always present |
| On-chip self-test | yes: an electrostatic actuation test of each axis, run on the ground (it disturbs readings) | no | no | Software: `BootReport.imu_self_test`. FAILED blocks self-check; NOT_RUN is flagged and, provisionally, does not block. Acceptance limits come from the datasheet, not chosen here |
| Physical plausibility (non-finite, beyond range, all-zero) | yes | yes | yes | Implemented; one heuristic among the others |
| Cross-sensor consistency | free fall vs barometric descent | — | — | Already used by release logic; it cannot help when both agree for the wrong reason (S4c) |

*What realistically cannot be verified with the current hardware:*
- **No redundant IMU or barometer.** A sensor that is healthy but measuring a misleading situation (the drone falling) is indistinguishable from a real release.
- **No calibration reference in flight.**
- **No sensor power-cycle control**, because sensors share the bus and supply (the power topology is TBD).
- **Bench test needed:** what the real MPU6050 returns on a disconnected or brown-out bus (zeros? 0xFFFF? last value?). That determines which rule catches it.

**OD-067 details: persistence failure (review item 5)** — undecided policy, no default.
- **Background:** the one-shot "parachute requested" flag must be saved before the request, so that a reset cannot cause a second request. If saving fails, there are two options:
- **RequestAnyway:** the request is queued once in this boot.
  - Consequence ([SIMULATED], test `persist_failure_request_anyway_can_duplicate_after_reset`): if the MCU then resets, the record still says "release confirmed, chute not requested". After T_SEP_MIN a **second request** is made.
  - For a servo latch, a second actuation could be harmless or harmful (moving into deployed lines, current draw during descent). This depends on the mechanism (OD-050).
  - It also breaks the [PDR] slide 19 "prevents repeated deployment commands" guarantee in that case.
- **WithholdUntilPersisted:** no request while saving fails; the save is retried every tick.
  - Consequence ([SIMULATED], test `persist_failure_withhold_never_requests_while_storage_fails`): if storage never recovers, **no parachute request is ever made**. That is fail-dangerous for recovery.
- **Mitigation ideas, not decided:**
  - a bounded retry budget, then fall back to one of the above;
  - a second store for the flag, e.g. ESP32 RTC memory, which [ASSUMPTION] survives a software reset but not power loss;
  - logging the request to SD as additional evidence;
  - bench-testing how often NVS writes actually fail under brown-out.
- **Note:** the state record itself can also be stale if writes fail, so after a reset the CanSat may resume an *earlier* state than it was in.

---

## H. OD-060: Stuck mount switch with sensor evidence of release (CRITICAL; team decision)

**Status:** [TBD] UNDECIDED. **This document does not choose an option.** The firmware will carry no default. Simulation runs every option side by side. A hardware build will refuse to compile until the team records an approved choice in `docs/decisions/DECISIONS.md`.

### H.1 The scenario
The CanSat has really been released, but a mount switch is mechanically stuck **closed**, so it still reads "attached". Meanwhile the MPU6050 reports free fall (|a| near 0 g) and the BMP280 reports falling altitude.

**The PDR rule:** [PDR] "SAFETY INTERLOCK: No parachute actuation while still mounted." (slide 19). The PDR does not say how "mounted" is determined, or what happens when the sensors disagree.

### H.2 Why there is no obviously safe answer
The software cannot know which world it is in. Both failure directions are dangerous:

| | Software **blocks** the parachute | Software **requests** the parachute |
|---|---|---|
| **World 1: really released** (switch failed) | **Missed deployment.** The CanSat falls about 100 m without a parachute: vehicle lost, and a ~0.4–0.5 kg [PDR slides 10/14] object lands at high speed on whatever is below. | Correct outcome. |
| **World 2: really still mounted** (the sensors are fooled) | Correct outcome. | **Deployment under the drone.** The canopy and lines can tangle in the rotors. The drone could be lost, and a much heavier object could fall from height. |

[ASSUMPTION] Ways World 2 could happen, i.e. free fall and descent seen *while still mounted*:
- **IMU fault reading as zeros.** For example, a failed I2C read or a disconnected sensor returning 0x0000 looks exactly like 0 g free fall. This is a realistic software and hardware failure, not an exotic one.
- **The drone itself descending fast or falling** (aggressive descent, or power loss). In that case the barometer agrees with the IMU.
- **Barometer disturbance** (prop wash) combined with an IMU glitch.

**How likely each world is: unknown.** [TBD] It depends on the switch's mechanical design, the drone's flight envelope, and the measured sensor fault modes.

### H.3 Candidate approaches

None is recommended here.

| ID | Approach | How it behaves in the scenario | Safety implications | Trade-offs and costs |
|---|---|---|---|---|
| **P-A** | **Strict veto:** the switch must read "open" for any parachute request (the literal PDR interlock) | Blocks. Logs DEGRADED. No parachute | Fully protects the drone (World 2). **Single point of failure** for recovery: one stuck switch means a guaranteed ballistic fall in World 1 | Simplest to implement, review and test. Puts all trust in one mechanical part |
| **P-B** | **Sensor override with stricter corroboration:** allow when free fall **and** baro descent are both sustained, all sensors pass validity checks (non-zero, not stale, WHO_AM_I OK), and possibly extra conditions such as altitude loss beyond what the drone could plausibly do | Requests after a longer confirmation, flagged DEGRADED | Covers World 1. Exposure to World 2 depends on how well the validity checks exclude IMU zero-faults and on drone behaviour | The extra waiting eats the fall-time budget (≈4.5 s from 100 m ignoring drag; see `PHASE1_PROPOSAL.md` §3.2). It needs real test data to tune, and it is more complex to verify |
| **P-C** | **Voting (2 of 3)** among switch-open, free fall and baro descent | Requests (2 of 3 agree) | Tolerates any **one** failed indicator, including a stuck switch *or* a faulty IMU. Two simultaneous faults (for example a zeroed IMU while the drone descends) defeat it | Symmetric and well-understood. Assumes the three indicators fail independently, which needs checking (the IMU and baro share I2C and power) |
| **P-D** | **Redundant mount switches:** use both limit switches on the mount; "released" when either opens (1-of-2), still corroborated by sensors | Avoids the scenario if only one switch sticks | Fewer stuck-closed failures. **More stuck-open (premature) failures**, which the sensor corroboration must catch | A mechanical decision (Haridas). Uses the second switch, whose role is still undecided (OD-015) |
| **P-E** | **External confirmation:** the ground station or drone side tells the CanSat that release happened (uplink command or drone signal) | Depends on the link | Adds an independent indicator | Needs an uplink (none in v1, and the PDR uplink is undefined). RF latency and loss during a ~4.5 s window. Uplink commands that can cause deployment need their own safety review |
| **P-F** | **Mechanical path:** a lanyard or static line from the drone pulls the parachute latch or pin on separation (a hybrid with [PDR] Concept A, slide 7) | Parachute release does not depend on the switch or software | Removes software from the critical path. New risks: snagging, and the lanyard opening the parachute too close to the drone | A mechanical redesign (Haridas). Changes SR-4's "actively … using a servo" wording |
| **P-G** | **Delayed fallback:** as P-A, but if sensors-only evidence persists for a further time T_FALLBACK, request anyway | Late request | Partly covers World 1, if enough altitude remains | Given the ~4.5 s budget, the fallback may come too late to help. The value of T_FALLBACK needs drop data |

The approaches can be combined, for example P-D + P-C, or P-F as a backup to software.

### H.4 Evidence needed to decide
1. The mount-switch mechanical design and its likely failure modes (stuck closed vs bouncing open): Haridas.
2. The drone's possible descent rates and failure behaviour, and whether flight procedures rule out fast descents while the CanSat is mounted: Shikhraj.
3. MPU6050 and BMP280 fault behaviour on our actual wiring (what a failed read returns), from bench fault-injection tests.
4. Drop data giving the real fall-time budget from 100 m with drag (sets what is achievable).
5. Mounted-on-drone sensor logs (vibration, prop-wash pressure) to judge how separable the two worlds are.

### H.4a Simulated comparison (Phase 2 step 3) — [SIMULATED], not hardware validation
SYNTHETIC scenarios and SYNTHETIC parameters (`firmware/sim/scenarios/`). This shows how each candidate policy *behaves as implemented*; it says nothing about which world is more likely or about real thresholds. **No option is recommended.**

| Scenario (truth) | P-A Strict veto | P-B Sensor override | P-C 2-of-3 vote | P-G Delayed fallback |
|---|---|---|---|---|
| S4 `stuck_switch_released` — really released, switches stuck closed | **no request** (stays ASCENT, degraded flag) | request (CanSat released) | request (CanSat released) | request after fallback delay |
| S4b `mounted_imu_zero` — really mounted, IMU returns all-zero reads, drone descending | no request | no request | no request | no request |
| S4c `mounted_drone_falling` — really mounted, healthy switches, drone itself in near free fall | no request | **request while still mounted** | **request while still mounted** | **request while still mounted** |

[SIMULATED] Observations:
1. S4b is protected for every policy only because the validator rejects all-zero IMU reads; if an IMU fault produced *plausible* low-g values instead of exact zeros, S4b would behave like S4c.
2. S4c shows the World-2 hazard concretely: P-B, P-C and P-G cannot distinguish "CanSat released" from "drone falling with CanSat attached" using IMU + baro alone. *(Rev 3 also showed a false LANDED here. Corrected in Rev 4, OD-065: the state now stays PARACHUTE_DEPLOY with OPENING_NOT_SENSED.)*
3. P-A is the only policy that never requests while mounted, and the only one that never requests in S4.

### H.6 Independent evidence that could separate "released" from "drone moving" (review item 2)

**No option is chosen, and none is enabled.** P-B, P-C and P-G remain simulation-only candidates. The hardware build still refuses to compile without an approved policy. The core problem is that IMU and barometer measure the CanSat's *motion*, and the CanSat moves exactly like the drone while attached. Only evidence about the *physical connection* to the drone is independent of drone motion.

| Evidence | What it observes | Hardware needed | Distinguishes S4c? | Main weaknesses |
|---|---|---|---|---|
| Second mount switch on a **different** actuation path (e.g. one on the pin, one on the body face) | Connection, via two mechanisms | In inventory (2 switches) [UNVERIFIED]; mechanical design (Haridas) | Yes, if they are independent | Common-mode jamming if mounted the same way; adds a stuck-open (premature) risk |
| **Break-wire / pull-pin continuity loop** across the interface (a GPIO with pull-up, opened when the CanSat leaves) | Connection, electrically | Wire + connector + resistor: very low mass/cost | Yes | Must not open during ascent vibration; connector retention design |
| **Hall-effect sensor + magnet** on the drone bracket | Proximity of the bracket, contactless | Purchase (sensor + magnet) | Yes | Mass; magnet near the IMU (no magnetometer in the baseline, so low impact) |
| **IR/optical proximity** to the bracket | Proximity | Purchase | Yes | Sunlight interference; alignment |
| **Ground-station uplink "released"** (operator or drone-release event over the HC-12) | Release command, independent channel | In inventory (HC-12 is two-way) [UNVERIFIED]; needs an uplink design | Yes, if timely | RF loss/latency in a ~4.5 s window; uplink safety review; half-duplex conflicts with telemetry |
| **Operator arming window** (GS arms release logic only at the hold point) | Shortens exposure time | HC-12 uplink | Partly (S4c outside the window is ignored) | Does not help if the drone falls during the window |
| **Lanyard / static line** (P-F) | Connection, mechanically drives the latch | Mechanical | Yes; removes software from the critical path | Snag risk; opening close to the drone |
| Vibration signature (prop frequencies disappear after release) | Indirect | High-rate IMU sampling + spectral processing | Weak: a falling drone with stopped motors looks similar | Unproven; needs data |
| Drone telemetry (drone's own IMU says the drone is falling) | Drone state | Link from drone to CanSat/GS | Yes | Integration with the drone autopilot; probably impractical |

- [RECOMMENDATION, for discussion only] The cheapest independent evidence with parts already listed is a **second switch on a different mechanism** or a **break-wire loop**. Each adds one GPIO input (ESP32 pin budget, PHASE1 §2.5).
- Any of these changes the release-detection inputs, so it is a hardware-interface decision for Haridas, Mukund and Shikhraj. Software can model it in simulation as an extra indicator once chosen.

### H.5 Approval record (to be completed by the team)
| Field | Value |
|---|---|
| Option(s) chosen | [TBD] |
| Approved by (names) | [TBD] |
| Date | [TBD] |
| Evidence used | [TBD] |
| Residual risk accepted | [TBD] |
| Recorded in `DECISIONS.md` as | [TBD] |

---

## I. Rev 5 additions: switch dependencies, record recovery, downstream interlock

### I.1 OD-068: limit-switch questions that software depends on

The mechanical answers are not currently obtainable. Software development continues without them, and **no answer is assumed** anywhere in code or tests. [TBD] All five stay open.

| ID | Question | Related | What depends on it |
|---|---|---|---|
| SW-Q1 | **Availability:** are both switches bought and fitted? (Not on the invoice, §F.) | OD-040 | Whether any switch-based evidence exists at all |
| SW-Q2 | **Role:** what is each switch for (mount sensing, a latch position, panels, an end stop)? | OD-015 | `SwitchVote`; whether two mount indicators exist |
| SW-Q3 | **Placement:** where does each switch sit, and what physical condition does it show (pin retracted vs CanSat body clear of the bracket)? | §H.6 | What "connection lost" means; any connection assessment |
| SW-Q4 | **Independence:** separate actuators and mechanical paths, or can one jam, debris or deformation affect both? Shared connector or ground? | §H.6 | Whether two switches count as diverse evidence (A2) |
| SW-Q5 | **Wiring:** NO/NC, pull-up location, logic polarity, and what a broken wire or connector reads as ("mounted" or "released") | OD-051 | `switchN_open_is_high`; fail direction of wiring faults |

**Software consequences** [DOC-CONFIRMED from the code]:
- The deployment interlock (I.3) takes an **abstract** connection assessment, so it needs none of these answers.
- No firmware code produces a connection assessment. A guard check enforces this.
- The existing release detector still reads two raw switch levels with SYNTHETIC polarity. That is unchanged and still [TBD].

### I.2 OD-069: corrupt or absent persisted record mid-flight

**Current behaviour (R-A)** [DOC-CONFIRMED from code, `RecoveryManager::restoreOnBoot()`; SIMULATED in the scenarios below]:
- A corrupt record (bad magic, version, CRC or state code) restarts at POWER_ON_SELF_CHECK. One-shot flags and the ground reference are discarded, and `kFaultRecoveryRecordCorrupt` is raised.
- An absent record is treated as a first boot. **No fault is raised.**
- `EventDetector::selfCheck()` passes only if the mount reads closed.

**What happens** [SIMULATED, not hardware validation; SYNTHETIC scenarios]:

| Scenario | Outcome under every policy (A, B, C, G) | Why |
|---|---|---|
| `corrupt_record_after_release`: reset after ReleaseConfirmed, before the request | **No parachute request.** Stays in POWER_ON_SELF_CHECK for the rest of the flight. | The mount reads open after separation, so self-check never passes. Release detection runs only in ASCENT and RELEASE_DETECTED. |
| `record_erased_after_release` | Same, and **not even the corrupt-record fault** is raised | Absent looks like a first boot |
| `corrupt_record_after_request` | The request was made before the reset. The new boot reports NOT_REQUESTED. | One-shot knowledge is lost. Any approach that resumes flight must answer "was it already requested?" |
| `corrupt_record_mounted_ascent` | Self-check **passes again at altitude** and captures that altitude as "ground". In this SYNTHETIC profile the flight then proceeds, but it ends in DESCENT, never LANDED. | The touchdown check compares against the wrong ground reference |
| Unit test: write failure, then reset | Resumes the **last successfully written** state (ASCENT), with the release one-shot lost | `persist()` failures leave the older record in place |

**Also observed:** a self-check stuck because the mount reads open raises **no specific fault** (`kFaultSelfCheck` stays clear), so telemetry would not show why it is stuck.

**Candidate approaches** [PROPOSED; none selected, none implemented]:

| | Approach | Main failure modes | Hardware or team dependency |
|---|---|---|---|
| R-A | Current: restart at self-check | No parachute after separation; wrong ground reference while mounted; erased record undetected | Accept the risk explicitly |
| R-B | Two copies of the record with sequence numbers; use the newest valid one | Lowers the probability only: both copies corrupt, a torn write, or a stale "newest" | [HW-VERIFY] ESP32 NVS write atomicity under brownout (PT-06) |
| R-C | A distinct "state unknown" boot mode that infers the situation from sensors | Comes back to release detection: can deploy while still mounted (the OD-060 hazard) | OD-060 / OD-068 |
| R-D | Mark the board as set up for flight, so a missing record means fault, not first boot | Only distinguishes the cases; the marker itself can be lost. Recovery still needs another approach. | Pre-flight procedure |
| R-E | Ground station supplies the state over an uplink (as in A3) | Radio loss or latency; operator error; spoofing | OD-061 (HC-12 link not established) |
| R-F | Accept R-A deliberately, but raise a dedicated fault and make it very visible in telemetry | Still no parachute in the after-release case | Team acceptance of the residual risk |

These can be combined (for example R-B + R-D + R-F). [TBD] Team decision with safety approval.

**Tests:**
- `test/test_recovery_faults.cpp` separates **INVARIANT_** tests, which must hold under any approach, from **HAZARD_** tests, which pin current R-A behaviour and are to be updated deliberately when an approach is chosen.
- Invariants checked:
  - a corrupt record never resumes a state, restores one-shots or restores the ground reference;
  - structurally invalid records with a valid CRC are rejected;
  - a corrupt or absent record never causes a request on its own;
  - no recovery-fault scenario requests twice or while truly mounted;
  - the corrupt fault stays visible for the boot.

### I.3 OD-070: downstream deployment interlock (mock-only) [PROPOSED]

**Scope approved for software:**
- Isolated, mock-only implementation in `firmware/lib/core/DeploymentInterlock.*` and `ActuatorManager.*`, plus `lib/hal_mock/MockActuators.h`.
- **Not approved:** physical Step 4 integration, servo drivers, GPIO, wiring or actuator tests.

**Structure:**
- `ActuatorManager` is the only caller of `IActuatorDriver::apply()` (guard check).
- Two phases: `authorize()` runs the interlock and issues a single-use token. `execute()` **re-reads** arming and the connection assessment, runs the interlock **again**, and only then calls the driver.
- Tokens are invalid after a reset (boot count), after use, or once a newer token exists.
- A driver whose `isPhysical()` is true is refused and never called. The compile-time flag remains 0 and `#error`s when set.
- The state machine is unchanged. It still only emits requests, and entering PARACHUTE_DEPLOY never actuates (tested).

**Proposed gate rules** (all must pass; every failure is reported as a reason bit):
1. `FlightParams` complete **and** `DeploymentInterlockParams` complete.
2. The request has an interlock rule. Only ReleaseParachute does; panels and buzzers are refused (OD-037, OD-052).
3. State is PARACHUTE_DEPLOY, and the release one-shot is recorded.
4. Not already executed in this boot.
5. `min_separation_ms` has elapsed since the state machine's release-timer start, checked again independently.
6. Arming reads **Armed**. Unknown and Disarmed both block (source: OD-059).
7. Connection assessment reads **Separated**, is no older than `connection_max_age_ms`, and is not future-dated. Unavailable, Invalid, Indeterminate and Connected all block.

**Notes on these rules:**
- Rule 7 decides only *what the interlock does with* an assessment. **How** an assessment is established is not implemented and not assumed: switches, other indicators, ground confirmation, a lanyard or a hardware interlock (A1–A5) all remain open (OD-060, OD-068).
- Requiring a positive "Separated" follows the PDR interlock ("No parachute actuation while still mounted", slide 19). The trade-off (no parachute when no method can say "Separated") is the same OD-060 question and needs team approval.

**New parameter:**
- `DeploymentInterlockParams::connection_max_age_ms`. [TBD] No default; tests use a SYNTHETIC value.
- It is deliberately **not** part of `FlightParams::isComplete()`, so the detector and state-machine rules are unchanged.

**Information the interlock will eventually need from the hardware layer** (no pins and no placement assumed):
- **Per connection indicator, whatever it turns out to be:**
  - whether it is fitted (SW-Q1);
  - whether it can be read at all (bus or electrical validity);
  - its reading mapped to Connected / Separated / Unknown (needs SW-Q2, Q3 and Q5);
  - a timestamp;
  - a common-mode group, to tell whether two indicators can fail together (SW-Q4);
  - the result of a pre-flight two-way functional test.
- **How several indicators combine into one assessment.** This is OD-060 and must be decided by the team.
- **The arming source and procedure** (OD-059): physical arm input, ground command or pre-flight step. Also whether arming can be withdrawn in flight.
- **Actuator status:**
  - whether the actuator is busy or moving;
  - its motion time;
  - whether position feedback exists;
  - the state of the servo supply rail;
  - the state of the hardware-interlock read-back, if A5 is used.

  `BlockedBusy` exists but is not used, because no busy signal exists.
- **The reset cause** (brownout vs watchdog), to tell a servo-induced brownout apart (PR-1, PT-05).
- **A persistent "executed" record.** Today it is RAM-only (see the hazard below).

**Known hazard at the authorization/execution boundary** [DOC-CONFIRMED by `HAZARD_reset_between_authorization_and_execution_loses_the_actuation`, SIMULATED]:
- The state machine persists "chute requested" *before* queueing (to prevent duplicates). The manager's "executed" record lives only in RAM.
- So a reset after the request is persisted but before it executes means the request is **never executed in any boot**: after the reset it is suppressed as already requested.
- Fixing this requires recording execution persistently, which changes the recovery implementation. **Not approved; not changed.** [TBD]

**Tests:** `test/test_interlock.cpp`, 29 cases, mocks only:
- every gate on its own, and several failing together;
- evidence becoming Connected, Invalid, Unavailable, Indeterminate or stale between authorization and execution;
- disarming, and a state change, between the two phases;
- duplicate execution, superseded tokens, forged tokens, and tokens from before a reset;
- reset after execution;
- refusal of a driver that claims to be physical;
- integration with the unchanged state machine.

## J. Rev 6: switch to MicroPython (D-017)

- **OD-011 resolved** by D-017: the team switched to MicroPython. The approver names and date were not supplied ([TBD], see D-017).
- **C++ status:** `firmware/` is the reference implementation. It is not changed apart from two additive simulator outputs (a trace exporter and `comm_ok`/`data_ready` CSV columns) used for parity checks. It is archived, not deleted, once the port matches it on all 17 scenarios.
- **Weaker safety guards ([ASSUMPTION], stated plainly):** C++ refuses to *compile* with TBD pins or physical actuators enabled. Python cannot do that. The port uses (a) boot-time checks that refuse to run and (b) a scan script that fails the build. Both can be bypassed by editing or skipping them, and neither covers code paths the scan does not recognise.
- **OD-071 (new, [TBD]):** whether to enable the hardware watchdog `machine.WDT`, its timeout, and which loop feeds it. A watchdog reset during descent re-enters recovery (OD-069 hazards apply). Software does not enable it.
- **[UNVERIFIED]:** whether MicroPython `esp32.NVS` writes survive a brownout.
- **Paused:** C++ physical sensor drivers. The same reasoning carries over to register-level MicroPython drivers over `machine.I2C`.

## K. Rev 7: module 1 review answers (D-017)

**C++ preservation.** `firmware/` has no Git history (the enclosing repository is the home directory, and these files are untracked), so originals cannot be recovered from Git. The exact Rev 6 change set is saved as `docs/patches/rev6_cpp_sim_changes.diff`.
- It touches 8 files: 2 new (`sim/TraceExporter.h/.cpp`) and 6 modified (`sim/SimRunner.cpp`, `sim/FswHook.h`, `sim/sim_main.cpp`, `Makefile`, `test/test_step2_sim.cpp`, `README.md`). No `lib/core` or flight-logic file is touched.
- Reverse-applying it was dry-run checked. A scratch copy rebuilt from it compiles and passes with the pre-change counts, and its matrix output is identical.
- Nothing has been reverted. The options need approval.

**OD-072 (fault schema).**
- The port defines exactly the C++ FaultBit set (bits 0-18). Parity compares all 32 bits, unmasked.
- The recovery record does not store the fault mask; the CSV prints `0x%05X`.
- How an unhandled exception is reported is undecided. Options:
  - (a) append a new bit 19 to both C++ and Python;
  - (b) a separate status field, outside the fault mask;
  - (c) log only.
- Separately, the uint16 telemetry `fault` field is already too narrow for bits 16-18.

**OD-073 (buzzer pins).**
- The C++ `requiredHardwareResolved()` lists both buzzer pins, and the port copies it for parity.
- With no buzzer code (D-017) there is no safety reason. It blocks any hardware boot, including sensor bring-up, until OD-052 is decided.
- Its only benefit is that it forces the pins to be reserved before the GPIO plan is frozen.
- [RECOMMENDATION] Require buzzer pins only when buzzer code exists. That changes a hardware-interface rule and needs approval.

**OD-074 (.mpy).**
- Refusing `.mpy` keeps the boot scan meaningful, but gives up precompilation: less RAM for parsing, faster import.
- [RECOMMENDATION, not implemented] An integrity manifest:
  - on the laptop: run `scan_guards.py` on the `.py` sources, compile them with a pinned `mpy-cross`, and write a manifest of SHA-256 hashes of every `.mpy`;
  - at boot: hash each `.mpy` with `hashlib.sha256` and refuse any file that is not listed, or whose hash differs.
- This guards against stale or unscanned builds, not against deliberate tampering, because the manifest can be edited too.
- The `.mpy` version must match the firmware build.

**OD-075 (float boundary).** See `micropython/tools/float_margins.py`. These are [SIMULATED] margins with SYNTHETIC thresholds. The ESP32's own `pow` accuracy is [UNVERIFIED].

## Revision log
| Date | Change |
|---|---|
| 2026-11-18 | Created (Phase 1). |
| 2026-11-24 | Rev 14: [HW-OBSERVED, bench] Apps deployed (no autorun): FLIGHT on /dev/cu.usbserial-4, GROUND on /dev/cu.usbserial-0001, identified by MAC; on-board files hash-match the repo; all modules import on MicroPython v1.29.0. First ESP-NOW test, boards ~bench distance, ~3 min: ground accepted 707 frames, lost 1 (0.14 %), 0 duplicates, 0 rejected, 0 foreign, 707 ACKs sent; flight: 0 send failures, 1 missing ACK, 0 recoveries, RTT 28-41 ms, RSSI about -50 dBm. Flight diagnostic: I2C scan on SDA 21/SCL 22 found NO devices (also with SoftI2C at 100 kHz/10 kHz and SDA/SCL swapped); both lines read high as inputs. No sensor identified; OD-076 (GY-91 chip) still open. Two short bursts of corrupted bytes were seen on the FLIGHT board's USB serial output. SD not touched. |
| 2026-11-24 | Rev 13: MicroPython v1.29.0 (ESP32_GENERIC-20260824, SHA-256 e67ad601…bd95f6) flashed with user approval. FLIGHT 4c:c3:82:ec:c9:d8: 460800 baud, hash verified; boots, sys.platform=esp32, `import espnow` OK. GROUND 70:4b:ca:02:ce:30: two attempts aborted before erase (USB serial dropped out, then device absent); succeeded at 115200 baud on /dev/cu.usbserial-0001 after reconnection, hash verified; same checks pass. Both report espnow.MAX_DATA_LEN=1470 (protocol frames are 78/27 B). Records in `esp32/config/board_records.jsonl`. No applications deployed. |
| 2026-11-24 | Rev 12: board roles confirmed by the user: FLIGHT = /dev/cu.usbserial-0001, MAC 4c:c3:82:ec:c9:d8 (wired to the sensors); GROUND = /dev/cu.usbserial-5, MAC 70:4b:ca:02:ce:30. Re-verified with `esptool read-mac`; written to `esp32/config/radio_config.py`. Firmware `ESP32_GENERIC-20260824-v1.29.0.bin` SHA-256 e67ad601…bd95f6 is byte-identical to the file served by micropython.org. Nothing flashed. |
| 2026-11-24 | Rev 11: OD-079 protocol v1 provisionally approved for bench testing (team sign-off pending). Board identities read with `esptool read-mac` (read-only): /dev/cu.usbserial-0001 = ESP32-D0WD-V3 rev v3.1, MAC 4c:c3:82:ec:c9:d8; /dev/cu.usbserial-5 = ESP32-D0WD-V3 rev v3.1, MAC 70:4b:ca:02:ce:30. Roles not yet assigned; nothing flashed. |
| 2026-11-24 | Rev 10: radio switched to ESP-NOW by user direction (D-020); bring-up/telemetry software added under `esp32/` (D-021). Added OD-078 (ESP-NOW link performance unmeasured), OD-079 (telemetry schema v1, proposed), OD-080 (path to running the FSW on hardware; guards unchanged), OD-081 (IMU data-ready bit), OD-082 (barometer mapping). No flight logic, guard, pin in `hardware_config.py` or C++ file changed. Nothing is [HW-VERIFIED]. |
| 2026-11-19 | Rev 9: added OD-076 (GY-91 hardware switch; flight baseline unchanged) and OD-077 (user-reported bring-up pins, unverified). Bring-up diagnostic added under `bringup/`; nothing in the flight software changed. |
| 2026-11-19 | Rev 8: OD-073 resolved by D-018; OD-074 deferred; modules 1-2 accepted (D-019). OD-072 and OD-075 remain open. |
| 2026-11-18 | Rev 7: module 1 review answers; added OD-072..OD-075 and §K. Nothing reverted; no pins assigned. |
| 2026-11-18 | Rev 6: OD-011 resolved by D-017 (switch to MicroPython; approvers/date not supplied). Added OD-071 (hardware watchdog, undecided) and §J. |
| 2026-11-18 | Rev 5: added OD-068 (switch questions SW-Q1…Q5, all unresolved), OD-069 (corrupt/absent record recovery analysis, R-A…R-F, none selected) and OD-070 (mock-only downstream interlock, proposed gate rules, hardware-layer information list, authorization/execution reset hazard). §I added. OD-060 still undecided; A1–A5 all remain candidates; no policy, threshold, GPIO or actuator enabled. |
| 2026-11-18 | Rev 4 (Step 3 review): false LANDED root-caused and corrected (OD-065); timeouts no longer cause transitions (OD-064 items 3–5); sensor-health evidence documented (OD-066); persistence-failure policy made explicit (OD-067); §H.6 independent-evidence options. OD-060 still undecided; no policy enabled. |
| 2026-11-18 | Rev 3 (Phase 2 step 3): added §H.4a simulated policy comparison and OD-064 provisional state-machine behaviours. No decision taken. |
| 2026-11-18 | Rev 2, after review: §C expanded with the full read-only Git inspection and repository options (none executed). Added OD-060 (stuck-switch decision, §H), OD-061 (HC-12 feasibility not established), OD-062 (shock measurement separated from free-fall detection) and OD-063 (power not finalised). No existing decision or hardware configuration was changed. |
