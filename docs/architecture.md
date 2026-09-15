# Architecture

## Layers

```
backend/app/
├── main.py            FastAPI app, lifespan, CORS, error handlers, latency guard
├── api/
│   ├── deps.py        shared dependencies (session, API key, device resolution, ranges)
│   ├── services.py    single import surface for routes (avoids import cycles)
│   └── routes/        health, sensors, analytics, risk, predictions, alerts, device,
│                      chatbot, realtime — one module per concern, mounted under /api/v1
├── core/
│   ├── config.py      every tunable value (pydantic-settings, .env driven)
│   ├── database.py    engine/session factory, UTC column types, session scope
│   ├── security.py    API-key comparison, secret registration for log redaction
│   ├── sensors.py     sensor registry: units, ranges, bands, aliases (single source of truth)
│   ├── realtime.py    in-process pub/sub bus with a bounded replay buffer
│   └── logging.py     structured logging with secret redaction
├── models/            SQLAlchemy 2.0 ORM (readings, alerts, devices, predictions, chat)
├── repositories/      query objects; the only place that touches the ORM directly
├── schemas/           Pydantic v2 request/response contracts
├── services/          business logic (ingest, analytics, risk, anomaly, prediction,
│                      alerts, device, chatbot, Ollama client, background scheduler)
└── utils/             statistics, time helpers, derived environment maths
```

Rules kept throughout: routes never touch the ORM, repositories never contain
business rules, and the sensor registry is the only place that defines units,
ranges and interpretation bands.

## Ingestion pipeline

`POST /api/v1/sensors/data` → `SensorService.ingest` performs, in order:

1. **Auth** — `X-API-Key` constant-time comparison; 401/403 on mismatch, 503 while no key is configured.
2. **Rate limit** — per-key token bucket (`INGEST_RATE_LIMIT_PER_MINUTE`).
3. **Schema validation** — Pydantic: types, `ge`/`le` bounds, unknown fields rejected.
4. **Physical plausibility** — values outside the registry's physical window are dropped (and reported), never stored.
5. **Timestamps** — device clock drift beyond `MAX_TIMESTAMP_SKEW_SECONDS` is rejected and the server receive time is used instead.
6. **Duplicates** — an identical payload inside `DUPLICATE_WINDOW_SECONDS` is acknowledged with `duplicate: true` and not stored twice.
7. **Normalisation** — raw ADC counts → percentages/indexes using the calibration constants; derived metrics (heat index, dew point).
8. **Persistence** — reading row + device upsert.
9. **Risk** — explainable score, level, reasons, actions, per-factor contributions.
10. **Anomalies** — rolling-baseline z-scores and sudden-change detection → severity + explanation.
11. **Alerts** — rule evaluation and upsert/dedupe by fingerprint.
12. **Realtime** — `reading`, `risk`, `anomaly`, `alert`, `device` events published to the bus.
13. **Response** — `{success, message, reading_id, risk_score, risk_level, risk_label, warnings, duplicate}` which is what drives the Arduino's LEDs.

The whole step runs in ~30–50 ms on SQLite; nothing calls the LLM on the ingest
path, and Ollama is only contacted by the chatbot endpoints.

## Risk engine

`risk_service.py` is deterministic and fully auditable:

* each factor (air quality, temperature, humidity, pressure, rain, light) has a
  weight and a monotonic 0..1 severity curve; `points = weight × severity`
* anomaly severity and a small set of combination rules add points
* the per-factor points sum to the reported score, which is why the UI can show
  `Air quality +28, Humidity +15, …` instead of a bare label
* levels 1–5 (`Very Low … Critical`) map to `led_index` and a `buzzer_pattern`;
  both the dashboard and the firmware read those from the same model
* `risk/model` publishes the weights, bands and level definitions for the UI
* `RISK_CONFIG_FILE` replaces the whole model with JSON, no code change

Confidence reflects data coverage (how many of the six channels actually
reported), so a score built from two sensors never claims certainty.

## Anomaly detection

Rolling mean/σ per metric over `window_points`, clamped σ to avoid
divide-by-zero on flat signals, plus a sudden-change detector comparing the new
sample with the previous one. Each anomaly carries sensor, current value,
baseline, severity and a human explanation — no opaque scores.

## Prediction

`prediction_service.py` estimates each channel over the requested horizon using
the best method the available data supports and reports which one it used:

* **seasonal/trend regression** when there is enough history with a stable trend
* **damped linear extrapolation** otherwise
* **exponential smoothing** as the last resort for noisy series

Each metric returns current → predicted value, unit, direction, expected
status, confidence, method and warnings; when the series is too short the
service says `data_sufficient: false` and gives the sample count rather than
inventing a forecast. Prediction snapshots are stored so `/predictions/accuracy`
can score past forecasts against what actually happened.

## Realtime

An in-process pub/sub bus (`core/realtime.py`) with a bounded replay buffer:

* `WS /api/v1/realtime/ws` — primary channel; clients may subscribe to topics and resume with `last_event_id`
* `GET /api/v1/realtime/events` — SSE fallback
* the frontend throttles heavy refreshes, so a fast device cannot thrash the API

## Chatbot

`chatbot_service.py` builds a complete snapshot (current reading, 6-hour
statistics, baselines, risk assessment with contributions, anomalies, alerts,
sensor health, forecasts, correlations) and sends it with explicit grounding
rules: quote only values present in the snapshot, state the horizon and
confidence of forecasts, say when data is missing or stale, never give
medical/safety-critical advice.

* `POST /api/v1/chat` — full answer with citations and `used_context`
* `POST /api/v1/chat/stream` — token stream
* Ollama is reached only from the backend; the model name stays configuration
* if Ollama is unreachable the same snapshot is answered by a deterministic
  rule-based analyst and the response says `fallback_used: true` with the reason
* transcripts are persisted per session under `/api/v1/chat/history/{session_id}`

## Data model

| Table | Contents |
| --- | --- |
| `sensor_readings` | one row per accepted payload: UTC timestamps, source, every metric, risk score/level/label, reasons, actions, anomaly list |
| `devices` | first/last seen, firmware, IP, RSSI, interval, counters, rejected payloads |
| `alerts` | fingerprint, category, severity, message, recommendation, active/resolved, occurrence count |
| `predictions` | forecast snapshots for the accuracy endpoint |
| `chat_messages` | transcripts with model, latency, grounding mode and error |

Timezone-aware UTC column types are used so SQLite and PostgreSQL behave
identically; repositories take a plain `Session`, so moving to PostgreSQL is a
`DATABASE_URL` change plus `pip install psycopg`.

## Background work

`scheduler` (disabled in tests) runs the device watchdog (offline detection and
alerting), prediction snapshots, retention pruning and periodic Ollama health
probing. Every job is independent: a failure in one is logged and the others
keep running.

## Extension points

* **Another sensor** — add it to `core/sensors.py`; registry, API metadata,
  validation, analytics and the UI pick it up.
* **A different database** — set `DATABASE_URL`; no ORM changes needed.
* **A different risk model** — supply `RISK_CONFIG_FILE`.
* **A real ML forecaster** — implement the same method interface in
  `prediction_service.py`; the API contract and UI stay unchanged.
* **A second node** — the device layer is already multi-device (`/device/list`,
  per-`device_id` queries and alerts).
