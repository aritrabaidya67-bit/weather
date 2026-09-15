# Arduino UNO R4 WiFi — environmental edge node

Firmware for the physical node of the **Environmental Intelligence Platform**.
It reads five sensors, validates every reading, POSTs a JSON payload to the
FastAPI backend over Wi-Fi with an `X-API-Key` header, and mirrors the backend's
risk assessment on five LEDs and a buzzer.

```
sensors -> read + validate -> JSON -> HTTP POST (X-API-Key)
        -> GET /device/{id}/risk-state -> level 1..5 -> 5 LEDs + buzzer pattern
```

## Validation status — read this first

| Item | Status |
| --- | --- |
| Code structure, pin map, JSON contract, HTTP flow | **Code-reviewed** |
| Static compilation (both sensor configurations, pin conflicts, API usage) | **DONE** — `bash arduino/static_check/run.sh` |
| Compiled with the Arduino IDE / UNO R4 toolchain | **NOT DONE** — the IDE and R4 board package were not available |
| Sensors actually read on a bench | **NOT DONE** |
| LEDs / buzzer physically observed | **NOT DONE** |
| Wi-Fi association, HTTP POST and risk polling against a running backend | **NOT DONE** |

Everything the backend does with this payload *is* tested (see
`backend/tests/`), and the firmware is verified to compile cleanly under
`-Wall -Wextra -Werror` with a host C++ compiler. The firmware must still be
compiled with the real toolchain and bench-verified by you; this file is written
so that you can do exactly that.

## 1. Hardware

| # | Part | Interface | Pin / address |
| --- | --- | --- | --- |
| 1 | Arduino UNO R4 WiFi | — | — |
| 2 | **AM2302 / DHT22** (temperature + humidity) — *default* | one-wire | `D2` (`config.h`: `PIN_DHT`) |
| 2b | *Alternative:* **DHT12** (temperature + humidity) in **I²C mode** | I²C | `SDA`/`SCL`, fixed address `0x5C` |
| 3 | Rain sensor (LM393 board) | analog | `A0` |
| 4 | LDR (GL5528 + 10 kΩ divider) | analog | `A1` |
| 5 | BMP280 (pressure + temperature) | I²C | `SDA`/`SCL`, address `0x76` (`0x77` if SDO is high) |
| 6 | MQ-135 (air quality / gas) | analog | `A2` |
| 7 | Buzzer | digital | `D8` |
| 8 | 5 × LEDs (risk indicator) | digital | `D3 D4 D5 D6 D7` = level 1…5 |

This table is the authoritative pin map. `config.h`, `docs/hardware.md` and the
sketch header must always match it, and the sketch contains `static_assert`s that
fail the build if any two of these pins collide.

### Wiring notes

* **LEDs:** anode → `D3`…`D7`, cathode → 220 Ω → GND (active-high, the default
  `LED_ACTIVE_HIGH 1`; set it to `0` for an active-low wiring).
* **AM2302/DHT22:** data → `D2`, plus a 10 kΩ pull-up from data to 3V3.* **DHT12 (alternative):** wire `SDA`/`SCL`/`VCC`/`GND` and set
  `TEMP_HUMIDITY_SENSOR SENSOR_DHT12_I2C`.
* **Do not put a DHT12 on `D2`.** The DHT12's one-wire mode transmits the
  DHT11-style frame (integer + decimal byte per quantity), not the AM2302/DHT22
  16-bit frame. A DHT22 decoder does not fail cleanly on it - it silently
  mis-decodes: a real 45.3 %RH / 24.6 °C DHT12 reading becomes about
  **1152 %RH / 615 °C**, which the firmware's range guard then discards. The
  firmware rejects the invalid combination at compile time, and the detail is in
  `docs/hardware.md`.
* **Rain sensor:** use the analog output (`AO`), power it from 3V3. The board is
  *inverted*: high counts = dry, low counts = wet. That is already handled, and
  the calibration constants match the backend.
* **MQ-135:** needs a 24-hour burn-in before its readings are meaningful. It is
  **not** calibrated, so the platform publishes a *relative index*, never ppm.
* **Grounds:** all sensor grounds must meet at the Arduino GND.
* **Power:** the UNO R4 WiFi can power these modules, but if the MQ-135 heater
  causes brownouts, give it a separate 5 V supply with a common ground.

## 2. Libraries

Install from *Arduino IDE → Tools → Manage Libraries*:

| Library | Version | Why |
| --- | --- | --- |
| **DHT sensor library** (Adafruit) | ≥ 1.4.6 | AM2302/DHT22 (only needed for the `SENSOR_AM2302_DHT22` build) |
| **Adafruit BMP280 Library** | ≥ 2.6.8 | pressure + temperature (pulls in *Adafruit Unified Sensor*) |
| **ArduinoJson** (Benoît Blanchon) | ≥ 7.0 | payload + response parsing |

`WiFiS3`, `Wire` and `tone()` ship with the **Arduino UNO R4 Boards** core — no
extra install. The Adafruit DHT library is only needed for the
`SENSOR_AM2302_DHT22` configuration; the DHT12 build uses `Wire` directly.

## 2b. Static checks (no Arduino IDE needed)

```bash
bash arduino/static_check/run.sh
```

This compiles the sketch with a host C++ compiler against signature-faithful API
stubs. It is a real check, not a formality: it type-checks every API call, and it
proves two safety properties by *requiring* the build to fail if they are broken
— an unsupported `TEMP_HUMIDITY_SENSOR` and a duplicated pin. It runs four
passes: the AM2302 build, the DHT12 build, and both negative cases.

It does **not** read a sensor, drive a pin, connect to Wi-Fi or upload anything.
Green here means "the code is sound", never "the board works".

## 3. Configuration

Credentials are **never** stored in the sketch or in git:

```bash
cd arduino/environmental_monitor
cp config.example.h config.h     # config.h is git-ignored
```

Edit `config.h`:

```c
#define WIFI_SSID       "YOUR_HOTSPOT_SSID"
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"
#define BACKEND_HOST    "192.168.1.50"   // laptop LAN/hotspot IP - NEVER localhost
#define BACKEND_PORT    8000
#define API_KEY         "the-same-value-as-API_KEY-in-backend/.env"
#define DEVICE_ID       "arduino-r4-wifi-01"   // must match DEVICE_ID in backend/.env
#define SEND_INTERVAL_MS 15000
#define TEMP_HUMIDITY_SENSOR SENSOR_AM2302_DHT22   // or SENSOR_DHT12_I2C
```

`API_KEY` must be the same value as `backend/.env`, and the backend **rejects**
placeholder or short keys outright (HTTP 503 naming the reason), so generate a
real one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

If `config.h` is missing the sketch still compiles against
`config.example.h` and prints a warning on the serial console — it will simply
never reach your backend.

> **`localhost` from the Arduino means the Arduino.** Use the PC's LAN address
> (`ipconfig` → IPv4 of the Wi-Fi adapter, or the hotspot gateway address).
> The backend prints its detected addresses at `/api/v1/meta`
> (`local_addresses`, `recommended_backend_url`) and on the **Hardware** page.

## 4. Flashing

1. Install **Arduino IDE 2.x** and the **Arduino UNO R4 Boards** core
   (*Boards Manager → "Arduino UNO R4 Boards" by Arduino*).
2. Open `arduino/environmental_monitor/environmental_monitor.ino`.
3. Select *Arduino UNO R4 WiFi* and the correct serial port.
4. Upload, then open **Serial Monitor at 115200 baud**.

Expected serial output:

```
=====================================================
 Environmental Intelligence Platform - Arduino UNO R4
=====================================================
INFO: Temperature/humidity sensor: AM2302/DHT22 on D2 (one-wire, DHT22 frame)
INFO: Pin map: rain=A0 light=A1 air=A2 LEDs=D3/D4/D5/D6/D7 buzzer=D8 (LEDs active-high)
INFO: BMP280 initialised
INFO: Connecting to Wi-Fi 'YOUR_HOTSPOT_SSID' ...
INFO: Wi-Fi connected. IP 192.168.137.42 RSSI -58 dBm
INFO: Posting to http://192.168.1.50:8000/api/v1/sensors/data
INFO: Clock synchronised with the backend server time
INFO: Payload accepted (id 128) - risk L1 Very Low 5.2/100
INFO: Buzzer pattern: silent
INFO: wifi=up posts=4 failed=0 risk=L1 pattern=silent stale=no alerts=0
```

Compare the `Pin map:` line against the table above before chasing anything
else: it is the wiring the firmware actually compiled with.

If you see `Backend rejected the API key (HTTP 401)`, `API_KEY` and
`backend/.env`'s `API_KEY` differ. If you see
`Cannot open TCP connection ...`, it is networking: wrong IP, different Wi-Fi
network, or Windows Firewall blocking the port (see the root README).

## 5. What the LEDs and buzzer mean

The risk level is computed **by the backend**, never by the firmware, so the
physical indicators and the dashboard always agree.

| Level | Label | LEDs lit | Buzzer pattern |
| --- | --- | --- | --- |
| 1 | Very Low | LED 1 | silent |
| 2 | Low | LED 1–2 | silent |
| 3 | Moderate | LED 1–3 | `single_short_60s` — one short beep per minute |
| 4 | High | LED 1–4 | `double_short_30s` — two short beeps every 30 s |
| 5 | Critical | LED 1–5 | `critical_alarm` — repeating alarm pattern |

Degraded states are visible rather than silent:

* **No assessment received yet** → LED 1 pulses slowly (node alive, no verdict).
* **Backend unreachable / stale reading** → the level's LEDs *blink*; the buzzer
  keeps the last pattern so a critical alarm is never lost.
* **Wi-Fi down** → same blinking indication; the firmware reconnects on its own.

Buzzer frequency and pattern timing are configurable in `config.h`
(`BUZZER_PASSIVE`, `BUZZER_FREQUENCY_HZ`) and on the backend side in
`BUZZER_PATTERNS` (`backend/app/services/risk_service.py`).

## 6. Payload contract

```json
{
  "device_id": "arduino-r4-wifi-01",
  "firmware_version": "1.0.0",
  "sequence": 128,
  "uptime_ms": 1920000,
  "transmission_interval_ms": 15000,
  "source": "arduino",
  "ip_address": "192.168.137.42",
  "rssi": -58,
  "timestamp": "2026-09-15T12:30:05Z",
  "temperature_c": 25.4,
  "humidity_pct": 61.2,
  "bmp_temperature_c": 25.1,
  "pressure_hpa": 1013.24,
  "rain_raw": 940,
  "rain_status": "dry",
  "ldr_raw": 780,
  "light_status": "high",
  "air_quality_raw": 310,
  "sensors_available": ["temperature_c", "humidity_pct", "pressure_hpa", "bmp_temperature_c", "rain_raw", "ldr_raw", "air_quality_raw"],
  "sensors_missing": []
}
```

* `timestamp` is **omitted** until the node has learned the wall clock from the
  backend's `server_time`; the backend then stamps the arrival time. A wrong
  clock is worse than no clock.
* No fake precision: the DHT is rounded to 0.1, the BMP280 pressure to 0.01 hPa,
  analog channels are sent as raw 10-bit ADC counts and the backend converts them
  with the same calibration constants (`RAIN_*`, `LIGHT_*`).
* Invalid readings (out of the physical window in `config.h`) are dropped and the
  channel is listed in `sensors_missing` instead of being transmitted as a lie.

The response is

```json
{ "success": true, "message": "Sensor data accepted", "reading_id": 128,
  "risk_score": 5.2, "risk_level": 1, "risk_label": "Very Low",
  "alerts_created": [], "warnings": [], "duplicate": false }
```

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| LEDs pulse slowly, nothing else | Backend unreachable: IP/port, same Wi-Fi network, firewall |
| `HTTP 401/403` | `API_KEY` in `config.h` ≠ `API_KEY` in `backend/.env` |
| `HTTP 422` | A value fell outside the backend's accepted range; the detail names the field |
| `BMP280 not found` | I²C wiring, address `0x76` vs `0x77`, 3V3 supply |
| `DHT12 did not acknowledge on the I2C bus` | DHT12 wiring/power, or `TEMP_HUMIDITY_SENSOR` set to `SENSOR_DHT12_I2C` for an AM2302/DHT22 (which is not on I²C) |
| Temperature/humidity always missing, other channels fine | Wrong `TEMP_HUMIDITY_SENSOR` for the wired part - a DHT12 on `D2` decodes to ~1152 %RH and is discarded by the range guard |
| DHT reads `nan` | Missing 10 kΩ pull-up, or the sensor needs a 2 s gap between reads |
| `Wi-Fi association timed out` repeating | SSID/password wrong, or the AP is out of range; the node waits `WIFI_ASSOC_TIMEOUT_MS` (20 s) per attempt |
| `Cannot open TCP connection to …` | `BACKEND_HOST` is not the PC's LAN IP, different network, or the firewall blocks the port (the firmware logs the first failure and then every 10th) |
| Rain/light values look inverted | Sensor board type differs; adjust `RAIN_DRY_ADC`/`RAIN_WET_ADC` (and the backend equivalents) together |
| Air quality always "poor" | MQ-135 still burning in, or its baseline drifted — recalibrate with clean air |
