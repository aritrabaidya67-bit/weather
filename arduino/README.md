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
| Compiled on physical hardware / Arduino IDE | **NOT DONE** — the Arduino IDE and R4 board package were not available while this firmware was written |
| Sensors actually read on a bench | **NOT DONE** |
| LEDs / buzzer physically observed | **NOT DONE** |

Everything the backend does with this payload *is* tested (see
`backend/tests/`). The firmware itself must still be compiled and bench-verified
by you; `arduino/README.md` is written so that you can do exactly that.

## 1. Hardware

| # | Part | Interface | Pin / address |
| --- | --- | --- | --- |
| 1 | Arduino UNO R4 WiFi | — | — |
| 2 | DHT12 / AM2302 (temperature + humidity) | one-wire | `D2` (`config.h`: `PIN_DHT`) |
| 3 | Rain sensor (LM393 board) | analog | `A0` |
| 4 | LDR (GL5528 + 10 kΩ divider) | analog | `A1` |
| 5 | BMP280 (pressure + temperature) | I²C | `SDA`/`SCL`, address `0x76` (`0x77` if SDO is high) |
| 6 | MQ-135 (air quality / gas) | analog | `A2` |
| 7 | Buzzer | digital | `D8` |
| 8 | 5 × LEDs (risk indicator) | digital | `D3 D4 D5 D6 D7` = level 1…5 |

### Wiring notes

* **LEDs:** anode → `D3`…`D7`, cathode → 220 Ω → GND (active-high, the default
  `LED_ACTIVE_HIGH 1`; set it to `0` for an active-low wiring).
* **DHT12/AM2302:** data → `D2`, plus a 10 kΩ pull-up from data to 3V3. If your
  DHT12 uses its I²C mode, wire it to `SDA`/`SCL` instead and keep
  `DHT_TYPE DHT22` — the sensor ships configured for the one-wire (DHT22)
  protocol, which is what this firmware expects.
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
| **DHT sensor library** (Adafruit) | ≥ 1.4.6 | DHT12 / AM2302 |
| **Adafruit BMP280 Library** | ≥ 2.6.8 | pressure + temperature (pulls in *Adafruit Unified Sensor*) |
| **ArduinoJson** (Benoît Blanchon) | ≥ 7.0 | payload + response parsing |

`WiFiS3`, `Wire` and `tone()` ship with the **Arduino UNO R4 Boards** core — no
extra install.

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
INFO: BMP280 initialised
INFO: Wi-Fi connected on boot. IP 192.168.137.42
INFO: Clock synchronised with the backend server time
INFO: Payload accepted (id 128) - risk L1 Very Low 5.2/100
INFO: Risk level from backend: L1 (Very Low, score 5.2/100)
INFO: Buzzer pattern: silent
INFO: wifi=up posts=4 failed=0 risk=L1 pattern=silent stale=no alerts=0
```

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
| DHT reads `nan` | Missing 10 kΩ pull-up, or the sensor needs a 2 s gap between reads |
| Rain/light values look inverted | Sensor board type differs; adjust `RAIN_DRY_ADC`/`RAIN_WET_ADC` (and the backend equivalents) together |
| Air quality always "poor" | MQ-135 still burning in, or its baseline drifted — recalibrate with clean air |
