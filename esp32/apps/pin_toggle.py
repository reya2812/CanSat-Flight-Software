# pin_toggle.py - bench tool: switch SDA (GPIO21) and SCL (GPIO22) LOW / HIGH
# together, once per second. Nothing else.
#
#     python3 -m mpremote connect <FLIGHT_PORT> run esp32/apps/pin_toggle.py     (Ctrl-C to stop)
#
# Open-drain only (approved exception, D-022): LOW = the ESP32 pulls the line to
# GND; HIGH = the ESP32 lets go and the pull-up resistors raise the line. It
# never drives a line high, so it cannot fight a sensor on the I2C bus. Only
# these two pins are touched. Stops after DURATION_S or Ctrl-C; both lines are
# always released and returned to inputs.
import time
from machine import Pin

SDA = 21
SCL = 22
HALF_PERIOD_MS = 1000
DURATION_S = 60


def main():
    sda = Pin(SDA, Pin.OPEN_DRAIN, value=1)
    scl = Pin(SCL, Pin.OPEN_DRAIN, value=1)
    print("== pin toggle: SDA=GPIO%d SCL=GPIO%d, %d ms LOW / %d ms HIGH, %d s (Ctrl-C to stop) =="
          % (SDA, SCL, HALF_PERIOD_MS, HALF_PERIOD_MS, DURATION_S))
    t0 = time.ticks_ms()
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < DURATION_S * 1000:
            sda.value(0)
            scl.value(0)
            print("LOW")
            time.sleep_ms(HALF_PERIOD_MS)
            sda.value(1)
            scl.value(1)
            print("HIGH (released)")
            time.sleep_ms(HALF_PERIOD_MS)
    except KeyboardInterrupt:
        pass
    finally:
        sda.value(1)
        scl.value(1)
        Pin(SDA, Pin.IN)
        Pin(SCL, Pin.IN)
        print("stopped: both lines released")


if __name__ == "__main__":
    main()
