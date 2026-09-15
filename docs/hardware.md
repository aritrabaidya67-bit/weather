# Hardware

## Validation status — read this first

| Item | Status |
| --- | --- |
| Pin map, sensor selection, JSON contract, HTTP flow | **Statically compiled and reviewed** (`bash arduino/static_check/run.sh`) |
| Compiled with the Arduino IDE / UNO R4 toolchain | **NOT DONE** — the toolchain was not available |
| Sensors read on a bench, LEDs/buzzer observed | **NOT DONE** |

Everything the *backend* does with a payload is covered by the automated test
suite. The firmware itself is written to be UNO R4 WiFi correct and is verified
by a host-side compile, but "it works on real hardware" is a claim that requires
the real toolchain and real sensors. Treat first-flash bring-up as a real task.

## Bill of materials

| # | Component | Notes |
| --- | --- | --- |
| 1 | Arduino UNO R4 WiFi | built-in Wi-Fi; 10-bit ADC usable up to 14 bits (this project uses 10 to match calibration) |
| 2 | AM2302 / DHT22 temperature + humidity | ±0.5 °C, ±2 %RH (max ±5 %), one-wire; **default configuration** |
| 2b | *(alternative)* DHT12 in I²C mode | ±0.5 °C / ±4 %RH, I²C address `0x5C`; see the sensor note below |
| 3 | Rain sensor (LM393 board) | **uncalibrated** wetness detector; inverted output (high = dry) |
| 4 | LDR (GL5528 + 10 kΩ) | relative illumination only |
| 5 | BMP280 | pressure ±1 hPa, temperature ±1 °C |
| 6 | MQ-135 | **uncalibrated** air-quality/gas sensor; needs 24 h burn-in |
| 7 | Buzzer | active or passive (see `BUZZER_PASSIVE`) |
| 8 | 5 × LEDs + 220 Ω resistors | physical risk indicator |

## Pin map

| Signal | Pin | Config key |
| --- | --- | --- |
| AM2302/DHT22 data | `D2` | `PIN_DHT` (one-wire only; not used by the DHT12 build) |
| DHT12 (alternative) | `SDA`/`SCL` | `DHT12_I2C_ADDRESS` (`0x5C`) |
| Rain analog | `A0` | `PIN_RAIN_ANALOG` |
| LDR analog | `A1` | `PIN_LDR_ANALOG` |
| MQ-135 analog | `A2` | `PIN_MQ135_ANALOG` |
| BMP280 | `SDA`/`SCL` | `BMP280_I2C_ADDRESS` (`0x76`/`0x77`) |
| LED level 1…5 | `D3 D4 D5 D6 D7` | `PIN_LED_1..5` |
| Buzzer | `D8` | `PIN_BUZZER` |

## The temperature/humidity sensor — AM2302 vs DHT12

These are **not** interchangeable, and this project does not pretend they are.
`config.h` selects exactly one of them via `TEMP_HUMIDITY_SENSOR`:

| | `SENSOR_AM2302_DHT22` (default) | `SENSOR_DHT12_I2C` |
| --- | --- | --- |
| Part | Aosong AM2302 (= DHT22) | Aosong DHT12 |
| Wiring | data → `D2`, 10 kΩ pull-up to 3V3 | `SDA`/`SCL` (default I²C pins) |
| Protocol | DHT22 single-bus frame: 16-bit humidity, 16-bit signed temperature, 1 ms wake-up | DHT12 I²C frame: 5 registers (`humi_int`, `humi_dec`, `temp_int`, `temp_dec`, checksum) at `0x5C` |
| Library | Adafruit *DHT sensor library* | none — read directly with `Wire` |
| Range | −40…80 °C, 0…100 %RH | −20…60 °C, 20…95 %RH |
| Accuracy | ±0.5 °C, ±2 %RH (max ±5 %) | ±0.5 °C, ±4 %RH |

The DHT12 also has a **one-wire mode, and that mode is not supported here.** In
one-wire mode the DHT12 transmits the *DHT11-style* frame — an integer and a
decimal byte per quantity with an ~18 ms wake-up — while the AM2302/DHT22 sends a
16-bit value per quantity with a 1 ms wake-up. Pointing a DHT22 decoder at a
DHT12 therefore does not fail cleanly: it decodes the integer/decimal bytes as a
single 16-bit number. With a typical reading of 45.3 %RH / 24.6 °C the DHT22
decoder would produce roughly **1160 % RH**, and the firmware's physical-range
guard would discard the channel. That is the honest outcome — but it looks like
a broken sensor, which is a bad way to spend an evening.

So: **if you have a DHT12, wire it to `SDA`/`SCL` and set
`TEMP_HUMIDITY_SENSOR SENSOR_DHT12_I2C`.** The firmware rejects any other
combination at compile time, and `arduino/static_check/run.sh` proves both
supported builds compile.

Consequence for the rest of the platform: the physical ranges and accuracy
figures used by the backend (`app/core/sensors.py`) describe the AM2302/DHT22,
which is the default and the configuration the documentation assumes.

## Wiring

```
        +3V3 ──┬── 10kΩ ──┬── D2 (AM2302/DHT22 data)
               │          │
           AM2302/DHT22 ──┘

        (alternative)  DHT12: SDA ── SDA,  SCL ── SCL,  VCC ── 3V3,  GND ── GND

        Rain AO ── A0        LDR divider ── A1        MQ-135 AO ── A2
        (3V3/GND)            (3V3 – LDR – A1 – 10kΩ – GND)

        BMP280  SDA ── SDA   SCL ── SCL   VCC ── 3V3   GND ── GND

        D3 ──▶|── 220Ω ── GND     (LED 1 = risk level 1)
        D4 ──▶|── 220Ω ── GND     (LED 2 = risk level 2)
        D5 ──▶|── 220Ω ── GND     (LED 3 = risk level 3)
        D6 ──▶|── 220Ω ── GND     (LED 4 = risk level 4)
        D7 ──▶|── 220Ω ── GND     (LED 5 = risk level 5)
        D8 ── buzzer ── GND
```

All grounds must be common. If the MQ-135 heater browns out the board, power it
from a separate 5 V rail with a shared ground.

## Calibration — the two sides must agree

The backend converts raw ADC counts into engineering units. The firmware ships
the same constants, and `config.h` documents this pairing explicitly:

| Quantity | Firmware (`config.h`) | Backend (`backend/.env`) | Default |
| --- | --- | --- | --- |
| Rain dry / wet | `RAIN_DRY_ADC` / `RAIN_WET_ADC` | `RAIN_DRY_ADC` / `RAIN_WET_ADC` | 950 / 250 |
| Light dark / bright | `LIGHT_DARK_ADC` / `LIGHT_BRIGHT_ADC` | `LIGHT_DARK_ADC` / `LIGHT_BRIGHT_ADC` | 40 / 900 |
| Air-quality baseline | `AIR_QUALITY_CLEAN_ADC` | `AIR_QUALITY_CLEAN_BASELINE` | 180 |
| ADC full scale | `ADC_MAX` | registry range | 1023 |

Change one and you must change the other, otherwise the dashboard and the node's
own serial log will disagree.

## Honest sensor limitations

* **MQ-135** is not calibrated to ppm, so the platform publishes a *relative*
  index (0–100) against a clean-air baseline. It is comparable over time on one
  node, not across devices, and it needs burn-in.
* **Rain sensor** is a wetness detector, not a rain gauge. "Rain 0–100 %" means
  how wet the board is, and heavy rain on a rainy day can read the same as a
  puddle splash.
* **LDR** gives relative illumination, not lux.
* **AM2302/DHT22** needs ≥ 2 s between reads and a 10 kΩ pull-up; without it you
  get `nan`. The DHT12 in I²C mode has no such timing constraint.
* **BMP280** pressure is absolute station pressure; the platform does not
  convert to sea level (that would require a known altitude).

## Risk indication (LEDs + buzzer)

The risk level always comes from the backend, so the physical indicators and the
dashboard cannot disagree.

| Level | Label | LEDs | Buzzer |
| --- | --- | --- | --- |
| 1 | Very Low | LED 1 | silent |
| 2 | Low | LED 1–2 | silent |
| 3 | Moderate | LED 1–3 | one short beep per minute |
| 4 | High | LED 1–4 | two short beeps every 30 s |
| 5 | Critical | LED 1–5 | repeating alarm |

Degraded behaviour:

* before any assessment → LED 1 pulses slowly (alive, no verdict)
* backend unreachable or reading stale → the level's LEDs blink; the buzzer keeps
  its last pattern so a critical alarm cannot be lost
* Wi-Fi drops → the firmware reconnects automatically and the indicators blink
  until a fresh assessment arrives

## Static verification (no Arduino IDE required)

```bash
bash arduino/static_check/run.sh
```

This compiles `environmental_monitor.ino` with a normal C++ compiler against
signature-faithful API stubs, in **both** sensor configurations, and asserts that
an unsupported sensor selection and a duplicated pin each fail the build. It
verifies syntax, API usage and the pin map; it does **not** read a sensor or
upload anything, and it is not a substitute for flashing the board.

## Bring-up checklist

1. Wire everything with the power off; double-check `3V3` vs `5V` rails.
2. Set `TEMP_HUMIDITY_SENSOR` in `config.h` to match the part you actually wired.
3. Flash the sketch — the boot lamp test lights each LED on its own in sequence
   and beeps once, which proves the indicator wiring before any data exists. The
   serial monitor then prints the pin map the firmware compiled with.
4. Open the serial monitor (115200) and confirm the sensor line, the pin map and
   the Wi-Fi/IP lines.
5. Send a reading and confirm `Payload accepted ... - risk L…`.
6. Cover the LDR / wet the rain board / breathe near the MQ-135 and watch the
   dashboard values change in step with the serial log.
7. Verify the LED count matches the risk level shown on the dashboard, and that
   level 5 triggers the alarm pattern.
8. Unplug the network and confirm the indicators blink (fail-visible, not
   silently stale).
