# 06 — Telemetry Protocol (Draft)

> **2026-11-24:** a concrete ESP-NOW protocol v1 ([PROPOSED], OD-079) is specified in `docs/10_esp32_espnow_bringup.md` §4 and implemented in `esp32/lib/cs_proto.py`. It is binary rather than CSV (78-byte frames, inside ESP-NOW's 250-byte limit), versioned, CRC-protected, with per-field validity bits. This draft remains the requirements list; the open questions below are answered there as proposals, pending team approval.

## PDR intent
The PDR selects ESP-NOW at 2.4 GHz and proposes lightweight CSV telemetry to a ground-station ESP32 receiver connected over USB at 115200 baud. A Python GUI is proposed for live plotting and CSV logging.

## PDR example field names
`TEAM_ID, TIME, PKT, ALT, TEMP, P, H%, SPC, SPV, VBAT, STATE`

The PDR example values include altitude, temperature, pressure, humidity, solar-panel current/voltage, battery and state. The example is illustrative and is not yet a formal packet specification.

## Rate and link targets
- PDR pages 6, 17 and 19 state a 4 Hz telemetry target.
- PDR page 17 states an allowable link gap of no more than 1.0 second.
- PDR page 16 gives a minimum line-of-sight target of 150 m (100 m mission height plus 50 m margin).
- PDR page 18 power table labels radio as “ESP-NOW at 1 Hz” while also mentioning 4 Hz in the duty description. This discrepancy is unresolved.

## Draft protocol fields — details TBD
| Field | Meaning | Type / units | Required? |
|---|---|---|---|
| TEAM_ID | CanSat/team identifier | String | TBD |
| TIME | Sample/event timestamp | TBD | TBD |
| PKT | Packet sequence number | Unsigned integer | TBD |
| ALT | Altitude | Metres? reference datum TBD | TBD |
| TEMP | Temperature | °C? | TBD |
| P | Pressure | Pa/hPa/other TBD | TBD |
| H% | Relative humidity | % | TBD |
| SPC | Solar-panel current | A/mA/µA TBD | TBD |
| SPV | Solar-panel voltage | V/mV TBD | TBD |
| VBAT | Battery measurement | V or % TBD | TBD |
| STATE | Flight state | Enumerated string/code TBD | TBD |

## Protocol decisions required
- CSV over ESP-NOW: confirm maximum payload and escaping/line-ending behaviour.
- Define packet version, field order, data types, units and missing-value representation.
- Define timestamp origin, precision and wrap behaviour.
- Define packet sequence behaviour and receiver-side loss detection.
- Define whether event packets are separate from periodic telemetry.
- Define checksum/integrity strategy if needed.
- Define command direction and authentication/validation for any GCS-to-CanSat commands. The PDR mentions simulation commands but does not specify the protocol.
- Define how the GCS handles malformed, stale and duplicate packets.

Do not write a production serializer/parser until the packet schema is approved.
