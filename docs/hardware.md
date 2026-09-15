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

## Bring-up checklist (must be performed on real hardware)

None of the items below has been executed: no UNO R4 toolchain or physical sensors
were available while this firmware was written. They are the tasks that remain
between "the code is sound" and "the node works", stated so they can be run as a
list rather than discovered one at a time. Do not report the node as validated
until each one produces the observation in the right-hand column.

### A. Toolchain and static pre-flight (no board needed)

| # | Step | Expected |
| --- | --- | --- |
| A1 | `bash arduino/static_check/run.sh` | 4 PASS (both sensor builds + both negative cases) |
| A2 | `cp config.example.h config.h`, then set `WIFI_SSID`, `WIFI_PASSWORD`, `BACKEND_HOST` (PC LAN IP, never `localhost`), `API_KEY` = `backend/.env` `API_KEY`, `DEVICE_ID` = `DEVICE_ID` | file exists, is git-ignored (`git status` stays clean) |
| A3 | Install the **Arduino UNO R4 Boards** core + the three libraries from `arduino/README.md` | Board manager shows the core; `WiFiS3`/`Wire` resolve |
| A4 | Compile **without uploading** (Sketch → Verify) for *Arduino UNO R4 WiFi* | 0 errors; note the flash/RAM figures |
| A5 | Recompile after switching `TEMP_HUMIDITY_SENSOR` to the other value | 0 errors (both configurations must build) |

### B. Power-on, clock and wiring

| # | Step | Expected observation |
| --- | --- | --- |
| B1 | Power up with the serial monitor at 115200 | Banner, sensor line, pin map line, Wi-Fi line with an IP |
| B2 | Watch the boot lamp test | LEDs 1→5 light **one at a time in sequence**, then one short beep |
| B3 | Compare the `Pin map:` line with the table above | Identical pins; a mismatch means the wiring or `config.h` is wrong |
| B4 | Confirm the node learned the wall clock | `Clock synchronised with the backend server time`, and `timestamp` present in the POST |
| B5 | Confirm the first POST is accepted | `Payload accepted (id …) - risk L… …/100` within one interval |

### C. Sensor truth (compare against an independent reference)

| # | Step | Expected observation |
| --- | --- | --- |
| C1 | Temperature/humidity vs a second thermometer/hygrometer | Within the part's accuracy (±0.5 °C / ±2–5 %RH); **never** ~1152 %RH (that is a DHT12 on `D2`) |
| C2 | BMP280 vs a local weather report | Pressure within a few hPa; temperature agrees with the DHT within ~1 °C |
| C3 | Rain board: dry, then water droplets on the tracks | `rain_status` goes dry → light/rain; `rain_pct` rises; **calibrate** `RAIN_DRY_ADC`/`RAIN_WET_ADC` if the crossover is wrong |
| C4 | LDR: cover it, then a bright light | `light_pct` low then high; `light_status` follows |
| C5 | MQ-135 after the 24 h burn-in, clean air vs alcohol/CO₂ source | Relative index rises then returns; it must **never** be read as ppm |

### D. Indicators (backend-driven)

| # | Step | Expected observation |
| --- | --- | --- |
| D1 | Healthy reading | LED count == `risk_level` on the dashboard; buzzer silent at L1/L2 |
| D2 | Force a high band (e.g. hold the MQ-135 near a source, or POST a hot reading) | Level rises on the dashboard and the LED count/buzzer pattern follow within one interval |
| D3 | Drive level 5 | All five LEDs lit and the repeating critical alarm |
| D4 | Level 3 and 4 | One beep per minute; two beeps per 30 s |
| D5 | Before the first assessment (fresh backend/DB) | LED 1 pulses slowly — alive, no verdict yet |

### E. Failure modes (the part that decides whether the node is trustworthy)

| # | Fault injected | Expected behaviour — and it must recover afterwards |
| --- | --- | --- |
| E1 | Stop the backend (`Ctrl-C`) | Indicators **blink** the last level instead of showing a stale solid value; buzzer keeps its pattern; serial logs the TCP failure, then only every 10th |
| E2 | Restart the backend | Node reconnects on its own; `Backend reachable again after N failures`; solid indication returns |
| E3 | Turn the AP / phone hotspot off, then on | Wi-Fi association retries with the configured timeout; no reboot needed; IP re-obtained |
| E4 | One sensor unplugged (e.g. DHT data line) | That channel is absent from the payload and listed in `sensors_missing`; **other channels keep reporting**; no fabricated value |
| E5 | All sensors unplugged | No POST is sent (an empty payload would be rejected); serial escalates `SENSOR_FAILURE_LIMIT` times, then says what to check |
| E6 | Wrong `API_KEY` (backend key changed) | `HTTP 401` logged once per attempt, **without ever printing the key** |
| E7 | Backend returns 422 (e.g. an out-of-range value) | The response body is logged and the node keeps running |
| E8 | Very long run (hours) | No memory corruption/reboot; sequence numbers keep incrementing; loop stays responsive (LEDs keep blinking) |
| E9 | Power-cycle mid-operation | Node reboots, re-syncs the clock, and resumes; the backend treats the restarted sequence as a new run |

### F. Dashboard agreement

| # | Step | Expected observation |
| --- | --- | --- |
| F1 | Open the dashboard while the node posts | Live tiles update without a refresh; the WebSocket reports `live` |
| F2 | Compare a serial reading with `GET /sensors/latest` | Identical values — the backend stores what the node measured |
| F3 | Compare the dashboard risk with the serial `risk L…` | Identical level and label (one risk model, no re-derivation on the device) |

Record the firmware version, the board, the sensor configuration and the
observations; attach the serial log. Anything you did not run stays unverified -
say so rather than implying it passed.
