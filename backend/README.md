# Backend — FastAPI environmental intelligence API

See the [root README](../README.md) for the project overview, hardware and full
setup. This file covers the backend specifically.

## Run

```bash
python -m venv ../venv                 # or reuse an existing 3.11+ environment
../venv/Scripts/activate               # source ../venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                   # then set API_KEY
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is required so the Arduino can reach the API over the LAN.
Docs: <http://127.0.0.1:8000/docs> · health: `/api/v1/health`.

The SQLite database (`data/environmental.db`) and its schema are created on
first start. Point `DATABASE_URL` at PostgreSQL later without code changes.

## Layout

```
app/
├── main.py          app assembly, lifespan, CORS, error handling
├── api/             deps, route modules, route-facing service surface
├── core/            config, database, security, logging, sensors registry, realtime bus
├── models/          SQLAlchemy ORM
├── repositories/    queries only
├── schemas/         Pydantic request/response contracts
├── services/        ingestion, analytics, risk, anomaly, prediction, alerts,
│                    device, chatbot, Ollama client, background scheduler
└── utils/           statistics, time helpers, derived environment maths
```

Architecture and data-flow details: [`../docs/architecture.md`](../docs/architecture.md).
Endpoint reference: [`../docs/api.md`](../docs/api.md).

## Configuration

Everything is driven by environment variables / `.env`; the full annotated list
is in [`.env.example`](.env.example). The values you are most likely to touch:

* `API_KEY` — the device key the Arduino sends as `X-API-Key`
* `DEVICE_ID` — must match the firmware
* `BACKEND_HOST` / `BACKEND_PORT`
* `CORS_ORIGINS` / `CORS_ALLOW_LAN_ORIGINS` — which browser origins may call the API
* `RAIN_*`, `LIGHT_*`, `AIR_QUALITY_*` — ADC calibration, mirrored in the firmware `config.h`
* `OLLAMA_HOST` / `OLLAMA_MODEL` / `OLLAMA_MODELS_DIRS` — reuse of the existing local Ollama install
* `RISK_CONFIG_FILE` — replace the risk weights/bands with JSON

### API key

The device key is the only credential in the system, and it is treated as one.
Generate it, keep it out of git, and use the same value in the firmware:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

A key is **rejected** (device endpoints answer HTTP 503 with the reason) when it
is empty, shorter than 16 characters, has almost no character variety, or
contains a placeholder marker such as `change-me`, `replace_with`, `example`,
`dev-local-key`, `test-key` or `password`. This is deliberate: a template value
in `.env` must fail loudly rather than silently becoming the production
credential. Read endpoints stay open so the dashboard works without a key; set
`REQUIRE_AUTH_FOR_READS=true` to lock those down too.

### CORS

`CORS_ORIGINS` is an explicit allow-list and a `*` entry is **ignored**, not
honoured — a wildcard would let any web page in a browser call this API.
Development lists the Vite dev server; production should list the real frontend
origin only. `CORS_ALLOW_LAN_ORIGINS=true` additionally accepts RFC1918 origins
(`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`) which is handy for opening the
dashboard from a phone on the same hotspot; it can never widen access to the
public internet.

## Tests

```bash
python -m pytest -q              # full suite
python -m pytest -q -k risk      # one area
```

The suite runs against a throwaway SQLite file, disables background workers and
Ollama, and needs no network. `tests/fixtures/environment_model.py` is a
deterministic sensor model used **only** by the tests so a full sensor trace can
be pushed through the very same ingestion pipeline the real device uses; the
application itself contains no simulation code.

## Notes

* Never commit `.env` — it holds the device API key. Only `.env.example` is tracked.
* Ingestion never calls the LLM; the chatbot endpoints are the only Ollama callers.
* Missing sensor data stays missing: the API reports it instead of filling it in.
