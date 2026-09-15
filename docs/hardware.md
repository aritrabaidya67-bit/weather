# Hardware

## Bill of materials

| # | Component | Notes |
| --- | --- | --- |
| 1 | Arduino UNO R4 WiFi | built-in Wi-Fi; 10-bit ADC usable up to 14 bits (this project uses 10 to match calibration) |
| 2 | DHT12 / AM2302 | temperature ±0.5 °C, humidity ±2–5 %RH |
| 3 | Rain sensor (LM393 board) | **uncalibrated** wetness detector; inverted output (high = dry) |
| 4 | LDR (GL5528 + 10 kΩ) | relative illumination only |
| 5 | BMP280 | pressure ±1 hPa, temperature ±1 °C |
| 6 | MQ-135 | **uncalibrated** air-quality/gas sensor; needs 24 h burn-in |
| 7 | Buzzer | active or passive (see `BUZZER_PASSIVE`) |
| 8 | 5 × LEDs + 220 Ω resistors | physical risk indicator |

## Pin map

| Signal | Pin | Config key |
| --- | --- | --- |
| DHT data | `D2` | `PIN_DHT` |
| Rain analog | `A0` | `PIN_RAIN_ANALOG` |
| LDR analog | `A1` | `PIN_LDR_ANALOG` |
| MQ-135 analog | `A2` | `PIN_MQ135_ANALOG` |
| BMP280 | `SDA`/`SCL` | `BMP280_I2C_ADDRESS` (`0x76`/`0x77`) |
| LED level 1…5 | `D3 D4 D5 D6 D7` | `PIN_LED_1..5` |
| Buzzer | `D8` | `PIN_BUZZER` |

## Wiring

```
        +3V3 ──┬── 10kΩ ──┬── D2 (DHT data)
               │          │
             DHT12 ───────┘

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
* **DHT12/AM2302** needs ≥ 2 s between reads and a pull-up; without it you get
  `nan`.
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

## Bring-up checklist

1. Wire everything with the power off; double-check `3V3` vs `5V` rails.
2. Flash the sketch — the boot lamp test lights every LED in sequence and beeps
   once, which proves the indicator wiring before any data exists.
3. Open the serial monitor (115200) and confirm the Wi-Fi/IP lines.
4. Send a reading and confirm `Payload accepted ... - risk L…`.
5. Cover the LDR / wet the rain board / breathe near the MQ-135 and watch the
   dashboard values change in step with the serial log.
6. Verify the LED count matches the risk level shown on the dashboard, and that
   level 5 triggers the alarm pattern.
7. Unplug the network and confirm the indicators blink (fail-visible, not
   silently stale).
