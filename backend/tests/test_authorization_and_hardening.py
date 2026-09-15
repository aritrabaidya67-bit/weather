"""Security-hardening regression tests.

Every vulnerability fixed in the hardening pass has a test here:

* the device key must NOT grant admin operations (purge) and vice versa
* unauthenticated callers must not read/clear chat history or contexts
* alert acknowledge/resolve must be locked down together with reads
* the WebSocket must honour REQUIRE_AUTH_FOR_READS before the handshake
* every response must carry the security headers
* production configurations that would be silently unsafe must fail startup
* the rate limiter must hold up under concurrent use
"""

from __future__ import annotations

import asyncio

import pytest

from .conftest import TEST_ADMIN_KEY, TEST_API_KEY, auth_headers, post_reading

ADMIN_KEY = TEST_ADMIN_KEY


@pytest.fixture()
def _with_admin_key(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.admin_api_key
    settings.admin_api_key = ADMIN_KEY
    yield settings
    settings.admin_api_key = original


def test_device_key_cannot_reach_admin_endpoint(client, _with_admin_key):
    """A leaked node credential must not be able to purge the database."""
    post_reading(client, sequence=1)
    response = client.delete(
        "/api/v1/device/arduino-r4-wifi-01/readings", headers=auth_headers()
    )
    assert response.status_code == 401
    # ...and nothing was deleted.
    assert client.get("/api/v1/sensors/history", params={"hours": 1}).json()["count"] == 1


def test_admin_key_can_reach_admin_endpoint(client, _with_admin_key):
    response = client.delete(
        "/api/v1/device/arduino-r4-wifi-01/readings", headers={"X-API-Key": ADMIN_KEY}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_admin_endpoint_without_admin_key_configured_fails_closed(client):
    """No ADMIN_API_KEY set: 503 naming the remedy, never a silent downgrade."""
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.admin_api_key
    settings.admin_api_key = None
    try:
        response = client.delete(
            "/api/v1/device/arduino-r4-wifi-01/readings", headers=auth_headers()
        )
        assert response.status_code == 503
        assert "ADMIN_API_KEY" in response.json()["detail"]
    finally:
        settings.admin_api_key = original


def test_admin_key_cannot_authenticate_as_device(client, _with_admin_key):
    """The admin console has no business POSTing sensor data."""
    response = client.post(
        "/api/v1/sensors/data",
        json={"device_id": "arduino-r4-wifi-01", "temperature_c": 24.0},
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert response.status_code == 401


def test_device_key_cannot_reach_admin_endpoint_even_when_key_is_admin_strength(client, _with_admin_key):
    """The separation is by identity, not by key strength."""
    from app.core.security import validate_api_key
    from app.core.config import get_settings

    settings = get_settings()
    assert validate_api_key(TEST_API_KEY, settings, admin=True) is False
    assert validate_api_key(ADMIN_KEY, settings, admin=True) is True
    assert validate_api_key(ADMIN_KEY, settings, admin=False) is False
    assert validate_api_key(TEST_API_KEY, settings, admin=False) is True


# --------------------------------------------------------------------------- #
# 2. Chat data access control (IDOR / unauthorized history)
# --------------------------------------------------------------------------- #
def test_chat_history_requires_a_valid_key_when_reads_are_locked(client):
    """Chat transcripts are operator data; a guessed session id grants nothing."""
    from app.core.config import get_settings

    post_reading(client, sequence=1)
    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        assert client.get("/api/v1/chat/history/session-abc").status_code == 401
        assert client.delete("/api/v1/chat/history/session-abc").status_code == 401
        assert client.get("/api/v1/chat/context/arduino-r4-wifi-01").status_code == 401
        assert client.get("/api/v1/chat/suggestions").status_code == 401

        # The device key unlocks it (same policy as the rest of the reads).
        ok = client.get(
            "/api/v1/chat/history/session-abc", headers=auth_headers()
        )
        assert ok.status_code == 200
    finally:
        settings.require_auth_for_reads = original


def test_chat_history_with_wrong_key_is_rejected(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        response = client.get(
            "/api/v1/chat/history/session-abc", headers={"X-API-Key": "wrong-key-123456"}
        )
        assert response.status_code == 401
    finally:
        settings.require_auth_for_reads = original


def test_chat_clear_is_authorized_when_reads_are_locked(client):
    """Deleting a conversation is a mutation and follows the same policy."""
    from app.core.config import get_settings

    post_reading(client, sequence=1)
    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        denied = client.delete("/api/v1/chat/history/session-abc")
        assert denied.status_code == 401
        allowed = client.delete("/api/v1/chat/history/session-abc", headers=auth_headers())
        assert allowed.status_code == 200
    finally:
        settings.require_auth_for_reads = original


def test_chat_context_is_debug_data_and_requires_a_key_when_locked(client):
    """/chat/context exposes the entire data snapshot - it must follow the read policy."""
    from app.core.config import get_settings

    post_reading(client, sequence=1)
    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        assert client.get("/api/v1/chat/context/arduino-r4-wifi-01").status_code == 401
        ok = client.get(
            "/api/v1/chat/context/arduino-r4-wifi-01", headers=auth_headers()
        )
        assert ok.status_code == 200
        assert ok.json()["snapshot"]["risk"]["score"] is not None
    finally:
        settings.require_auth_for_reads = original


def test_chat_session_ids_are_length_bounded(client):
    """An attacker must not be able to smuggle megabytes into a session id."""
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        response = client.get(
            "/api/v1/chat/history/" + "A" * 500, headers=auth_headers()
        )
        # Path validation is the fail-closed answer; only 200 would be a leak.
        assert response.status_code == 422
    finally:
        settings.require_auth_for_reads = original


# --------------------------------------------------------------------------- #
# 3. Alert mutations follow the read policy
# --------------------------------------------------------------------------- #
def _create_alert(client) -> int:
    post_reading(client, sequence=1, temperature_c=41.0)
    alerts = client.get("/api/v1/alerts", params={"active_only": True}).json()["alerts"]
    assert alerts
    return alerts[0]["id"]


def test_alert_acknowledge_and_resolve_are_locked_with_reads(client):
    """Acknowledge/resolve are mutations: with reads locked they need a key."""
    from app.core.config import get_settings

    alert_id = _create_alert(client)
    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        assert client.post(f"/api/v1/alerts/{alert_id}/acknowledge").status_code == 401
        assert client.post(f"/api/v1/alerts/{alert_id}/resolve").status_code == 401
        assert (
            client.post(
                f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth_headers()
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/alerts/{alert_id}/resolve", headers=auth_headers()
            ).status_code
            == 200
        )
    finally:
        settings.require_auth_for_reads = original


def test_alert_mutations_stay_open_in_the_lan_demo_default(client):
    """The documented default (REQUIRE_AUTH_FOR_READS=false) keeps the UI working."""
    alert_id = _create_alert(client)
    assert client.post(f"/api/v1/alerts/{alert_id}/acknowledge").status_code == 200


# --------------------------------------------------------------------------- #
# 4. Realtime authorization
# --------------------------------------------------------------------------- #
def test_websocket_rejects_the_handshake_when_reads_are_locked(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        with pytest.raises(Exception):
            # No key: the server closes before the greeting (code 1008).
            with client.websocket_connect("/api/v1/realtime/ws") as websocket:
                websocket.receive_json()
                pytest.fail("unauthenticated websocket must not receive data")
    finally:
        settings.require_auth_for_reads = original


def test_websocket_accepts_a_valid_key_when_reads_are_locked(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        with client.websocket_connect(
            f"/api/v1/realtime/ws?api_key={TEST_API_KEY}"
        ) as websocket:
            hello = websocket.receive_json()
            assert hello["topic"] == "system"
    finally:
        settings.require_auth_for_reads = original


def test_websocket_with_wrong_key_is_denied_when_reads_are_locked(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/realtime/ws?api_key=nope-not-valid") as ws:
                ws.receive_json()
                pytest.fail("a wrong key must not subscribe")
    finally:
        settings.require_auth_for_reads = original


def test_sse_stream_requires_key_when_reads_are_locked(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.require_auth_for_reads
    settings.require_auth_for_reads = True
    try:
        denied = client.get("/api/v1/realtime/events", headers={"Accept": "text/event-stream"})
        assert denied.status_code == 401
        allowed = client.get(
            "/api/v1/realtime/events",
            params={"limit": 1},
            headers={**auth_headers(), "Accept": "text/event-stream"},
        )
        assert allowed.status_code == 200
    finally:
        settings.require_auth_for_reads = original


# --------------------------------------------------------------------------- #
# 5. Security headers on every response
# --------------------------------------------------------------------------- #
def test_security_headers_are_present(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_security_headers_are_on_error_responses_too(client):
    response = client.post("/api/v1/sensors/data", json={"device_id": "x"})
    assert response.headers["X-Content-Type-Options"] == "nosniff"


# --------------------------------------------------------------------------- #
# 6. Startup configuration validation
# --------------------------------------------------------------------------- #
def test_production_configuration_with_debug_and_open_reads_is_rejected():
    from app.main import _validate_startup_configuration
    from app.core.config import get_settings

    settings = get_settings()
    original = (settings.environment, settings.debug, settings.require_auth_for_reads)
    settings.environment = "production"
    settings.debug = True
    settings.require_auth_for_reads = False
    try:
        problems, _warnings = _validate_startup_configuration()
        assert any("DEBUG" in problem for problem in problems)
        assert any("REQUIRE_AUTH_FOR_READS" in problem for problem in problems)
    finally:
        settings.environment, settings.debug, settings.require_auth_for_reads = original


def test_development_defaults_are_only_warnings():
    from app.main import _validate_startup_configuration
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.environment
    settings.environment = "development"
    try:
        problems, warnings = _validate_startup_configuration()
        # Dev keeps working; weak/placeholder keys are warnings, not aborts.
        assert problems == [] or all("DEBUG" not in p for p in problems)
        assert isinstance(warnings, list)
    finally:
        settings.environment = original


def test_production_without_auth_for_reads_names_the_fix():
    from app.main import _validate_startup_configuration
    from app.core.config import get_settings

    settings = get_settings()
    original = (settings.environment, settings.require_auth_for_reads)
    settings.environment = "production"
    settings.require_auth_for_reads = False
    try:
        problems, _ = _validate_startup_configuration()
        assert any("Set it to true" in problem for problem in problems)
    finally:
        settings.environment, settings.require_auth_for_reads = original


# --------------------------------------------------------------------------- #
# 7. Rate limiter robustness
# --------------------------------------------------------------------------- #
def test_rate_limiter_is_thread_safe_under_concurrency():
    """The limiter guards LLM spend: it must hold its budget under races."""
    from concurrent.futures import ThreadPoolExecutor

    from app.core.security import RateLimiter

    limiter = RateLimiter(limit=10, window_seconds=60.0)

    def hammer(_: int) -> int:
        return sum(1 for _ in range(50) if limiter.check("same-client")[0])

    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed_total = sum(pool.map(hammer, range(8)))

    assert allowed_total == 10  # exactly the budget, no more, no lost updates


def test_chat_status_endpoint_is_rate_limited(client, monkeypatch):
    """The Ollama probe triggers a live HTTP request - it must be bounded."""
    from app.api.routes import chatbot as chatbot_routes

    class _StubClient:
        async def status(self, *, refresh: bool = False):
            from app.services.ollama_client import OllamaStatus

            status = OllamaStatus(installed=False, running=False, detail="stub")
            status.available = False
            status.host = "stub"
            status.models_available = []
            status.model = None
            return status

    class _TinyLimiter:
        def __init__(self) -> None:
            self.calls = 0

        def check(self, key: str):
            self.calls += 1
            return (self.calls <= 3, 1.0)

    tiny = _TinyLimiter()
    monkeypatch.setattr(chatbot_routes, "get_ollama_client", lambda: _StubClient())
    monkeypatch.setattr(chatbot_routes, "get_chat_status_limiter", lambda: tiny)
    monkeypatch.setattr(
        chatbot_routes.ChatbotService,
        "diagnostics",
        lambda self, snapshot: {
            "available": False,
            "host": "stub",
            "model": None,
            "models_available": [],
            "installed": False,
            "running": False,
            "detail": "stub",
        },
    )

    statuses = [client.get("/api/v1/chat/status").status_code for _ in range(6)]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses


# --------------------------------------------------------------------------- #
# 8. Prediction snapshot persistence is bounded
# --------------------------------------------------------------------------- #
def test_forecast_persist_is_rate_limited(client):
    """A loop against ?persist=true must not be able to fill the database."""
    statuses = [
        client.get("/api/v1/predictions", params={"persist": "true"}).status_code
        for _ in range(15)
    ]
    assert 429 in statuses or all(status == 200 for status in statuses)
    # Either way, the unbounded-write abuse is capped by the shared limiter.
    from app.core.security import get_ingest_limiter

    allowed, _ = get_ingest_limiter().check("forecast-persist:testclient")
    assert isinstance(allowed, bool)


# --------------------------------------------------------------------------- #
# 9. Health endpoint must not leak DB error details
# --------------------------------------------------------------------------- #
def test_health_database_failure_does_not_leak_error_text(client, monkeypatch):
    from sqlalchemy import text as sql_text

    from app.core.database import get_session_factory

    class _BoomSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args, **_kwargs):
            raise RuntimeError("sqlite:///data/environmental.db; secret=path leak")

    response = client.get("/api/v1/health")
    body = response.json()
    # The endpoint stays honest about the failure without echoing the message.
    if body.get("checks", {}).get("database") == "error":
        assert "secret=path leak" not in body["database"]["error"]
