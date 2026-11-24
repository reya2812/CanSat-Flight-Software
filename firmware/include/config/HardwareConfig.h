// HardwareConfig.h — the ONLY place where hardware pins and bus settings live.
//
// [TBD] Every GPIO is unresolved (docs/OPEN_DECISIONS.md OD-054). Pins are
// named logically and set to kPinTbd. Do NOT fill these in without the exact
// ESP32 board pinout and the team-approved wiring. Pin constraints to respect
// are listed in docs/PHASE1_PROPOSAL.md §2.5 (strapping pins, input-only pins,
// boot-time glitch pins).
//
// A hardware build (CANSAT_TARGET_HARDWARE=1) fails to compile while any
// required item below is still TBD. Native/laptop builds never touch pins.
#pragma once

#include <stdint.h>

#include "BuildFlags.h"

namespace cansat {
namespace hw {

constexpr int kPinTbd = -1;

// ---- I2C sensor bus (BMP280, MPU6050, INA219) ----  [TBD] OD-054
constexpr int PIN_I2C_SDA = kPinTbd;
constexpr int PIN_I2C_SCL = kPinTbd;

// ---- HC-12 radio UART ----  [TBD] OD-054, OD-055
constexpr int PIN_HC12_TX = kPinTbd;   // ESP32 TX -> HC-12 RXD
constexpr int PIN_HC12_RX = kPinTbd;   // ESP32 RX <- HC-12 TXD
constexpr int PIN_HC12_SET = kPinTbd;  // [TBD] may be unused if AT config is fixed
constexpr bool kHc12SetPinUsed = false;  // [TBD] OD-055; SET pin only checked if true
constexpr uint32_t kHc12UartBaud = 0;    // [TBD] OD-055 (0 = unresolved). Not chosen by software.

// ---- Micro-SD (SPI) ----  [TBD] OD-054
constexpr int PIN_SD_SCK = kPinTbd;
constexpr int PIN_SD_MISO = kPinTbd;
constexpr int PIN_SD_MOSI = kPinTbd;
constexpr int PIN_SD_CS = kPinTbd;

// ---- Limit switches ----  [TBD] OD-015, OD-051 (roles, NO/NC, pull-ups)
constexpr int PIN_SWITCH_1 = kPinTbd;
constexpr int PIN_SWITCH_2 = kPinTbd;

// ---- Buzzers ----  [TBD] OD-052 (driver circuit)
constexpr int PIN_BUZZER_1 = kPinTbd;
constexpr int PIN_BUZZER_2 = kPinTbd;

// ---- Servo signals ----  [TBD] OD-050 (assignments). Declared for completeness
// only; no physical servo driver exists (OD-059), so they are not required by
// the hardware build in Phases 1–2.
constexpr int PIN_SERVO_1 = kPinTbd;
constexpr int PIN_SERVO_2 = kPinTbd;
constexpr int PIN_SERVO_3 = kPinTbd;

// ---- I2C addresses ----
// [UNVERIFIED] team-reported (docs/03_hardware_specification.md); confirm by
// I2C scan on the assembled bus (MEETING_BRIEF M2).
constexpr uint8_t kBmp280AddrCandidateA = 0x76;  // [UNVERIFIED] OD-056: 0x76 or 0x77
constexpr uint8_t kBmp280AddrCandidateB = 0x77;  // [UNVERIFIED] OD-056
constexpr uint8_t kMpu6050Addr = 0x68;           // [UNVERIFIED]
constexpr uint8_t kIna219Addr = 0x40;            // [UNVERIFIED]

// ---- Ground station USB link ----
constexpr uint32_t kGroundStationUsbBaud = 115200;  // [PDR] slide 17

// True only when every pin/setting required by the hardware build is resolved.
constexpr bool requiredHardwareResolved() {
  return PIN_I2C_SDA != kPinTbd && PIN_I2C_SCL != kPinTbd &&
         PIN_HC12_TX != kPinTbd && PIN_HC12_RX != kPinTbd &&
         (!kHc12SetPinUsed || PIN_HC12_SET != kPinTbd) && kHc12UartBaud != 0 &&
         PIN_SD_SCK != kPinTbd && PIN_SD_MISO != kPinTbd &&
         PIN_SD_MOSI != kPinTbd && PIN_SD_CS != kPinTbd &&
         PIN_SWITCH_1 != kPinTbd && PIN_SWITCH_2 != kPinTbd &&
         PIN_BUZZER_1 != kPinTbd && PIN_BUZZER_2 != kPinTbd;
}

#if CANSAT_TARGET_HARDWARE
static_assert(PIN_I2C_SDA != kPinTbd, "PIN_I2C_SDA unresolved (OD-054)");
static_assert(PIN_I2C_SCL != kPinTbd, "PIN_I2C_SCL unresolved (OD-054)");
static_assert(PIN_HC12_TX != kPinTbd, "PIN_HC12_TX unresolved (OD-054)");
static_assert(PIN_HC12_RX != kPinTbd, "PIN_HC12_RX unresolved (OD-054)");
static_assert(!kHc12SetPinUsed || PIN_HC12_SET != kPinTbd, "PIN_HC12_SET unresolved (OD-055)");
static_assert(kHc12UartBaud != 0, "HC-12 UART baud unresolved (OD-055)");
static_assert(PIN_SD_SCK != kPinTbd, "PIN_SD_SCK unresolved (OD-054)");
static_assert(PIN_SD_MISO != kPinTbd, "PIN_SD_MISO unresolved (OD-054)");
static_assert(PIN_SD_MOSI != kPinTbd, "PIN_SD_MOSI unresolved (OD-054)");
static_assert(PIN_SD_CS != kPinTbd, "PIN_SD_CS unresolved (OD-054)");
static_assert(PIN_SWITCH_1 != kPinTbd, "PIN_SWITCH_1 unresolved (OD-051, OD-054)");
static_assert(PIN_SWITCH_2 != kPinTbd, "PIN_SWITCH_2 unresolved (OD-051, OD-054)");
static_assert(PIN_BUZZER_1 != kPinTbd, "PIN_BUZZER_1 unresolved (OD-052, OD-054)");
static_assert(PIN_BUZZER_2 != kPinTbd, "PIN_BUZZER_2 unresolved (OD-052, OD-054)");
#endif

}  // namespace hw
}  // namespace cansat
