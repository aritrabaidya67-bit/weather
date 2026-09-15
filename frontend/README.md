# Frontend — realtime environmental dashboard

React 19 + TypeScript + Vite, styled with Tailwind CSS v4, animated with Framer
Motion, charted with Recharts, icons from Lucide. It talks **only** to the
FastAPI backend; no secret ever reaches the browser.

```bash
npm install
npm run dev        # http://127.0.0.1:5173 (proxies /api to the backend)
npm run build      # tsc -b && vite build
npm run preview    # serve the production build
```

## Configuration

Copy `.env.example` to `.env` when you need to deviate from the defaults:

| Variable | Meaning |
| --- | --- |
| `VITE_API_BASE_URL` | absolute backend URL; empty means same-origin (dev proxy) |
| `VITE_PROXY_TARGET` | where the dev server proxies `/api` (default `http://127.0.0.1:8000`) |
| `VITE_WS_URL` | explicit WebSocket origin, if it differs from the API host |
| `VITE_DEV_PORT` | dev server port (default 5173) |

There is no API key in the frontend, on purpose.

## Pages

| Route | Contents |
| --- | --- |
| `/` | Dashboard: risk gauge, device status, live metric cards with sparklines, combined chart, insights |
| `/sensors`, `/sensors/:key` | channel grid and per-sensor detail (live value, history, min/max/mean, trend, health, anomalies, interpretation) |
| `/analytics` | trends, moving averages, correlations, observations, comparisons |
| `/risk` | score breakdown with per-factor points, reasons, reducing factors, anomalies, recommendations |
| `/predictions` | forecast over 15/30/60/120 min with confidence, method and horizon labelling |
| `/alerts` | alert centre with severity, timestamps, affected sensor, action, acknowledge/resolve, rule catalogue |
| `/device` | hardware telemetry, sensor availability, firmware configuration snippet and backend workers |
| `/chat` | AI analyst with suggested questions, citations, streaming, model status |
| `/settings` | configuration summary, feature flags, environment variables, data-truthfulness notes |

## Realtime and states

Live updates arrive over the WebSocket (`/api/v1/realtime/ws`) with an SSE
fallback; heavy refreshes are throttled so the UI stays responsive.

Every degraded state is explicit and readable — no empty charts, no `undefined`:

* backend unreachable → error card with retry
* no readings yet → "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data"
* stale reading → "stale" chips in the header and on the affected cards
* Ollama unavailable → model card says so; the rest of the dashboard is unaffected
* insufficient history → the prediction page says insufficient data and shows the sample count
* a dead sensor → the channel renders as missing rather than as a fabricated value

Responsive from mobile to wide desktop: collapsible drawer navigation, adaptive
grids and reduced chart heights on small screens.
