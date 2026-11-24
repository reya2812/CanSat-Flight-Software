# Phase 1 Proposal: Feasibility, Release Detection, Architecture, Telemetry, Acceptance Demo

**Status:** PROPOSAL awaiting the software lead's approval (2026-11-18). No code has been written. Nothing has been installed or flashed.
**Companion files:** `OPEN_DECISIONS.md` (conflicts), `MEETING_BRIEF.md` (questions), `TRACEABILITY.md` (requirements).
**Label key:** [PDR] · [DOC-CONFIRMED] · [HW-VERIFIED] · [TEAM DECISION] · [UNVERIFIED] · [RECOMMENDATION] · [ASSUMPTION] · [SIMULATED] · [TBD]

**Rev 2 (2026-11-18, after the software lead's review):**
- §2.1: the HC-12 link is marked **not established**, with calculated and tested results separated and an RF test plan added.
- §2.2: free-fall detection and opening-shock measurement are split into two separate requirements.
- §2.3–2.4a: power is marked **not finalised**, with a risk list and a test list added.
- §3.2 and §6: the stuck-switch policy is now an undecided team decision (OD-060) with no default.

No existing decision or hardware configuration was changed.

> **About datasheet figures in this file.** No component datasheets are stored in `references/`, and none were read in this session. Figures quoted as "datasheet (recalled)" come from the manufacturer documents as I remember them. They are labelled [ASSUMPTION] until someone adds the PDF to `references/` and checks the number. Only then do they become [DOC-CONFIRMED]. "Typical" means commonly measured hobby-module behaviour and is not guaranteed by any datasheet.

---

## 1. Existing repository structure (as inspected)

- [DOC-CONFIRMED] Git root is `/Users/reya` (home directory). The project folder is untracked, and that repository has no commits (OD-002).
- [DOC-CONFIRMED] The project contains documentation only, with no source code:

```
CanSat-Flight-Software/
├── CLAUDE.md, README.md, .gitignore
├── docs/01–09_*.md         project overview, requirements (SW-01..13), hardware spec, architecture draft,
│                           state-machine draft, telemetry draft, safety, test plan, open questions
├── docs/decisions/         DECISIONS.md (D-001..D-012), README.md
├── hardware/pinout.md      all TBD (still headed "ESP32-S3")
├── references/             CanSat_PDR.pdf (24 slides), components_invoice_photo.png
├── demo/                   experiment_log.md, agent_results.md (templates, empty)
└── docs/OPEN_DECISIONS.md, MEETING_BRIEF.md, TRACEABILITY.md, PHASE1_PROPOSAL.md   ← created in Phase 1
```
- [DOC-CONFIRMED] `README.md` lists `src/`, `tests/`, `simulator/` and `data/`. None of them exist.
- [DOC-CONFIRMED] `PlatformIO`, `arduino-cli`, `cmake`, `pytest` and `pyserial` are not installed. `g++`/`clang++` (Apple) and Python 3.14.2 are available.

---

## 2. Feasibility review: findings only, nothing is fixed here

### 2.1 HC-12 throughput vs the 4 Hz CSV packet

Three different rates are involved, and they are easy to confuse:

| Quantity | What it is | Set by |
|---|---|---|
| UART baud | Wire speed between the ESP32 and the HC-12 (bits/s, 8N1 = **10 bits per byte**) | HC-12 `AT+Bxxxx`; must match the ESP32 `Serial2.begin()` on both ends |
| Air data rate | RF bit rate between the two HC-12s | [ASSUMPTION, datasheet recalled] In FU3 mode it is chosen automatically from the UART baud |
| Application throughput | Telemetry bytes per second the software actually needs | Packet length × packet rate |

**Sources:** [PDR] 4 Hz (slides 6, 17, 19, 20). [ASSUMPTION, HC-12 manual recalled] Factory default is FU3, 9600 baud, channel 001, 20 dBm. In FU3 the UART→air mapping is 1200/2400 → 5 kbps, 4800/9600 → 15 kbps, 19200/38400 → 58 kbps, 57600/115200 → 236 kbps. FU4 (long range) allows only 1200 baud, small packets and seconds between packets, so it cannot carry 4 Hz. Higher air rates have lower receiver sensitivity, so they reach a shorter range.

**Packet size:**
- [PDR] The slide 17 example string is 73 characters, or 75 with CR/LF.
- [ASSUMPTION] The proposed v1 frame (§5) is computed by script: typical **72 B**, worst case with every field at maximum width **123 B**.

**Formula:** UART utilisation = L × 10 bit × 4 Hz ÷ baud. The largest packet that fits at 4 Hz is baud ÷ 10 ÷ 4.

| UART baud | Max bytes/packet at 4 Hz (100 % load) | Utilisation, L = 72 B | Utilisation, L = 123 B | FU3 air rate (recalled) |
|---:|---:|---:|---:|---:|
| 1200 | 30 | 240 % ✗ | 410 % ✗ | 5 kbps |
| 2400 | 60 | 120 % ✗ | 205 % ✗ | 5 kbps |
| 4800 | 120 | 60 % | 103 % ✗ | 15 kbps |
| 9600 | 240 | 30 % | 51 % | 15 kbps |
| 19200 | 480 | 15 % | 26 % | 58 kbps |

> **Feasibility status of the HC-12 link: NOT ESTABLISHED.** [TBD]
> The table above checks only one thing: whether the **UART wire** between the ESP32 and the HC-12 can carry the bytes. It says nothing about whether the **radio link** delivers them reliably. The link must not be called feasible until the RF test plan below has been run and its results reviewed.

**What has been calculated vs what has been tested:**

| Question | Calculated (theory) | Tested |
|---|---|---|
| Can the ESP32 → HC-12 UART carry 72–123 B at 4 Hz? | [ASSUMPTION] Yes at 9600 baud (30–51 % load); marginal at 4800; no at 1200/2400 | **Nothing tested** |
| Air-side throughput, including HC-12 framing and preamble overhead | [TBD] The HC-12 does not document its internal air-frame overhead (in anything I have read) | **Nothing tested** |
| End-to-end latency, from the ESP32 write to the ground-station USB line | [TBD] The module buffers bytes and transmits after an internal timeout. The delay is not quantified here | **Nothing tested** |
| Half-duplex behaviour | [ASSUMPTION] The HC-12 is half-duplex, so any future uplink competes with the downlink | **Nothing tested** |
| Packet loss and corruption at range | [TBD] Cannot be calculated meaningfully without a link budget and a measured environment | **Nothing tested** |
| Range ≥150 m ([PDR] slide 16) at the chosen air rate | [ASSUMPTION] Range falls as air rate rises. Vendor range claims are for ideal open air | **Nothing tested** |
| Interference | [ASSUMPTION] 433 MHz is a shared band. Other teams' HC-12s on the same channel would be received as garbage or as foreign valid-looking lines | **Nothing tested** |
| Effect of the CanSat body, antenna orientation, drone EMI and ground proximity after landing | [TBD] | **Nothing tested** |
| Effect of a sagging supply rail during TX bursts or servo moves | [ASSUMPTION] Supply droop is a known cause of HC-12 resets and garbled bytes; decoupling and the rail design matter | **Nothing tested** |

**What the calculation does show:**
- [ASSUMPTION] Low UART bauds (1200/2400) **rule out** 4 Hz at the proposed packet size. That is a "no", and it holds without any test.
- [ASSUMPTION] Higher bauds are only a **necessary** condition, not a sufficient one.
- [ASSUMPTION] There is a trade-off between range and rate. The longest-range settings are exactly the ones that cannot carry the 4 Hz packet.
- [RECOMMENDATION] If range forces a lower baud, shorten the packet (fewer fields per frame, or binary). Do not drop the rate silently, because that would change a PDR requirement.

**Proposed RF test plan** ([RECOMMENDATION]; owner [TBD], probably Mukund with Shikhraj; all tests [TBD], none run). Every test uses the v1 frame with `pkt` sequence numbers and CRC, so loss, corruption and gaps are counted by the ground-station tool rather than judged by eye.

| Test | Setup | What it measures | Pass criterion |
|---|---|---|---|
| RF-01 Bench link, wired antennas ~1 m apart | Both HC-12s set to the chosen mode, baud and channel; read back with AT commands and record | Baseline: sustained 4 Hz for ≥30 min. Lost, corrupted, duplicate, gap > 1.0 s counts. End-to-end latency, by timestamping on the flight side and comparing with the GS receive time | [TBD] The team sets the acceptable loss. [PDR] slide 20 says "100% packet reception at 4 Hz; no link gaps > 1.0s". 100 % over RF may be unrealistic, so the team should confirm whether that is the real criterion. |
| RF-02 Rate and size margin | Same setup, stepping packet size and rate upward | Where the link starts losing packets. This gives the real margin instead of the theoretical 2× | Record only |
| RF-03 Supply stress | Flight power rail, with simulated load steps (no deployment servos attached) | Whether TX bursts or load steps cause resets or garbled bytes | Zero module resets |
| RF-04 Range, line of sight | Flight antenna mounted in the real structure; 50 / 100 / 150 / 200 m; several orientations | Loss and gap counts against distance and orientation | ≥150 m at the agreed criterion ([PDR] slide 16) |
| RF-05 Interference | A third HC-12 transmitting on the same channel, then on an adjacent channel | Does the GS reject foreign frames (CRC, team ID)? Does our loss rise? | No foreign frame accepted as ours |
| RF-06 On the drone | CanSat mounted, drone motors running, at height | Drone EMI, height and geometry | As RF-01 |
| RF-07 Drop and landing | Logged during a dummy drop | Link during motion, and after landing on the ground | Gap pattern recorded. Post-landing reception [TBD] |

The link may be labelled feasible only after RF-01, RF-04 and RF-06 pass at the chosen settings. Even then it is [HW-VERIFIED] only for those settings and that antenna installation.

### 2.2 MPU6050: two separate requirements, kept apart

**Sources:**
- [PDR] "Kevlar shroud lines anchored via a heavy-duty eye-bolt with fender washers to withstand the 30G deployment shock" (slide 10). This is a **structural design load** for the attachment. It is not a measured value, and it is not stated as something to be measured.
- [ASSUMPTION, datasheet recalled] MPU-6050 accelerometer full scale is selectable at ±2, ±4, ±8 or ±16 g per axis (2048 LSB/g at ±16 g). Its shock-survival rating is far above 30 g, so surviving the shock is not the issue; measuring it is.

#### Requirement A: detect release and free fall (needed for the minimum viable software)

| Aspect | Finding |
|---|---|
| Is there a PDR requirement? | [PDR] Yes: "Mount switch opens + GY-91 acceleration change" (slide 19), with the GY-91 now replaced by the MPU6050 [UNVERIFIED] |
| Signal level | [ASSUMPTION] Free fall ≈ 0 g; mounted or descending ≈ 1 g. Both sit far inside even the ±2 g range |
| Is the range adequate? | [ASSUMPTION] On range alone, yes. The ±16 g setting is not required for this; a lower range gives finer resolution |
| What is still unknown | [TBD] Noise and drone vibration while mounted, the sample rate needed, and a fault mode where a failed I2C read returns zeros that *look like* free fall (§3.2). These need test data (§3.3) |
| Status | Range plausibly adequate on paper. **Detection performance is not established.** |

#### Requirement B: measure the parachute-opening shock (not part of the minimum viable software)

| Aspect | Finding |
|---|---|
| Is there a PDR requirement to *measure* it? | [TBD] I found none. The PDR states 30 g as a design load for the eye-bolt (slide 10). Whether the team wants a measured peak (for example to verify that load) is a team decision (OD-062) |
| Can the MPU6050 measure it? | [ASSUMPTION] **Not if the peak exceeds 16 g on any axis.** That axis clips at ±16 g and the true peak is lost; a magnitude computed from clipped axes is also invalid. Clipped data shows only that "the peak was at least 16 g on that axis" |
| Sampling | [ASSUMPTION] An opening shock probably lasts tens of milliseconds. At the PDR's 4 Hz polling (250 ms between samples) it would most likely be missed entirely, whatever the range. Capturing its shape would need a burst mode sampling at around 1 kHz or more [ASSUMPTION] with buffered logging, even within ±16 g |
| Additional hardware needed? | **Only if the team decides the peak must be measured.** In that case: [RECOMMENDATION, for discussion only] a high-g accelerometer such as ADXL375 (±200 g), H3LIS331DL (±100/200/400 g) or ADXL377 (analog ±200 g), sampled at a high rate. That is a hardware change (mass, a pin or I2C/SPI slot, a driver) and is Mukund's call, not software's |
| Non-electronic alternatives | [RECOMMENDATION, for discussion] For verifying the eye-bolt and shroud attachment, a ground test with a load cell or spring scale on the tether, or a drop test with a known mass, measures the load on the structure more directly than an onboard accelerometer |
| Software behaviour regardless | [RECOMMENDATION] Use the MPU6050 for Requirement A only. Flag saturated samples. Never report a clipped value as a measured peak. |

> **Power architecture status (§2.3–2.4): NOT FINALISED.** [TBD]
> Nothing below is a power-management decision. The following are all unconfirmed:
> - the battery configuration (two independent 1S cells? parallel? separate subsystems?)
> - how each TP4056 board is wired (OUT± vs B±, which cell)
> - which MT3608 feeds which load
> - where the INA219 sits
> - whether the converters can carry the real loads
>
> The calculations here only identify **risks** and the **tests needed**. Owners: Mukund and Krish (OD-053, OD-063).

### 2.3 MT3608 vs three SG90 servos

**Sources:**
- [ASSUMPTION, SG90 datasheet recalled] The TowerPro sheet gives 4.8 V operation, 1.8 kg·cm stall torque and 0.1 s/60°. It gives **no current figure**.
- [ASSUMPTION, typical] Hobby measurements: idle ≈ 10 mA, moving ≈ 100–300 mA, stall ≈ 550–800 mA at 5 V. A stall-level inrush can occur when power is first applied.
- [ASSUMPTION, MT3608 datasheet recalled] 4 A switch-current limit (typical) and 2–24 V input.
- [DOC-CONFIRMED] The invoice listing says "MT3608 … 2A". That is the seller's claim.

**Formula:** input current I_in = V_out × I_out ÷ (V_in × η). Peak switch current ≈ I_in + half the inductor ripple.

**Assumptions:** [ASSUMPTION] V_out = 5.0 V, η = 0.85, V_in = 3.3 V (low cell), 3.7 V (nominal) or 4.2 V (full). Stall = 0.75 A per servo.

| Case | P_out | I_in at 3.3 V | I_in at 3.7 V | I_in at 4.2 V |
|---|---:|---:|---:|---:|
| 1 servo stalled (0.75 A) | 3.75 W | 1.34 A | 1.19 A | 1.05 A |
| 3 servos moving, no load (3 × 0.25 A) | 3.75 W | 1.34 A | 1.19 A | 1.05 A |
| 3 servos stalled or at power-up inrush (2.25 A) | 11.25 W | **4.01 A** | **3.58 A** | 3.15 A |

**Findings:**
- [ASSUMPTION] Three servos stalled at once on one MT3608 from a 1S cell need about 3.2–4.0 A of average input current. That is at or beyond the converter's switch limit before ripple is added. It is also around the over-current trip level of a typical DW01 + 8205A protection board (150 mV across roughly 40–60 mΩ ≈ 2.5–3.8 A). The likely outcomes are rail sag, the protection board cutting the cell, and an ESP32 brownout if the logic shares that rail.
- [ASSUMPTION] One servo at a time is plausible on paper.
- [TBD] The rail has to be measured under real servo load (`docs/09` P2). It depends on the power topology (OD-053).
- [RECOMMENDATION] Have the software enforce **one actuator move at a time**. That costs nothing in code and is built into the ActuatorManager design (§4).

### 2.4 Do the TP4056 boards have over-discharge protection?

- [DOC-CONFIRMED] The invoice line reads "TP4056 1A Li-ion Lithium Battery Charging Module **with Current Protection** – Type C".
- [ASSUMPTION, typical] Boards sold this way usually carry a DW01A protection IC and an FS8205A dual MOSFET. They have separate B+/B− (cell) and OUT+/OUT− (load) pads.
- [ASSUMPTION, DW01A datasheet recalled] Over-discharge detection at about 2.4 V, release at about 3.0 V, overcharge detection at about 4.3 V, over-current at 150 mV.
- **Answer:** probably yes, but:
  - [ASSUMPTION] It protects only if the load is wired to **OUT±**, not B±.
  - [ASSUMPTION] About 2.4 V is a deep cut-off. The MT3608 keeps running down to 2 V, so the cell can be drained well below a healthy level before anything stops.
  - [ASSUMPTION] The TP4056 has no power-path circuit, so charging while the load is connected can upset charge termination.
  - [TBD] Check physically for a 6-pin DW01 and an 8-pin 8205A on each board.
- **Software consequence:** [RECOMMENDATION] Report battery voltage in telemetry and raise a low-battery fault flag. The threshold is [TBD] and is not chosen here.

### 2.4a Power risks and the tests needed (no decisions)

**Risks** (all [ASSUMPTION], derived from the calculations above; none measured):

| # | Risk | Depends on (unconfirmed) |
|---|---|---|
| PR-1 | Several servos moving or stalling together exceed what one MT3608 or one protected cell can supply. The rail sags, protection trips, or the ESP32 browns out | Which loads share a converter and a cell |
| PR-2 | Servo power-up inrush (all servos twitch at once when the rail turns on) causes the same sag, and can move a mechanism unexpectedly | Rail switching order; servo signal state at boot |
| PR-3 | HC-12 TX bursts on a weak or shared rail cause radio resets or corrupted bytes | Which rail powers the HC-12; decoupling |
| PR-4 | A load is wired to the TP4056 B± pads instead of OUT±, bypassing over-discharge protection | Board wiring |
| PR-5 | The deep DW01 cut-off (~2.4 V) lets a cell be over-drained, because the MT3608 keeps running below a healthy cell voltage | Board variant; monitoring |
| PR-6 | Paralleling the two TP4056 outputs or the two cells directly makes them cross-charge or fight each other (already warned in `docs/03` §4) | Topology |
| PR-7 | Charging while the load is connected confuses TP4056 charge termination (no power path) | Charging procedure |
| PR-8 | The single INA219 measures only one rail, so faults on other rails are invisible to software | INA219 placement |
| PR-9 | MT3608 heating at high current inside a closed PETG body | Real loads; enclosure |

**Tests needed** ([RECOMMENDATION]; none run). Run them on a current-limited bench supply first, then on the cells, supervised, with no deployment mechanism attached to any servo.

| Test | Measures | Closes |
|---|---|---|
| PT-01 Board identification | Photograph each TP4056 and MT3608 board; confirm the DW01 and 8205A chips and the OUT± pads | PR-4, PR-5 board variant |
| PT-02 Drawn power tree, reviewed | Which cell → which charger → which switch → which converter → which loads; where the common ground is; where the INA219 sits | PR-6, PR-8; OD-053 |
| PT-03 MT3608 set-up | Output voltage at no load, set and recorded for each module | Baseline |
| PT-04 Single-servo load | Rail voltage (min, ripple) and input current with one SG90 moving and then held at stall, briefly | PR-1 (one servo) |
| PT-05 Multi-servo and inrush | Same with all servos moving together, and at power-on | PR-1, PR-2 |
| PT-06 Combined load | ESP32 + sensors + SD write + HC-12 TX + a servo move on the intended rails; ESP32 reset and brownout events logged | PR-1, PR-3 |
| PT-07 Protection behaviour | Over-current and under-voltage cut-off, tested with a bench supply in place of the cell where possible | PR-4, PR-5 |
| PT-08 Thermal | Converter temperature during a mission-length run inside the structure | PR-9 |
| PT-09 Endurance | Powered time from power-on through landing and recovery (not only the 28 s descent) | OD-044 |

### 2.5 ESP32 pins and peripherals

**Sources:** [ASSUMPTION, Espressif ESP32 datasheet / TRM recalled; boot-glitch list from common community pin guides, not official]

| Constraint | Pins | Why it matters here |
|---|---|---|
| Strapping pins | GPIO0, 2, 5, 12, 15 | Their level at reset selects the boot mode. **GPIO12 pulled high selects 1.8 V flash, and the ESP32 DevKit then fails to boot.** Never connect a pull-up device (such as a switch with a pull-up) to GPIO12. |
| Input-only, no internal pull-ups | GPIO34, 35, 36, 39 | Good for limit switches and UART RX/MISO, but **external pull-up resistors are required**. The resistor kit is not on the invoice (OD-040). |
| Flash pins | GPIO6–11 | Never use them. They are usually not broken out on 30-pin boards. |
| UART0 | GPIO1 (TX), 3 (RX) | Wired to the CP2102 USB bridge for programming and debug, so do not use them for the HC-12. The ESP32 has UART1 and UART2 available. |
| ADC2 | GPIO0, 2, 4, 12–15, 25–27 | Unusable while Wi-Fi is on. The HC-12 baseline does not use Wi-Fi, but [RECOMMENDATION] any analog input (battery or solar divider) should use ADC1 (GPIO32–39) anyway. |
| Boot-time output glitches | GPIO1, 3, 5, 14, 15 | They toggle or emit PWM during boot. **A servo or buzzer on these pins could twitch or beep at power-up.** That is a safety issue for any deployment servo. |
| Peripheral routing | — | The GPIO matrix can route I2C, SPI, UART and LEDC (servo PWM) to most pins, so the pin choice is constrained by the rows above, not by the peripherals. |

**Signal count needed:**
- [UNVERIFIED baseline] Outputs or bidirectional: I2C ×2, HC-12 TX + SET ×2, SD SCK/MOSI/CS ×3, servos ×3, buzzers ×2 = **12**.
- Inputs: HC-12 RX, SD MISO, switches ×2 = **4**.

**Pins likely available:**
- [ASSUMPTION] A typical 30-pin DevKit exposes about 25 GPIOs. That needs checking on the actual board's silkscreen.
- Leaving out UART0, the strapping pins and the glitching pins leaves roughly **14 "clean" bidirectional pins** (4, 13, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33) plus **4 input-only pins** (34, 35, 36, 39).

**Finding:**
- [ASSUMPTION] The baseline fits, with about 2 clean pins to spare. That is feasible but tight. Adding a second INA219 costs no pins (it shares I2C). An ADC divider costs one ADC1 pin.
- **No pin assignment is proposed here.** [TBD] The allocation belongs to OD-054 and needs the real board in hand.

### 2.6 Mass and volume (detail for OD-018)

**Sources:**
- [PDR] Total 428 g, ceiling 500 g, battery 32 g (9 V) (slide 14).
- [UNVERIFIED] 18650 cells about 45 g each (`docs/03`). SG90 9 g each (`docs/03`, invoice).

**Delta known so far:**
- [ASSUMPTION] Battery: 2 × 45 − 32 = **+58 g**. That uses 58 of the 72 g margin, or 81 %.

**Masses not yet known:**
- [TBD] 2 holders, 2 × TP4056, 3 × MT3608 (or however many are flown), HC-12 module + spring antenna, SD module + card, 2 buzzers, 2 limit switches, and a possible third onboard servo.
- [TBD] The 30-pin DevKit may differ from the PDR's 12 g ESP32 allowance.
- [TBD] All of these must be **weighed**.

**Descent sensitivity:**
- [ASSUMPTION] From the PDR equation (slide 10), v ∝ √m. With the same canopy, 550 g gives v ≈ 3.0 × √(550/500) ≈ 3.15 m/s.

**Volume:**
- [ASSUMPTION, standard 18650 size] Each cell is about 18 × 65 mm before the holder.
- [ASSUMPTION, typical] A 30-pin DevKit is about 50 × 28 mm.
- [PDR] The body is 50 × 50 × 100 mm external, and the parachute bay sits at the top (slide 13).
- [TBD] Wall thickness and internal volume are not given. A CAD fit check is needed (Aditya or Haridas).

---

## 3. Release-detection analysis (parameterised; no values chosen)

### 3.1 What each signal is expected to show

These are [ASSUMPTION] physics expectations, not measured data.

| Phase | Mount switch(es) | Accel magnitude \|a\| | Baro altitude | Notes |
|---|---|---|---|---|
| On ground / mounted, motors off | Closed (if wired that way) | ≈ 1 g | Constant ± noise | Defines the ground reference. |
| Mounted, hovering or ascending | Closed | ≈ 1 g + drone vibration | Rising | Prop wash may bias the pressure reading under the drone. |
| Release instant | Opens (may bounce) | Short jolt possible | — | Switch bounce typically lasts milliseconds. |
| Free fall, before the chute | Open | **Drops toward ≈ 0 g**. As drag builds, it climbs back toward 1 g. | Falling, speeding up | An accelerometer measures *specific force*. In free fall that is about zero on all axes. **It is not a spike.** |
| Chute opening | Open | Spike, possibly saturating at ±16 g per axis | Rate drops to about descent speed | May be missed at a 4 Hz sample rate (§2.2). |
| Descent under chute | Open | ≈ 1 g + swing | Falling at about [PDR] 3 m/s | |
| Landing | Open | Impact spike, then steady ≈ 1 g and gyro ≈ 0 | Constant | |

### 3.2 Parameterised logic

All parameters are [TBD]. The firmware will have **no default values** for them.

```
Parameters (all TBD, set only from test data and team approval):
  T_DB_SW        switch debounce time           SW_POLARITY[k]   open = HIGH or LOW per switch
  SW_VOTE        ANY | ALL | SW1_ONLY            (depends on OD-015: role of 2nd switch)
  A_FF           free-fall |a| threshold (g)    T_FF             min duration below A_FF
  DH_MIN, W_B    min altitude loss over baro window W_B (or V_DESC = min descent rate)
  T_CONFIRM      window in which corroboration must follow the switch event
  T_SEP_MIN      min time after confirmed release before a parachute request is allowed
                 ("deploy after safe distance from the drone" [PDR] slide 10)
  T_STALE        sample age after which a sensor is treated as unavailable
  ARM_COND       what arms release logic (state == ASCENT? altitude gain? GS command?)  (OD-057)

Derived signals (only VALID, non-stale samples count):
  mount_open  = SW_VOTE( debounce(raw_k XOR SW_POLARITY[k], T_DB_SW) )
  freefall    = |a| < A_FF continuously for ≥ T_FF
  baro_desc   = h(t − W_B) − h(t) ≥ DH_MIN       (or slope ≤ −V_DESC)

Events:
  RELEASE_CANDIDATE        armed AND mount_open (rising edge)
  RELEASE_CONFIRMED        RELEASE_CANDIDATE AND (freefall OR baro_desc) within T_CONFIRM
  RELEASE_UNCORROBORATED   RELEASE_CANDIDATE AND neither within T_CONFIRM  → log + flag; policy TBD
  SWITCH_REVERTED          mount_open returns false before confirmation → cancel candidate, flag
  RELEASE_SENSORS_ONLY     armed AND freefall AND baro_desc AND NOT mount_open (switch stuck closed?)
                           → always flagged DEGRADED and logged. What happens next is set by
                             STUCK_SWITCH_POLICY, which is an UNDECIDED SAFETY DECISION (OD-060).
                             The firmware has NO default policy.

Parachute-request interlock (evaluated by ActuatorManager, not the state machine):
  allow = release_basis_ok(STUCK_SWITCH_POLICY)          ← OD-060, team decision
          AND (t − t_release ≥ T_SEP_MIN)
          AND armed_flag AND build_enables_physical      (compile-time false in Phases 1–2)
  where, for the strict option, release_basis_ok = RELEASE_CONFIRMED latched AND mount_open.
  The other candidate options are listed in OPEN_DECISIONS.md §H. In simulation each option
  is run side by side; none is promoted to a default.
```

- [ASSUMPTION] **Timeline caution, which applies to every option.** Ignoring drag (worst case), a body dropped from 100 m reaches the ground in √(2 × 100 / 9.81) ≈ 4.5 s. It falls 4.9 m in the first 1 s, 19.6 m by 2 s and 44 m by 3 s. Drag lengthens these times, but by an unknown amount until drop data exists. Every corroboration window, T_SEP_MIN, latch actuation time and the [PDR] "~2 s" opening time must fit inside that budget. A cautious detector that waits "to be sure" can end up being, in effect, no parachute.

- [RECOMMENDATION] Require the switch **and** at least one independent physical sign (free fall or barometric descent). One noisy sample of any single sensor must never be enough (`docs/05`).
- [RECOMMENDATION] Sample the IMU and barometer internally faster than 4 Hz, so that free fall and debounce can be judged reliably. The 4 Hz figure would remain the telemetry rate. This is [TBD] (OD-042).

### 3.3 Test data needed to choose the parameters

1. Switch bounce traces at release (high-rate GPIO capture or a logic analyser), repeated many times. This sets T_DB_SW.
2. IMU + barometer logs while mounted on the drone: motors off, hover, ascent and hold at altitude. This gives the vibration level, the |a| distribution, baro noise and the prop-wash bias, and it sets margins against false triggers.
3. Tethered-release and dummy-drop logs with an independent release-time reference (for example, video synced to the log). These give the free-fall |a| minimum and how long |a| stays below each candidate A_FF. They set A_FF, T_FF and T_CONFIRM.
4. Barometer at rest over several minutes and across temperature, to measure noise and drift. This sets DH_MIN and W_B.
5. Parachute-opening and landing traces, including saturation behaviour.
6. ESP32 reset-to-first-valid-sample time, needed for reset recovery during flight.
7. False-trigger tests: handling, transport, mounting, bumps and hand-carrying while powered.
8. Time from drone release until the CanSat is clear of the drone, needed for T_SEP_MIN. Haridas and Shikhraj would supply this.

---

## 4. Firmware architecture

### 4.1 Principles

1. **Pure logic stays separate from hardware.** All flight logic is plain C++17 with no `Arduino.h`, so it compiles and runs on a laptop. Only thin drivers touch hardware.
2. **States, events and commands are different things.**
   - *State* is where the mission is.
   - An *event* is something detected.
   - A *command request* is something the state machine would like done.
   - The **ActuatorManager** alone decides whether a request is executed, blocked or simulated.
3. **Physical actuation is disabled at compile time.** No physical servo driver is written in Phase 2. The hardware build fails if required pins or parameters are still TBD.
4. **One cooperative loop at a fixed tick** (no FreeRTOS tasks at first). Beginners can reason about it easily, and it gives deterministic tests. [ASSUMPTION] SD writes can occasionally block for tens to hundreds of milliseconds, so logging goes through a buffer. A separate task can come later if measurements show it is needed.

### 4.2 Data flow

```
             ┌──────────── HAL interfaces (real ESP32 drivers  OR  mocks/replay) ───────────┐
             │ IClock  IBarometer  IImu  IPowerMonitor  IDigitalInputs  ISerialLink  ILogSink │
             │ IPersistentStore   IActuatorDriver (mock-only in Phase 2)  IBuzzer (mock-only)  │
             └───────────────────────────────────────────────────────────────────────────────┘
                 │ samples                                    ▲ bytes / lines / records
                 ▼                                            │
          SensorManager ──SensorFrame (validity, age, saturation)──┐
                 │                                                 │
                 ├──► PowerMonitor ──► power faults                │
                 ▼                                                 │
          ReleaseDetector ──Events──► FlightStateManager ──State + ActuatorRequests
                                            │       ▲                       │
                                            │       │ restored record       ▼
                                            │   RecoveryManager ◄─── ActuatorManager ──► IActuatorDriver (mock)
                                            │   (NVS one-shot flags)   │ interlock + arming + build flag
                                            ▼                          ▼ ActuatorDecision events
                                    Diagnostics (fault flags, counters)
                                            │
                          ┌─────────────────┴───────────────┐
                          ▼                                 ▼
                 TelemetryManager ──frame──► ISerialLink   DataLogger ──CSV──► ILogSink (SD / laptop file)
```

### 4.3 Modules and their interfaces (sketch, to be refined in Phase 2 step 1)

```cpp
// ---- common types (lib/core/Types.h) ----
enum class FlightState : uint8_t { PowerOnSelfCheck=1, ReadyOnDrone, Ascent, ReleaseDetected,
                                   ParachuteDeploy, PanelDeploy, Descent, Landed };   // [PDR] slide 19
struct BaroSample  { uint32_t t_ms; float pressure_pa, temp_c; bool valid; };
struct ImuSample   { uint32_t t_ms; float ax_g, ay_g, az_g, gx_dps, gy_dps, gz_dps; bool valid, saturated; };
struct PowerSample { uint32_t t_ms; float bus_v, current_ma; bool valid; };
struct SwitchSample{ uint32_t t_ms; bool raw[2]; bool valid; };
struct SensorFrame { BaroSample baro; ImuSample imu; PowerSample pwr; SwitchSample sw; };

enum class EventType : uint8_t { SelfCheckPass, SelfCheckFail, AscentDetected, ReleaseCandidate,
      ReleaseConfirmed, ReleaseUncorroborated, ReleaseSensorsOnly, SwitchReverted, ChuteOpenDetected,
      PanelsOutDetected, TouchdownDetected, SensorFault, ResetRecovered };
enum class ActuatorRequest : uint8_t { ReleaseParachute, DeployPanels /*only if a servo exists*/,
                                       BuzzerOn, BuzzerOff };
enum class ActuatorDecision : uint8_t { ExecutedSimulated, BlockedBuildDisabled, BlockedNotArmed,
                                        BlockedInterlockMounted, BlockedAlreadyDone, BlockedBusy };

// ---- HAL (lib/hal/*.h) ----
struct IClock         { virtual uint32_t nowMs() = 0; };
struct IBarometer     { virtual BaroSample read() = 0; };
struct IImu           { virtual ImuSample read() = 0; };
struct IPowerMonitor  { virtual PowerSample read() = 0; };
struct IDigitalInputs { virtual SwitchSample read() = 0; };
struct ISerialLink    { virtual size_t write(const uint8_t*, size_t) = 0; virtual int read() = 0; };
struct ILogSink       { virtual bool append(const char* line) = 0; virtual bool flush() = 0; };
struct IPersistentStore { virtual bool load(RecoveryRecord&) = 0; virtual bool save(const RecoveryRecord&) = 0; };
struct IActuatorDriver  { virtual void apply(ActuatorRequest) = 0; };   // mock-only in Phase 2

// ---- modules (lib/core) ----
class SensorManager      { SensorFrame poll(); };                      // validity, staleness, saturation
class ReleaseDetector    { explicit ReleaseDetector(const ReleaseParams&);   // no defaults
                           void update(const SensorFrame&, FlightState, EventSink&); };
class FlightStateManager { void onEvent(const Event&); FlightState state() const;
                           // emits ActuatorRequest into a queue; never calls drivers
                           bool popRequest(ActuatorRequest&); };
class ActuatorManager    { ActuatorDecision handle(ActuatorRequest, const InterlockInputs&); };
class RecoveryManager    { RestoreResult restoreOnBoot(const SwitchSample&); void persist(...); };
class TelemetryManager   { size_t buildFrame(const Snapshot&, char* out, size_t cap); };  // §5
class DataLogger         { void log(const Snapshot&); void logEvent(const Event&); };
class PowerMonitor       { void update(const PowerSample&, Diagnostics&); };
class Diagnostics        { uint32_t faultMask() const; void raise(Fault); /* counters */ };
// Config: HardwareConfig.h (named logical pins), FlightParams.h (no defaults), BuildFlags.h
```

### 4.4 Config and compile-time guards

- `include/config/HardwareConfig.h`: named logical pins such as `PIN_I2C_SDA` and `PIN_HC12_TX`, all set to `PIN_TBD` (-1).
  - Under `#if CANSAT_TARGET_HARDWARE`, each required pin has `static_assert(PIN_X != PIN_TBD, "PIN_X unresolved – see OD-054")`, so a hardware build fails until the pins are filled in.
  - Native builds do not use pins at all.
- `include/config/FlightParams.h`: declares `struct ReleaseParams { ... }` with **no default member values**. The hardware build requires `CANSAT_FLIGHT_PARAMS_APPROVED`, otherwise `#error`. Test scenarios build their own params from constants named `SYNTHETIC_*` inside `test/` and `sim/` only.
- `STUCK_SWITCH_POLICY` (OD-060) is an enum with **no default**. A hardware build without an explicit, team-approved value fails with `#error`. Native tests and the simulation iterate over every candidate value.
- `include/config/BuildFlags.h`: `CANSAT_ENABLE_PHYSICAL_ACTUATORS` defaults to `0`. Setting it to `1` triggers `#error "No approved physical actuator driver (OD-059)"` during Phases 1–2.

### 4.5 Reset recovery (RecoveryManager)

- **Persisted record** (NVS on hardware, an in-memory or file mock in tests):
  - `{magic, version, boot_count, last_state, one_shot_flags{release_confirmed, chute_requested, chute_decided}, t_release_rel, crc}`
  - It is written on every state change and every one-shot flag change. That is only a handful of writes per flight.
- **On boot:** increment `boot_count`. If a valid record shows the last state was at or past Ascent, re-check the switches and sensors before resuming ([PDR] slide 19).
  - A one-shot flag that is already set is **never** re-issued.
- **Open policy question** for Gautam ([TBD]): what happens on a reset *after* a parachute request was recorded but *before* its outcome was known? The options are to re-attempt, or to assume it was done and continue. The safe default has to be decided by the team.

### 4.6 Laptop-testability

- **Mocks:** scriptable mock sensors (value sequences), a mock switch, a mock link (captures bytes and can corrupt or drop them), a mock log sink (a file), a mock persistent store, and a mock actuator (counts calls and *can never touch hardware*).
- **Scenario runner** (`sim/`): reads a scripted scenario or replays a CSV trace through `SensorManager → … → Telemetry/Logger` with a virtual clock.
- **Fault injection:** sensor dropout (valid = false), freeze (repeated samples, i.e. stale), spikes, a stuck switch (closed throughout, or open at boot), and a reset at any tick (the core objects are destroyed and rebuilt from the persisted store).

### 4.7 Proposed project layout (Phase 2)

```
firmware/
  platformio.ini            envs: native (tests), esp32dev (compile-only until pins resolved)
  include/config/           HardwareConfig.h  FlightParams.h  BuildFlags.h
  lib/core/                 Types, SensorManager, ReleaseDetector, FlightStateManager, ActuatorManager,
                            RecoveryManager, TelemetryManager(+CRC), DataLogger, PowerMonitor, Diagnostics
  lib/hal/                  interfaces only
  lib/hal_mock/             mocks used by tests and sim
  lib/hal_esp32/            real drivers (sensors, UART, SD, NVS) – later; NO physical actuator driver
  src/main.cpp              wiring only (hardware build)
  test/                     unit tests (native)
sim/                        scenario runner + scenarios/ (all values SYNTHETIC)
ground_station/
  gs_firmware/              ESP32 HC-12 → USB passthrough sketch
  gs_tool/                  Python parser, validator, CSV logger (stdlib only; pyserial optional)
  tests/                    unittest, replayed/simulated streams
data/synthetic/             generated traces, clearly marked SYNTHETIC
```

### 4.8 Build and test setup: recommendation

- **PlatformIO** [RECOMMENDATION], because:
  - one `platformio.ini` gives both a **native** environment (unit tests run on the laptop with the Unity framework) and an **esp32dev Arduino-framework** environment. The code stays Arduino C++, which matches the [TEAM DECISION].
  - library versions can be pinned per environment.
  - `pio test -e native` is a single command that can also run in CI.
- **arduino-cli** compiles and uploads, but it has no way to run tests on the host. We would have to build a separate host test harness anyway.
- **Cost:** `pip install platformio`, plus a toolchain download of a few hundred MB on the first ESP32 build. **I will not install it without your approval.**
- **Zero-install fallback, so work is not blocked:** the core library is plain C++17, so Phase 2 step 1 can start with a `Makefile` + the system `c++` + a tiny in-repo test harness. PlatformIO is added when you approve it. The Python ground-station tests use stdlib `unittest` (pytest is not installed). Live serial needs `pyserial` later (also needs approval). Tests and replay read files or pipes.

---

## 5. Telemetry packet schema v1 (proposal)

**Framing:** `$` + comma-separated **numeric** fields + `*` + 4-hex-digit CRC + `\n`.
- **CRC:** CRC-16/CCITT-FALSE (polynomial 0x1021, init 0xFFFF) over the bytes strictly between `$` and `*`. [ASSUMPTION] The test vector "123456789" → 0x29B1 was checked by script.
- **Missing data:** the field is sent as `0` and its bit in `valid` is cleared. Parsers **must** check `valid`. No text and no units appear inside fields.
- **Versioning:** any change to field order, meaning or units increments `ver`. The ground station rejects unknown versions but still logs them raw.

| # | Field | Type / units | Source | PDR field | Status |
|---|---|---|---|---|---|
| 0 | `ver` | uint, =1 | constant | — | [RECOMMENDATION] |
| 1 | `team` | uint | config | `TEAM_ID` ("001") | [TBD] value |
| 2 | `boot` | uint16, boot counter | RecoveryManager | — | [RECOMMENDATION] Shows resets to the ground station. |
| 3 | `pkt` | uint32, sequence number per boot | Telemetry | `PKT` | [PDR] |
| 4 | `t_ms` | uint32, ms since boot | IClock | `TIME` (was "00:01:23.4") | [RECOMMENDATION] Numeric. The ground station converts it. |
| 5 | `state` | uint8, FlightState code 1–8 | FSM | `STATE` (was text) | [PDR] states, numeric code |
| 6 | `evt` | uint16 bitmask, latched events | FSM / detector | — | [RECOMMENDATION] Covers "release event and timestamp recorded in telemetry" ([PDR] slide 9). |
| 7 | `fault` | uint16 bitmask | Diagnostics | — | [RECOMMENDATION] |
| 8 | `valid` | uint16 bitmask, per-sensor validity | SensorManager | — | [RECOMMENDATION] |
| 9 | `sw` | uint8, debounced switch bits | inputs | — | [TBD] meaning (OD-015) |
| 10 | `alt_dm` | int32, decimetres above the ground reference | derived from pressure | `ALT` | [TBD] ground-reference method and formula |
| 11 | `p_pa` | uint32, Pa | BMP280 | `P` (was "0.98atm") | [UNVERIFIED] sensor |
| 12 | `temp_cc` | int16, 0.01 °C | BMP280 | `TEMP` | [UNVERIFIED] sensor |
| 13–15 | `ax_mg, ay_mg, az_mg` | int16, milli-g | MPU6050 | — (IMU is in the [PDR] slide 20 bench test) | [TBD] whether to send gyro (log only?) |
| 16 | `v_mv` | uint16, mV | INA219 bus voltage | `VBAT`? | [TBD] which rail (OD-014, OD-053) |
| 17 | `i_ma` | int16, mA | INA219 | — | [TBD] which rail |
| 18 | `act` | uint16, actuator request/decision bits | ActuatorManager | — | [RECOMMENDATION] Shows "requested / blocked / simulated", never "deployed". |
| — | `H%` | — | **no sensor** | `H%` | [TBD] OD-013 |
| — | `SPC`, `SPV` | — | **no second sensor** | `SPC`, `SPV` | [TBD] OD-014 |

- **Example (illustrative, [SIMULATED] values):** `$1,1,3,342,85412,7,13,0,63,0,854,100240,2450,-12,8,1003,3912,182,1*AC80`
- **Size:** 72 B typical, 123 B worst case (§2.1).
- **Ground-station side:**
  - The ESP32 passes HC-12 bytes straight through to USB at [PDR] 115200 baud (slide 17).
  - The Python tool timestamps each line on receipt and validates framing, CRC, version, field count, integer parsing and plausibility ranges.
  - It counts lost packets (`pkt` gaps), duplicates and reboots (`boot` changes).
  - It writes three files: a raw log, a parsed CSV and a rejects log.
- [TBD] **Uplink:** the PDR mentions "SIMULATION commands" from the GCS (slide 17). v1 is downlink-only. An uplink would need authentication and safety review, and it must never be able to trigger deployment.

---

## 6. Software-only acceptance demonstration (definition for Phase 2 item 8)

**One command** (for example `make demo`, or `pio test -e native && python3 -m gs_tool.demo`) runs the scenarios below on the laptop with no hardware. Every output file and report is stamped **"SIMULATED – not hardware validation"**.

All thresholds and timings in these scenarios are `SYNTHETIC_*` and live only under `sim/` and `test/`.

| Scenario | Injected condition | Expected software behaviour |
|---|---|---|
| S1 Nominal | Power-on → mounted → ascent → release → free fall → chute → descent → touchdown | States 1→2→3→4→5→6→7→8. Exactly one `ReleaseParachute` request, decision `ExecutedSimulated` (or `BlockedBuildDisabled`, depending on the demo build). Telemetry is parsed with 0 CRC errors. |
| S2 Baro dropout | Barometer invalid during descent | `valid` bit cleared and fault flag raised. No altitude-based transition is made from invalid data. Logging continues. |
| S3 IMU dropout at release | IMU invalid in the release window | Release is confirmed only through the baro path, or flagged uncorroborated, exactly per §3.2. No crash. |
| S4 Switch stuck closed | Switch never opens; free fall and baro descent do occur. A variant S4b has the CanSat still mounted with a faulty IMU reading zeros and the drone descending | `ReleaseSensorsOnly` + DEGRADED flag in every case. The scenario is run **once per candidate policy** in OD-060 §H, and the report shows side by side whether each policy requests the parachute in S4 (truly released) and in S4b (truly mounted). **No policy is marked as the pass/fail expectation** until the team decides. |
| S5 Switch open at power-on | Switch reads open while on the drone | Self-check reports the fault. The release logic is not armed. |
| S6 Reset after release | Reset between ReleaseConfirmed and the parachute request | Restored from the record. The flight continues without re-detecting release. One request in total. |
| S7 Reset after request | Reset just after a recorded parachute request | **No second request.** The reset is visible in telemetry (`boot` incremented). |
| S8 Link corruption | Bytes flipped, lines truncated, packets dropped on the simulated link | The ground station rejects bad frames, counts the gaps, and keeps running. The onboard CSV log is complete. |

**Pass criteria:**
- Deterministic results.
- The state and event sequence matches the expected one for each scenario.
- The mock actuator's physical-call counter is 0, and no physical driver is linked.
- At most one parachute request per flight, across resets.
- The parsed ground-station CSV matches the onboard log for every packet that was not corrupted.

**Explicitly NOT demonstrated:**
- release-detection thresholds or timing
- sensor accuracy or calibration
- radio range or packet loss on real RF
- servo timing or torque
- parachute or panel deployment
- power-rail behaviour
- physical safety

The report will list the hardware tests still required (`docs/08` Stages 3–4, `TRACEABILITY.md`).

---

## 7. Questions for you (software lead): max 5

| # | Question | Options | Recommended default | Consequence | Who knows |
|---|---|---|---|---|---|
| Q1 | Create a separate Git repository for this project? (full inspection and options R1–R4 in `OPEN_DECISIONS.md` §C) | R1 nested `git init` in the project folder; R2 = R1 + exclude the folder in the home repo; R4 clean up the home repo | R1 (optionally R2). R4 later, separately | R1 touches nothing outside the project. R4 could destroy the only copy of the staged `drone_slam_ws` data | You |
| Q2 | Install PlatformIO now? | (a) yes, `pip install platformio` (~hundreds of MB of toolchains); (b) start with Makefile + system `c++`, decide later | (b) now, (a) before the ESP32 compile check | (b) is unblocked today. (a) adds the ESP32 compile check and the Unity runner. | You |
| Q3 | May I mark stale statements in the older docs (D-002, D-008, `hardware/pinout.md`, `docs/04`, `docs/06`, `docs/07`) as superseded, by adding notes and not deleting anything? | (a) yes, add notes only; (b) leave them, and keep the log in OPEN_DECISIONS only | (a) | (b) leaves contradictory guidance for teammates and future agents. | You |
| Q4 | Record the Arduino-C++ and HC-12 deviations in `DECISIONS.md` (proposed text in §8)? | (a) append; (b) wait for the team meeting | (b), then (a) | Appending now records the [TEAM DECISION] before the team has reaffirmed it tonight. | Team |
| Q5 | Telemetry encoding for v1 | (a) ASCII CSV as in §5; (b) compact binary | (a) | (a) is human-readable and close to the PDR. (b) is about half the size, so it allows a lower baud and longer range, but it is harder to debug. | You + Mukund |

---

## 8. Proposed `DECISIONS.md` additions (NOT yet written; for approval)

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-013 | Arduino C++ on ESP32 is the firmware environment. This is a **deviation** from [PDR] slide 19 "ESP-IDF (C/C++)". A teammate's MicroPython suggestion was not adopted. | [TEAM DECISION] | Deviation recorded; supersedes the open note in D-003. |
| D-014 | HC-12 433 MHz UART telemetry is a **deviation** from [PDR] ESP-NOW (slides 16, 17, 22). PDR range (≥150 m) and link-gap (≤1.0 s) targets still apply. | [TEAM DECISION] | Supersedes D-008. |
| D-015 | D-002 (ESP32-S3) is superseded by D-006/D-009 (ESP32 DevKit). | Consistency | Housekeeping |
| D-016 | Phases 1–2: physical actuation is disabled at compile time. No physical servo driver will be written until OD-059 is closed. | Safety | [RECOMMENDATION] awaiting approval |
