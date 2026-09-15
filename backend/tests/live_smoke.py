"""Live smoke test - runs against an ALREADY RUNNING backend.

    # terminal 1
    cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    # terminal 2
    cd backend && python tests/live_smoke.py

Why this exists next to `pytest`: the test suite runs in-process against a
throwaway SQLite file with Ollama and the background workers disabled. That
proves the logic but not the *deployment*: a real socket, real CORS middleware,
real WebSocket handshake, real background workers, the real `.env`, and the
user's actual Ollama installation. This script exercises those.

It is deliberately NOT named `test_*.py`, so `pytest` does not collect it and it
can never silently become part of the offline suite.

The device API key is read from `.env` and never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000")
API = f"{BASE}/api/v1"

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label}{' - ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' - ' + detail if detail else ''}")
    return condition


def _headers(raw: object) -> dict[str, str]:
    """Lower-cased response headers.

    HTTP/1.1 header names are case-insensitive and h11 (uvicorn's protocol
    implementation) transmits them lower-cased, so ``dict(response.headers)``
    yields ``content-type``, never ``Content-Type``. Normalising here means every
    check can address headers by their canonical lower-case name instead of
    depending on the casing a particular server happens to emit.
    """
    return {str(key).lower(): str(value) for key, value in dict(raw).items()}  # type: ignore[arg-type]


def http(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    key: str | None = None,
    origin: str | None = None,
    raw: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict | str, dict]:
    url = path if path.startswith("http") else f"{API}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if raw is not None:
        data = raw.encode()
        headers["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if key:
        headers["X-API-Key"] = key
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode()
            try:
                parsed: dict | str = json.loads(payload)
            except json.JSONDecodeError:
                parsed = payload
            return response.status, parsed, _headers(response.headers)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = payload
        return exc.code, parsed, _headers(exc.headers)
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc), {}


def ws_probe(base_url: str, path: str, timeout: float = 8.0) -> tuple[str, str | None]:
    """Perform a raw WebSocket handshake and read one server frame.

    Implemented on ``socket`` + hashlib/base64/struct so it has no third-party
    dependency, and unlike a mocked client it exercises the real upgrade path.
    """
    import base64
    import hashlib
    import socket
    import struct
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    key = base64.b64encode(os.urandom(16)).decode()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        return f"connection failed: {exc}", None
    with sock:
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode())
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            try:
                chunk = sock.recv(4096)
            except OSError as exc:
                return f"handshake read failed: {exc}", None
            if not chunk:
                break
            buffer += chunk
        head, _, rest = buffer.partition(b"\r\n\r\n")
        status = head.split(b"\r\n")[0].decode(errors="replace")
        if "101" not in status:
            return status, None
        # The RFC6455 accept hash must match the key we sent.
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expected.lower() not in head.decode(errors="replace").lower():
            return f"{status} (Sec-WebSocket-Accept mismatch)", None
        try:
            sock.settimeout(6.0)
            frame_data = rest or sock.recv(8192)
        except OSError:
            return status, None
        if len(frame_data) < 2:
            return status, None
        length = frame_data[1] & 0x7F
        index = 2
        if length == 126:
            length = struct.unpack(">H", frame_data[index:index + 2])[0]
            index += 2
        elif length == 127:
            length = struct.unpack(">Q", frame_data[index:index + 8])[0]
            index += 8
        return status, frame_data[index:index + length].decode(errors="replace")


def load_device_key() -> str:
    """Read the device API key without ever echoing it.

    Precedence: ``SMOKE_API_KEY`` (run against an isolated instance launched with
    its own key), then ``API_KEY`` from the environment, then ``backend/.env``.
    """
    explicit = os.environ.get("SMOKE_API_KEY") or os.environ.get("API_KEY")
    if explicit:
        return explicit
    for candidate in (Path(".env"), Path(__file__).resolve().parents[1] / ".env"):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("API_KEY", "")


FIXTURE = {
    "device_id": "live-smoke-node",
    "firmware_version": "1.0.0",
    "ip_address": "192.168.1.77",
    "rssi": -57,
    "transmission_interval_ms": 15000,
    "temperature_c": 24.6,
    "humidity_pct": 52.0,
    "bmp_temperature_c": 24.4,
    "pressure_hpa": 1012.6,
    "rain_raw": 940.0,
    "ldr_raw": 700.0,
    "air_quality_raw": 205.0,
}


def reading(**overrides) -> dict:
    payload = dict(FIXTURE)
    payload.update(overrides)
    return payload


def main() -> int:
    key = load_device_key()
    print(f"Live smoke test against {BASE}")
    print(f"Device key loaded from .env: {'yes' if key else 'NO - device endpoints will 503'}")
    print()

    # ---------------------------------------------------------------- liveness
    print("== Reachability and health")
    status, body, _ = http("GET", "/health")
    check("GET /health is 200", status == 200, str(status))
    check("health reports status ok", isinstance(body, dict) and body.get("status") == "ok", str(body)[:160])
    check("database check ok", isinstance(body, dict) and body.get("checks", {}).get("database") == "ok")
    check("uptime is reported", isinstance(body, dict) and body.get("uptime_seconds") is not None)

    status, meta, _ = http("GET", "/meta")
    check("GET /meta is 200", status == 200)
    check("meta lists 6 channels", isinstance(meta, dict) and len(meta.get("channels", [])) == 6)
    check("meta lists 5 risk levels", isinstance(meta, dict) and len(meta.get("risk_model", {}).get("levels", [])) == 5)
    check(
        "risk weights sum to 100",
        isinstance(meta, dict) and sum(meta.get("risk_model", {}).get("weights", {}).values()) == 100,
    )
    check(
        "sensor registry documents the AM2302/DHT22 sensor",
        isinstance(meta, dict)
        and any("AM2302" in (s.get("description") or "") for s in meta.get("sensors", [])),
    )
    check(
        "no 'DHT12' claim remains in the sensor registry",
        isinstance(meta, dict) and "DHT12" not in json.dumps(meta.get("sensors", [])),
    )
    check(
        "meta recommends a LAN (non-loopback) backend URL",
        isinstance(meta, dict)
        and meta.get("recommended_backend_url") is not None
        and "127.0.0.1" not in meta["recommended_backend_url"],
        str(meta.get("recommended_backend_url") if isinstance(meta, dict) else ""),
    )
    print(f"        recommended_backend_url = {meta.get('recommended_backend_url') if isinstance(meta, dict) else '?'}")
    print(f"        local_addresses = {meta.get('local_addresses') if isinstance(meta, dict) else '?'}")

    status, body, _ = http("GET", "/status")
    check("GET /status is 200", status == 200)

    # ------------------------------------------------------------------- auth
    print("\n== Authentication")
    status, body, _ = http("POST", "/sensors/data", body=reading())
    check("ingest without a key is 401", status == 401, str(status))
    status, _, _ = http("POST", "/sensors/data", body=reading(), key="wrong-key")
    check("ingest with a wrong key is 401", status == 401, str(status))
    status, _, _ = http("GET", "/device/live-smoke-node/risk-state")
    check("risk-state without a key is 401", status == 401, str(status))
    status, _, _ = http("DELETE", "/device/live-smoke-node/readings")
    check("destructive purge without a key is 401", status == 401, str(status))

    # ------------------------------------------------------------------- CORS
    print("\n== CORS policy (live middleware)")
    status, _, headers = http("GET", "/health", origin="http://localhost:5173")
    check("configured origin is allowed", headers.get("access-control-allow-origin") == "http://localhost:5173")
    status, _, headers = http("GET", "/health", origin="https://evil.example.com")
    check("unlisted origin is refused", "access-control-allow-origin" not in headers)
    status, _, headers = http("GET", "/health", origin="http://192.168.1.99:5173")
    check("LAN origin refused while CORS_ALLOW_LAN_ORIGINS=false", "access-control-allow-origin" not in headers)
    status, _, _ = http(
        "OPTIONS",
        "/sensors/data",
        origin="http://localhost:5173",
    )
    check("preflight does not error", status in {200, 204, 405}, str(status))

    # -------------------------------------------------------------- ingestion
    print("\n== CASE 1: normal sensor data")
    status, body, _ = http("POST", "/sensors/data", body=reading(sequence=1), key=key)
    check("ingest with the real key is 200", status == 200, f"{status} {str(body)[:120]}")
    if status != 200:
        print("\nCannot continue without ingestion. Aborting.")
        return report()
    check("payload accepted", body.get("accepted") is True)
    check("a reading id was assigned", body.get("reading_id") is not None)
    check("a risk score was computed", isinstance(body.get("risk_score"), (int, float)))
    check("the risk level is 1..5", 1 <= int(body.get("risk_level", 0)) <= 5)
    check("no channels missing", body.get("missing_metrics") == [])
    check("response carries server_time for the firmware clock",
          isinstance(body.get("server_time"), str) and "T" in body["server_time"])
    check("response stays small enough for the UNO R4", len(json.dumps(body)) < 3000,
          f"{len(json.dumps(body))} bytes")

    status, latest, _ = http("GET", "/sensors/latest", key=key)
    check("the reading is stored and served back", status == 200 and latest.get("temperature_c") == 24.6)

    print("\n== CASE 2-5: single-factor excursions")
    # Each excursion is measured against the *calm baseline*, never against
    # another excursion. The model weights factors differently (temperature 20,
    # humidity 15, air quality 30), so "humidity must score above temperature"
    # was an expectation the engine never made - it happened to hold early on
    # and then went red as soon as stored-history escalation reordered things.
    calm = body.get("risk_score") or 0.0

    def factor(key: str) -> dict | None:
        """Current risk contributions after the last ingested payload."""
        fresh = http("GET", "/risk/current")[1]
        return next((c for c in fresh.get("contributions", []) if c["key"] == key), None)

    status, hot, _ = http("POST", "/sensors/data", body=reading(sequence=2, temperature_c=39.5), key=key)
    check("high temperature is accepted", status == 200)
    current = http("GET", "/risk/current")[1]
    check("high temperature raises the score above the calm baseline",
          hot["risk_score"] > calm, f"{hot['risk_score']} vs calm {calm}")
    check("the contribution total equals the score (the explanation adds up)",
          abs(sum(c["points"] for c in current.get("contributions", [])) - current["score"]) < 0.11,
          f"{sum(c['points'] for c in current.get('contributions', []))} vs {current['score']}")
    temp_factor = factor("temperature")
    check("the temperature factor is named and scored",
          temp_factor is not None and temp_factor["points"] > 0)
    check("temperature points respect the configured weight",
          temp_factor is not None and temp_factor["points"] <= temp_factor["max_points"],
          str(temp_factor))

    status, humid, _ = http("POST", "/sensors/data", body=reading(sequence=3, humidity_pct=93.0), key=key)
    check("high humidity is accepted", status == 200)
    check("high humidity raises the score above the calm baseline",
          humid["risk_score"] > calm, f"{humid['risk_score']} vs calm {calm}")
    humid_factor = factor("humidity")
    check("the humidity factor is named and scored",
          humid_factor is not None and humid_factor["points"] > 0, str(humid_factor))

    status, polluted, _ = http("POST", "/sensors/data", body=reading(sequence=4, air_quality_raw=950.0), key=key)
    check("poor air quality is accepted", status == 200)
    check("poor air quality raises the score above the calm baseline",
          polluted["risk_score"] > calm, f"{polluted['risk_score']} vs calm {calm}")
    air_factor = factor("air_quality")
    check("the air-quality factor is named and scored",
          air_factor is not None and air_factor["points"] > 0, str(air_factor))

    # CASE 14: multiple simultaneous anomalies compose. The model is additive, so
    # a payload that is bad on two axes cannot score below either single-factor
    # excursion at the same instant.
    status, both, _ = http(
        "POST", "/sensors/data",
        body=reading(sequence=45, temperature_c=39.5, humidity_pct=93.0, air_quality_raw=950.0),
        key=key,
    )
    check("multiple simultaneous anomalies are accepted", status == 200)
    check("combined anomalies score at least as high as each single excursion",
          both["risk_score"] >= max(hot["risk_score"], humid["risk_score"], polluted["risk_score"]),
          f"{both['risk_score']} vs {max(hot['risk_score'], humid['risk_score'], polluted['risk_score'])}")
    check("every active factor is reported in the explanation",
          sum(1 for c in http("GET", "/risk/current")[1].get("contributions", []) if c["points"] > 0) >= 3)

    status, wet, _ = http("POST", "/sensors/data", body=reading(sequence=5, rain_raw=110.0, air_quality_raw=200.0), key=key)
    check("rain is detected and raised risk", status == 200 and wet["risk_score"] > 0)
    latest = http("GET", "/sensors/latest", key=key)[1]
    check("wetness is derived from the raw ADC", latest.get("rain_pct", 0) > 80, str(latest.get("rain_pct")))
    check("rain status is derived by the backend", latest.get("rain_status") in {"rain", "heavy rain"}, str(latest.get("rain_status")))

    print("\n== CASE 7: sensor unavailable")
    partial = reading(sequence=6)
    partial.pop("rain_raw")
    partial.pop("air_quality_raw")
    status, body, _ = http("POST", "/sensors/data", body=partial, key=key)
    check("partial payload is still accepted", status == 200)
    check("missing channels are reported", set(body.get("missing_metrics", [])) == {"rain", "air_quality"},
          str(body.get("missing_metrics")))
    latest = http("GET", "/sensors/latest", key=key)[1]
    check("a missing channel is null, not invented", latest.get("rain_pct") is None)
    check("healthy channels are unaffected", latest.get("temperature_c") is not None)

    print("\n== CASE 9: malformed transport payloads")
    for label, kwargs in (
        ("invalid JSON", {"raw": "{not json"}),
        ("JSON array", {"raw": "[1,2,3]"}),
        ("wrong types", {"body": {"temperature_c": {"nested": 1}}}),
    ):
        status, _, _ = http("POST", "/sensors/data", key=key, **kwargs)
        check(f"{label} is rejected with 422", status == 422, str(status))

    print("\n== CASE 12/13: key policy")
    status, _, _ = http("POST", "/sensors/data", body=reading(sequence=99), key="dev-local-key-change-me")
    check("the old development key is rejected", status == 401, str(status))

    # ------------------------------------------------------------------ Ollama
    print("\n== Ollama integration (existing installation, never modified)")
    status, chat_status, _ = http("GET", "/chat/status")
    check("GET /chat/status is 200", status == 200, str(status))
    print(f"        installed={chat_status.get('installed')} running={chat_status.get('running')} "
          f"model={chat_status.get('model')} models={chat_status.get('models_available')}")
    if chat_status.get("running"):
        check("a model is selected while Ollama runs", bool(chat_status.get("model")))
    else:
        check("Ollama is reported as not running", chat_status.get("running") is False)
        check("the reason is explained to the user", bool(chat_status.get("detail")))
        check("not running implies not available", chat_status.get("available") is False)
        check(
            "the model list still comes from the existing install on disk",
            isinstance(chat_status.get("models_available"), list)
            and len(chat_status["models_available"]) > 0,
            str(chat_status.get("models_available")),
        )

    status, answer, _ = http("POST", "/chat", body={"message": "What is the current risk?"}, timeout=200)
    check("chat answers over HTTP", status == 200, str(status))
    if status == 200:
        check("the answer is non-empty", bool(answer.get("answer")))
        check("citations are attached", isinstance(answer.get("citations"), list) and answer["citations"])
        if chat_status.get("running"):
            check("the model was used", answer.get("model") is not None and not answer.get("fallback_used"))
        else:
            check("the rule-based analyst answered instead", answer.get("fallback_used") is True)
            check("the degradation is disclosed", bool(answer.get("warning")))
        check("grounding is stated", answer.get("grounding") in {"live_data", "historical_data", "analysis_only"},
              str(answer.get("grounding")))

    status, ctx, _ = http("GET", "/chat/context/live-smoke-node")
    check("the exact model context is inspectable", status == 200 and ctx.get("context_chars", 0) > 0)
    check("the context fits the configured budget",
          status == 200 and ctx.get("context_chars", 0) <= ctx.get("context_limit", 0))

    # ---------------------------------------------------------------- realtime
    print("\n== Realtime")
    status, rt, _ = http("GET", "/realtime/status")
    check("GET /realtime/status is 200", status == 200)

    # A real RFC6455 handshake, done with the standard library so the probe
    # genuinely runs. (It used to print "websocket-client present" while
    # asserting a hardcoded True - the library is not installed, so that line
    # claimed a verification that never happened.)
    ws_status, ws_frame = ws_probe(
        BASE, "/api/v1/realtime/ws?topics=reading,risk,alert&last_event_id=0"
    )
    check("WebSocket handshake upgrades (101 Switching Protocols)",
          "101" in ws_status, ws_status)
    check("WebSocket delivers a server frame after connecting",
          ws_frame is not None and '"topic"' in ws_frame, str(ws_frame)[:120])

    status, sse, headers = http("GET", "/realtime/events?topics=reading&limit=1", timeout=15)
    check("SSE stream responds 200", status == 200, str(status))
    check("SSE content type is text/event-stream",
          "text/event-stream" in headers.get("content-type", ""),
          headers.get("content-type", ""))
    check("SSE replays at least one event", "event:" in str(sse), str(sse)[:120])

    # ------------------------------------------------------------------- reads
    print("\n== Dashboard read endpoints")
    for label, path in (
        ("overview", "/analytics/overview"),
        ("observations", "/analytics/observations"),
        ("trends", "/analytics/trends"),
        ("classification", "/analytics/classification"),
        ("compare", "/analytics/compare"),
        ("history", "/sensors/history"),
        ("aggregate", "/sensors/aggregate"),
        ("anomalies", "/sensors/anomalies"),
        ("baseline", "/sensors/baseline"),
        ("sensor health", "/sensors/health"),
        ("catalog", "/sensors/catalog"),
        ("risk model", "/risk/model"),
        ("risk analysis", "/risk/analysis"),
        ("predictions", "/predictions"),
        ("prediction accuracy", "/predictions/accuracy"),
        ("alerts", "/alerts"),
        ("alert rules", "/alerts/rules"),
        ("device list", "/device/list"),
        ("workers", "/system/workers"),
        ("chat suggestions", "/chat/suggestions"),
    ):
        status, _, _ = http("GET", path)
        check(f"GET {path} ({label}) is 200", status == 200, str(status))

    status, summary, _ = http("GET", "/analytics/summary/day")
    check("GET /analytics/summary/day is 200", status == 200, str(status))

    # -------------------------------------------------------------- prediction
    print("\n== Prediction honesty with sparse live data")
    status, prediction, _ = http("GET", "/predictions")
    check("GET /predictions is 200", status == 200)
    if status == 200 and not prediction.get("data_sufficient"):
        check("insufficient history is stated, not hidden", bool(prediction.get("notes")))
        check(
            "no metric invents a value",
            all(m.get("predicted_value") is None for m in prediction.get("metrics", {}).values()),
        )
        check(
            "no metric invents a confidence",
            all(m.get("confidence") == 0.0 for m in prediction.get("metrics", {}).values()),
        )
        print(f"        samples_used={prediction.get('samples_used')} "
              f"(reported honestly, current values still available)")
        check(
            "current values are still reported alongside the missing forecast",
            all(m.get("current_value") is not None for m in prediction.get("metrics", {}).values()),
        )

    # ------------------------------------------------------------- risk state
    print("\n== Risk-state contract for the Arduino LEDs/buzzer")
    status, state, _ = http("GET", "/device/live-smoke-node/risk-state", key=key)
    check("risk-state accepts the real key", status == 200, str(status))
    for field in ("risk_level", "risk_label", "led_index", "buzzer_pattern", "stale", "alerts_active", "server_time"):
        check(f"risk-state includes {field}", isinstance(state, dict) and field in state)
    check("led_index mirrors the risk level", state.get("led_index") == state.get("risk_level"))
    check("buzzer pattern is one of the four implemented patterns",
          state.get("buzzer_pattern") in {"silent", "single_short_60s", "double_short_30s", "critical_alarm"},
          str(state.get("buzzer_pattern")))

    # ------------------------------------------------------------------ cleanup
    print("\n== Cleanup (live database left as found)")
    status, purged, _ = http("DELETE", "/device/live-smoke-node/readings", key=key)
    check("smoke-test readings purged", status == 200 and purged.get("deleted_readings", 0) > 0,
          str(purged))
    history = http("GET", "/sensors/history?hours=24&device_id=live-smoke-node")[1]
    check("no smoke-test readings remain", history.get("count") == 0, str(history.get("count")))

    return report()


def report() -> int:
    print()
    print("=" * 68)
    print(f"Live smoke test: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFailures:")
        for item in FAILED:
            print(f"  - {item}")
        return 1
    print("All live checks passed against the running backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
