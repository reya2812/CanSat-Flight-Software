# hardware_config.py - the ONLY place where pins and bus settings live.
# (port of include/config/HardwareConfig.h)
#
# [TBD] Every GPIO is unresolved (docs/OPEN_DECISIONS.md OD-054). Pins are
# named logically and set to PIN_TBD. Do NOT fill these in without the exact
# ESP32 board pinout and the team-approved wiring (constraints:
# docs/PHASE1_PROPOSAL.md section 2.5).
#
# WEAKER THAN C++: C++ refuses to compile a hardware build while any required
# item is TBD (static_assert). Here boot_checks refuses to start on hardware,
# and tools/scan_guards.py fails if a pin is assigned a number anywhere else.

PIN_TBD = -1

# ---- I2C sensor bus (BMP280, MPU6050, INA219) ----  [TBD] OD-054
PIN_I2C_SDA = PIN_TBD
PIN_I2C_SCL = PIN_TBD

# ---- HC-12 radio UART ----  [TBD] OD-054, OD-055
PIN_HC12_TX = PIN_TBD   # ESP32 TX -> HC-12 RXD
PIN_HC12_RX = PIN_TBD   # ESP32 RX <- HC-12 TXD
PIN_HC12_SET = PIN_TBD  # [TBD] may be unused if AT config is fixed
HC12_SET_PIN_USED = False  # [TBD] OD-055; SET pin only checked if True
HC12_UART_BAUD = 0         # [TBD] OD-055 (0 = unresolved). Not chosen by software.

# ---- Micro-SD (SPI) ----  [TBD] OD-054
PIN_SD_SCK = PIN_TBD
PIN_SD_MISO = PIN_TBD
PIN_SD_MOSI = PIN_TBD
PIN_SD_CS = PIN_TBD

# ---- Limit switches ----  [TBD] OD-015, OD-051, OD-068
PIN_SWITCH_1 = PIN_TBD
PIN_SWITCH_2 = PIN_TBD

# ---- Buzzers ----  [TBD] OD-052. No buzzer output code exists (D-017), so a
# hardware boot does not require these yet (D-018).
PIN_BUZZER_1 = PIN_TBD
PIN_BUZZER_2 = PIN_TBD

# ---- Servo signals ----  [TBD] OD-050. Declared for completeness only; no
# servo output code exists (D-017, OD-059), so they are never required.
PIN_SERVO_1 = PIN_TBD
PIN_SERVO_2 = PIN_TBD
PIN_SERVO_3 = PIN_TBD

# ---- I2C addresses ----  [UNVERIFIED] team-reported (docs/03); confirm by I2C scan.
BMP280_ADDR_CANDIDATE_A = 0x76  # [UNVERIFIED] OD-056: 0x76 or 0x77
BMP280_ADDR_CANDIDATE_B = 0x77  # [UNVERIFIED] OD-056
MPU6050_ADDR = 0x68             # [UNVERIFIED]
INA219_ADDR = 0x40              # [UNVERIFIED]

# ---- Ground station USB link ----
GROUND_STATION_USB_BAUD = 115200  # [PDR] slide 17


def unresolved_items():
    """Names of the items a hardware run still needs.

    Same list as the C++ static_asserts EXCEPT the buzzer pins (D-018): no buzzer
    code exists, so they are not required. When buzzer code is approved
    (OD-052, OD-059), add PIN_BUZZER_1/2 back to this list in the same change.
    """
    out = []
    for name in ("PIN_I2C_SDA", "PIN_I2C_SCL", "PIN_HC12_TX", "PIN_HC12_RX",
                 "PIN_SD_SCK", "PIN_SD_MISO", "PIN_SD_MOSI", "PIN_SD_CS",
                 "PIN_SWITCH_1", "PIN_SWITCH_2"):
        if globals()[name] == PIN_TBD:
            out.append(name)
    if HC12_SET_PIN_USED and PIN_HC12_SET == PIN_TBD:
        out.append("PIN_HC12_SET")
    if HC12_UART_BAUD == 0:
        out.append("HC12_UART_BAUD")
    return out


def required_hardware_resolved():
    return len(unresolved_items()) == 0
