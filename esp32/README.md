# esp32/ — board bring-up, ESP-NOW telemetry, diagnostics

Software for the two ESP32-WROOM-32 boards (flight + ground) running MicroPython. It is kept outside the guarded `micropython/` flight package (D-021). Full guide: [`docs/10_esp32_espnow_bringup.md`](../docs/10_esp32_espnow_bringup.md).

**Status:** software-tested on a laptop only. Nothing has run on an ESP32 yet. Nothing here drives a servo, buzzer or any output pin.

## Quick start (from the repository root)

```sh
# 0. laptop tests (no hardware)
python3 -m unittest discover -s esp32/tests

# 1. find ports, identify boards (plug in one at a time)
python3 esp32/tools/esp32_ports.py
python3 esp32/tools/esp32_ports.py --read-mac <PORT>

# 2. flash the SAME stable ESP32_GENERIC image to each board (dry run first; --execute asks for a typed confirmation)
python3 esp32/tools/flash_micropython.py --port <FLIGHT_PORT> --role flight --firmware <ESP32_GENERIC-...bin>
python3 esp32/tools/flash_micropython.py --port <FLIGHT_PORT> --role flight --firmware <ESP32_GENERIC-...bin> --execute
python3 esp32/tools/flash_micropython.py --port <GROUND_PORT> --role ground --firmware <ESP32_GENERIC-...bin> --execute

# 3. verify and read MACs, then put them in esp32/config/radio_config.py
mpremote connect <FLIGHT_PORT> run esp32/apps/board_info.py
mpremote connect <GROUND_PORT> run esp32/apps/board_info.py

# 4. deploy (refuses if the board's MAC does not match the role)
python3 esp32/tools/deploy.py --role flight --port <FLIGHT_PORT>
python3 esp32/tools/deploy.py --role ground --port <GROUND_PORT>

# 5. hardware diagnostic on the flight board
mpremote connect <FLIGHT_PORT> run esp32/apps/flight_diag.py

# 6. run (two terminals)
mpremote connect <GROUND_PORT> run esp32/apps/ground_node.py
mpremote connect <FLIGHT_PORT> run esp32/apps/flight_node.py
```

Layout: `config/` (MACs, pins, gates), `lib/` (deployed to `/lib`), `apps/` (programs), `tools/` (laptop), `tests/` (laptop, fakes only).
