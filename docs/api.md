# API reference

Base URL `http://<host>:8000/api/v1` · interactive docs at `/docs` · schema at `/openapi.json`.

## Conventions

* **Auth** — device/write endpoints require the header `X-API-Key: <API_KEY>`.
  Read endpoints are open by default; set `REQUIRE_AUTH_FOR_READS=true` to
  require the same header everywhere. Missing key → `401`, wrong key → `403`,
  no key configured on the server → `503`.
* **Errors** — `{"success": false, "error": "...", "detail": "...", "timestamp": "..."}`.
  Validation failures return FastAPI's `422` with the offending field.
* **Timestamps** — UTC ISO-8601 everywhere. `timestamp` is when the device says
  it measured; `received_at` is when the backend stored it.
* **Units** — `degC`, `%RH`, `hPa`, `idx` (relative 0–100 air-quality index),
  `%` (derived rain/light), plus raw 10-bit ADC counts for `*_raw` fields.

## Ingest

### `POST /sensors/data`
Send a reading from the Arduino. Body:

```json
{
  "device_id": "arduino-r4-wifi-01",
  "timestamp": "2026-09-15T12:30:05Z",
  "firmware_version": "1.0.0",
  "sequence": 128,
  "uptime_ms": 1920000,
  "transmission_interval_ms": 15000,
  "ip_address": "192.168.137.42",
  "rssi": -58,
  "temperature_c": 25.4,
  "humidity_pct": 61.2,
  "bmp_temperature_c": 25.1,
  "pressure_hpa": 1013.24,
  "rain_raw": 940,
  "ldr_raw": 780,
  "air_quality_raw": 310
}
```

Every measurement is optional: a payload with a subset of channels is accepted
and the missing ones are reported back. `sensors_missing` / `sensors_available`
make "sensor not connected" explicit instead of looking like a zero.

Response:

```json
{
  "success": true,
  "message": "Sensor data accepted",
  "reading_id": 128,
  "risk_score": 5.2,
  "risk_level": 1,
  "risk_label": "Very Low",
  "alerts_created": [],
  "warnings": [],
  "duplicate": false
}
```

Rejections: `422` (values outside the physical range, stale timestamp — the
detail names the field), `401/403` (key), `429` (rate limit).

### `POST /sensors/heartbeat`
Optional keep-alive for a node that cannot send a full payload.

## Readings and history

| Endpoint | Notes |
| --- | --- |
| `GET /sensors/latest` | latest stored reading (404 before the first payload) |
| `GET /sensors/history?hours=6&bucket=1h&limit=500` | readings + per-metric series (min/max/mean/latest/slope/trend) |
| `GET /sensors/aggregate?hours=24&bucket=30m` | downsampled averages for charts |
| `GET /sensors/summary/day`, `/sensors/summary/week` | daily/weekly aggregates |
| `GET /sensors/anomalies?hours=6` | anomalies in the window, with severity and explanation |
| `GET /sensors/baseline` | rolling mean/σ per monitored metric |
| `GET /sensors/health` | per-sensor reporting rate, staleness, stuck-value detection |
| `GET /sensors/correlations` | pairwise correlations where they are meaningful |
| `GET /sensors/catalog` | registry: keys, units, ranges and interpretation bands |

## Analytics

| Endpoint | Notes |
| --- | --- |
| `GET /analytics/overview` | everything the dashboard needs in one call: channels, risk, classification, sensor health, observations |
| `GET /analytics/observations` | evidence-backed statements (only emitted when the statistics support them) |
| `GET /analytics/trends` | slope, rate of change and moving averages per channel |
| `GET /analytics/classification` | plain-language environmental classification |
| `GET /analytics/compare?hours=6` | last N hours vs the preceding N hours |

## Risk

* `GET /risk/current` — score (0–100), level (1–5), label, code, colour,
  confidence, reasons, reducing factors, recommended actions and per-factor
  contributions that sum to the score.
* `GET /risk/analysis?hours=6` — the above plus trend points, top contributors,
  anomalies and alerts.
* `GET /risk/model` — weights, combination rules, level bands, LED index and
  buzzer pattern per level (the same data the Arduino receives).
* `GET /risk/alerts` — alerts relevant to the current assessment.

## Predictions

* `GET /predictions?horizon_minutes=30` — per metric: current value, predicted
  value, unit, direction, expected status, confidence, method, warnings; plus
  risk and rain outlooks, a summary and notes. When history is too short the
  response carries `data_sufficient: false` and the sample count.
* `GET /predictions/accuracy` — past forecasts scored against actual readings.
* `GET /predictions/history` — stored forecast snapshots.

## Alerts

* `GET /alerts?active_only=true&limit=50` — list with severity/category counts.
* `GET /alerts/rules` — rule catalogue (id, category, severity, condition, action).
* `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve`.

## Device

* `GET /device` — primary device status: online/offline, last payload, IP, RSSI,
  firmware, transmit interval, delivery rate, missed intervals, sensor
  availability and health notes.
* `GET /device/list` — every device the backend has seen.
* `GET /device/{device_id}` — status of one device.
* `GET /device/{device_id}/risk-state` — **the endpoint the firmware polls**:

```json
{
  "device_id": "arduino-r4-wifi-01",
  "risk_score": 5.2, "risk_level": 1, "risk_label": "Very Low",
  "risk_code": "VERY_LOW", "color": "#22c55e",
  "led_index": 1, "buzzer_pattern": "silent",
  "reasons": ["..."], "recommended_actions": ["..."],
  "stale": false, "age_seconds": 3.1, "data_source": "arduino",
  "alerts_active": 0, "server_time": "2026-09-15T12:30:06Z"
}
```

## System

* `GET /health` — status, version, uptime, database, device summary, Ollama.
* `GET /status` — dashboard header: backend/database/device state, reading
  staleness, realtime subscriber count, data source, active alerts, notes.
* `GET /meta` — sensor registry, risk model, alert rules, feature flags,
  detected LAN addresses and the recommended backend URL for the firmware.
* `GET /system/workers` — background job state and realtime subscriber count.

## Chatbot

`POST /chat`

```json
{ "message": "Why is the risk score what it is right now?", "session_id": "chat-abc", "device_id": "arduino-r4-wifi-01" }
```

Response:

```json
{
  "session_id": "chat-abc",
  "answer": "…grounded explanation…",
  "model": "gemma3:4b",
  "grounding": "historical_data",
  "data_available": true,
  "used_context": { "risk_score": 5.2, "risk_level": 1, "data_source": "arduino", "stale": false,
                    "anomalies": 0, "active_alerts": 0, "prediction_available": true, "snapshot_at": "…" },
  "citations": [ { "label": "Temperature", "value": "25.4 degC", "source": "latest stored reading", "timestamp": "…" } ],
  "latency_ms": 8421,
  "fallback_used": false,
  "warning": null,
  "created_at": "…"
}
```

Also: `POST /chat/stream` (token stream), `GET /chat/status` (Ollama
availability and chosen model), `GET /chat/suggestions` (context-aware
questions), `GET /chat/history/{session_id}`, `DELETE /chat/history/{session_id}`,
`GET /chat/context/{device_id}` (the exact snapshot handed to the model, for
debugging).

## Realtime

* `WS /api/v1/realtime/ws` — topics `reading`, `risk`, `anomaly`, `alert`,
  `device`, `prediction`, `system`; subscribe with
  `{"action":"subscribe","topics":[...],"last_event_id":N}`.
* `GET /api/v1/realtime/events` — SSE fallback with the same event shape.
* `GET /api/v1/realtime/status` — subscriber count, topics, buffer depth.

## Examples

```bash
# ingest (as the Arduino does)
curl -X POST http://192.168.1.50:8000/api/v1/sensors/data \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"device_id":"arduino-r4-wifi-01","temperature_c":24.6,"humidity_pct":52,"pressure_hpa":1012.6,"rain_raw":940,"ldr_raw":700,"air_quality_raw":205}'

# ask the analyst
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Which sensor is the biggest concern right now?"}'

# risk state for a hardware bring-up check
curl -H "X-API-Key: $API_KEY" http://192.168.1.50:8000/api/v1/device/arduino-r4-wifi-01/risk-state
```
