# Environmental Intelligence Platform

Real-time environmental monitoring and analysis for an **Arduino UNO R4 WiFi**
edge node: ingestion, historical storage, explainable risk scoring, anomaly
detection, forecasting, alerting, a realtime dashboard and an AI analyst that
reasons over the platform's own data through a **local Ollama** model.

```
                 ┌──────────────────────────────┐
                 │        PHYSICAL SENSORS       │
                 │ AM2302/DHT22  rain   LDR      │
                 │ BMP280        MQ-135          │
                 └───────────────┬──────────────┘
                                 │
                 ┌───────────────▼──────────────┐
                 │  ARDUINO UNO R4 WIFI (edge)   │
                 │  read → validate → JSON       │
                 │  HTTP POST + X-API-Key        │
                 │  5 risk LEDs + buzzer         │
                 └───────────────┬──────────────┘
                        Wi-Fi / HTTP (LAN or hotspot)
                 ┌───────────────▼──────────────┐
                 │        FASTAPI BACKEND        │
                 │ API-key auth → validation →   │
                 │ normalisation → SQLite →      │
                 │ analytics → risk engine →     │
                 │ anomalies → prediction →      │
                 │ alerts → realtime bus         │
                 └───────┬───────────────┬───────┘
              REST/WebSocket             │ grounded context
                 ┌───────▼───────┐  ┌────▼─────────────┐
                 │  REACT + TS   │  │ OLLAMA (existing │
                 │  DASHBOARD    │◄─┤ local install)   │
                 │  + AI analyst │  └──────────────────┘
                 └───────────────┘
```

## Verification status (honest summary)

| Component | Status |
| --- | --- |
| FastAPI backend | **Executed — PASS** (`pytest`, plus live smoke tests against a running server) |
| Frontend (React 19 + TS + Vite) | **Executed — PASS** (`npm run typecheck`, `npm run build`) |
| Database, analytics, risk, anomalies, prediction, alerts | **Executed — PASS** |
| Realtime WebSocket + SSE | **Executed — PASS** |
| Chatbot | **Executed — PASS with a stubbed model**; a real grounded answer requires the local Ollama server to be running |
| Arduino firmware — static compilation, both sensor configs, pin-conflict guard | **Executed — PASS** (`bash arduino/static_check/run.sh`) |
| Arduino firmware — Arduino IDE compile, real sensors, LEDs, buzzer, Wi-Fi | **NOT DONE** — no Arduino IDE / toolchain available |

Two things are deliberately *not* claimed. The firmware has never been compiled
with the UNO R4 toolchain nor downloaded to a board, and the chatbot's answers
are verified against a stubbed model rather than a live Ollama instance. Treat
first-flash bring-up and a live Ollama check as real tasks, not formalities.

## Repository layout

```
backend/     FastAPI application, tests, .env.example
frontend/    React + TypeScript dashboard (Vite, Tailwind, Recharts, Framer Motion)
arduino/     UNO R4 WiFi firmware + config.example.h + wiring/setup guide
docs/        architecture, API and hardware documentation
```

## 1. Backend

```bash
cd backend
python -m venv ../venv                 # Python 3.11+ (developed and tested on 3.14)
../venv/Scripts/activate               # Windows;  source ../venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                   # then edit API_KEY
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

* Interactive docs: <http://127.0.0.1:8000/docs>, OpenAPI JSON at `/openapi.json`
* Health probe: `GET /api/v1/health` (version, uptime, DB, device, Ollama)
* The database is created automatically on first start (`backend/data/environmental.db`)

**Bind to `0.0.0.0`.** The Arduino must reach this machine over the LAN/hotspot,
so `127.0.0.1` would make the API unreachable from the node.

## 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173  (proxies /api to the backend)
npm run build        # type-checks and produces dist/
```

`VITE_API_BASE_URL` (see `frontend/.env.example`) points the UI at a backend on
another host. No secret is ever shipped to the browser — the frontend only talks
to FastAPI.

## 3. Arduino

Full instructions, wiring tables and troubleshooting live in
[`arduino/README.md`](arduino/README.md). The short version:

```bash
cd arduino/environmental_monitor
cp config.example.h config.h     # git-ignored: Wi-Fi + API key live here
```

Set `WIFI_SSID`, `WIFI_PASSWORD`, `BACKEND_HOST` (the PC's LAN IP — **never**
`localhost`), `BACKEND_PORT`, `API_KEY` (same value as `backend/.env`),
`DEVICE_ID` and `TEMP_HUMIDITY_SENSOR` (`SENSOR_AM2302_DHT22` by default; use
`SENSOR_DHT12_I2C` if you wired a DHT12 to `SDA`/`SCL`). Then flash
`environmental_monitor.ino` to an UNO R4 WiFi with the Arduino IDE 2.x and watch
the serial monitor at 115200 baud.

Without the Arduino IDE you can still verify the firmware compiles:

```bash
bash arduino/static_check/run.sh
```

## 4. Configuration reference

Backend (`backend/.env`, template in `backend/.env.example`):

| Variable | Purpose |
| --- | --- |
| `API_KEY` | device key the Arduino sends in `X-API-Key` (required) |
| `BACKEND_HOST` / `BACKEND_PORT` | bind address/port (use `0.0.0.0`) |
| `DATABASE_URL` | SQLite by default; PostgreSQL-ready |
| `DEVICE_ID` | must match `DEVICE_ID` in the firmware |
| `CORS_ORIGINS` | allowed browser origins (wildcards are ignored, never honoured) |
| `CORS_ALLOW_LAN_ORIGINS` | also accept RFC1918 browser origins (demo convenience; off by default) |
| `REQUIRE_AUTH_FOR_READS` | also protect read endpoints |
| `RAIN_*` / `LIGHT_*` / `AIR_QUALITY_*` | ADC calibration; must match the firmware |
| `ANALYTICS_DEFAULT_HOURS`, `RETENTION_DAYS` | history windows |
| `OLLAMA_HOST`, `OLLAMA_MODEL` | local Ollama endpoint and model |
| `OLLAMA_MODELS_DIRS` | extra model-store locations to read when listing installed models |
| `RISK_CONFIG_FILE` | optional JSON that replaces the risk weights/bands |

Frontend (`frontend/.env`): `VITE_API_BASE_URL`, `VITE_PROXY_TARGET`,
`VITE_WS_URL`, `VITE_DEV_PORT`.

Firmware (`arduino/environmental_monitor/config.h`): Wi-Fi, backend host/port,
API key, `DEVICE_ID`, `SEND_INTERVAL_MS`, pin map, ADC calibration, timeouts.

## 5. Ollama integration

The platform **uses the Ollama installation that already exists** on the
machine. It never installs, downloads, replaces or duplicates anything.

* detection order: `ollama` on `PATH` → `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`
  → `/usr/local/bin/ollama` etc.
* models are read from the running server (`GET /api/tags`) and, if the server is
  down, from the model directory on disk, so you can still see what is installed.
  Lookup order: `OLLAMA_MODELS` (Ollama's own variable), then `OLLAMA_MODELS_DIRS`
  (a comma-separated list for machines that keep models off the system drive,
  e.g. `D:/OllamaModels`), then the conventional per-platform locations. No path
  is hardcoded in the source.
* the model is selected by `OLLAMA_MODEL` when set, otherwise from
  `OLLAMA_FALLBACK_MODELS` (default `gemma3:4b,qwen3:4b,qwen3:8b,…`)
* `GET /api/v1/chat/status` reports availability, the chosen model and the reason
  when nothing is available

Start it with your existing install (`ollama serve`, or the desktop app). If it
is not running, the dashboard keeps working and the chatbot answers from its
built-in rule-based analyst, clearly labelled as a fallback — sensor monitoring
never depends on the LLM.

The browser never talks to Ollama: `Frontend → FastAPI → Ollama → FastAPI → Frontend`.

## 6. Tests

```bash
cd backend
python -m pytest -q          # isolated temp database, no network needed
```

Coverage includes health/auth, payload validation (malformed, extreme, stale,
duplicate, partially missing sensors), ingestion, historical/aggregation
endpoints, risk scoring and explanations, anomaly detection, prediction and its
"insufficient data" behaviour, alerts, the chatbot (including the offline
fallback), WebSocket/SSE realtime, and an end-to-end pass that pushes a full
deterministic sensor trace through the real ingestion pipeline and asserts the
values reach storage, analytics, risk, prediction and the chatbot context
unchanged.

## 7. Connecting the real Arduino

1. Put the PC and the Arduino on the same network (a phone hotspot is fine).
2. Find the PC's address: `ipconfig` → the Wi-Fi adapter's IPv4 (or
   `GET /api/v1/meta` → `local_addresses`, also shown on the **Hardware** page).
3. Put that IP in `BACKEND_HOST` in the firmware `config.h`.
4. Allow inbound TCP on the backend port — on Windows, when the firewall prompt
   appears choose **Private networks**; otherwise add a rule:
   ```
   netsh advfirewall firewall add rule name="EnvMon API" dir=in action=allow protocol=TCP localport=8000
   ```
5. Flash, open the serial monitor, and confirm the node logs
   `Payload accepted ... - risk L…`.

The node POSTs every `SEND_INTERVAL_MS` (default 15 s) and polls
`/api/v1/device/{id}/risk-state` so its LEDs and buzzer mirror the backend's
level. Until the first payload arrives the dashboard shows the honest
**"Waiting for the Arduino UNO R4 Wi-Fi to send sensor data"** state, and
analytics/prediction report insufficient history rather than inventing numbers.

## 8. API overview

All routes are versioned under `/api/v1`. Device endpoints require `X-API-Key`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/status`, `/meta` | liveness, dashboard header, sensor/risk/alert metadata |
| POST | `/sensors/data` | ingest an Arduino payload (API key required) |
| POST | `/sensors/heartbeat` | optional keep-alive for the node |
| GET | `/sensors/latest`, `/history`, `/aggregate`, `/summary/{day\|week}` | readings and aggregation |
| GET | `/sensors/anomalies`, `/baseline`, `/health`, `/correlations` | anomaly and sensor-health analytics |
| GET | `/analytics/overview`, `/observations`, `/trends`, `/classification`, `/compare` | dashboard analytics |
| GET | `/risk/current`, `/risk/analysis`, `/risk/model`, `/risk/alerts` | explainable risk |
| GET | `/predictions`, `/predictions/accuracy`, `/predictions/history` | forecasts + accuracy |
| GET | `/alerts`, `/alerts/rules`, POST `/alerts/{id}/acknowledge\|resolve` | alert centre |
| GET | `/device`, `/device/list`, `/device/{id}/risk-state` | device telemetry + LED/buzzer state |
| GET/POST | `/chat`, `/chat/status`, `/chat/suggestions`, `/chat/history/{session}` | AI analyst |
| WS/SSE | `/realtime/ws`, `/realtime/events` | live dashboard updates |

Details, schemas and examples: [`docs/api.md`](docs/api.md) and `/docs`.

## 9. Documentation

* [`docs/architecture.md`](docs/architecture.md) — components, data flow, design decisions
* [`docs/api.md`](docs/api.md) — endpoint reference and payload contracts
* [`docs/hardware.md`](docs/hardware.md) — sensors, wiring, calibration, LED/buzzer semantics
* [`arduino/README.md`](arduino/README.md) — firmware setup and bring-up

## 10. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Dashboard shows "Waiting for the Arduino…" | Node not flashed, wrong `BACKEND_HOST`, different network, or firewall blocking the port |
| `POST /sensors/data` → 401/403 | `API_KEY` mismatch between `backend/.env` and the firmware `config.h` |
| `POST /sensors/data` → 503 | `API_KEY` is still a placeholder or shorter than 16 characters; the response names the reason |
| `POST /sensors/data` → 422 | A value outside the physical range, or a stale timestamp (the error names the field) |
| Device goes offline in the UI | No payload within `DEVICE_OFFLINE_AFTER_SECONDS` (default 60 s) — check power/Wi-Fi |
| `/chat` says "AI unavailable" | Ollama is not running; the sensor platform is unaffected |
| Charts are empty | No readings yet, or a time range with no data — the UI says which |
| Analytics reports insufficient history | Fewer samples than the prediction/anomaly window needs; wait for more readings |
| Frontend cannot reach the API | `VITE_PROXY_TARGET`/`VITE_API_BASE_URL` wrong, or the backend is bound to `127.0.0.1` |
| Pressure/humidity look implausible | Calibration constants differ between `config.h` and `backend/.env` |

## 11. Design principles

* **One risk model.** The score, its level, its reasons and its recommended
  actions are computed once, in the backend, and reused by the API, the
  dashboard, the chatbot, the alerts and the Arduino's LEDs — never re-invented
  per component.
* **No invented numbers.** Missing sensors stay missing, forecasts carry
  method/confidence/horizon, and the chatbot is instructed to quote only values
  present in the snapshot it is given.
* **Degrade, never crash.** Ollama down, device offline, empty database, one
  sensor dead — each has an explicit state in the API and the UI.
* **Secrets stay outside the repo.** `.env` and `config.h` are git-ignored; only
  `.env.example` / `config.example.h` templates are tracked. The server also
  *refuses* to authenticate a device with a placeholder or short key, so a
  template value can never quietly become a production credential.
