"""Test fixtures: isolated temp database, deterministic settings, TestClient."""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

#: The device key used by the suite is generated per run and never committed.
#: A literal test credential in the repository is a real risk: it is public, so
#: copying it into `.env` (or reusing it as the admin key) would hand an attacker
#: the deployment's credential. A random value cannot be reused by accident, and
#: the previously published literals are blacklisted in
#: ``app.core.security.WEAK_KEY_MARKERS``.
TEST_API_KEY = f"device-{secrets.token_urlsafe(24)}"
#: Same reasoning for the admin-scope credential used by the auth tests.
TEST_ADMIN_KEY = f"admin-{secrets.token_urlsafe(24)}"


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment() -> Iterator[None]:
    """Point the app at a throwaway SQLite file and disable background noise."""
    tmpdir = tempfile.mkdtemp(prefix="envmon-tests-")
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{Path(tmpdir, 'test.db').as_posix()}",
            "API_KEY": TEST_API_KEY,
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "WARNING",
            "BACKGROUND_WORKERS_ENABLED": "false",
            "OLLAMA_ENABLED": "false",
            "ANALYTICS_DEFAULT_HOURS": "6",
            "REQUIRE_AUTH_FOR_READS": "false",
        }
    )
    # Import after the environment is set so cached settings pick it up.
    from app.core.config import get_settings, get_risk_config

    get_settings.cache_clear()
    get_risk_config.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client(_isolated_environment: None) -> Iterator["object"]:
    from fastapi.testclient import TestClient

    from app.core.database import Base, reset_engine
    from app.main import app

    # Fresh schema per test: cheap on SQLite and keeps tests independent.
    from app.core.database import get_engine

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()


@pytest.fixture()
def session(client: object):
    from app.core.database import get_session_factory

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}


def sample_payload(**overrides) -> dict:
    payload = {
        "device_id": "arduino-r4-wifi-01",
        "sequence": 1,
        "firmware_version": "1.0.0",
        "ip_address": "192.168.1.42",
        "rssi": -58,
        "transmission_interval_ms": 15000,
        "temperature_c": 24.6,
        "humidity_pct": 52.0,
        "bmp_temperature_c": 24.4,
        "pressure_hpa": 1012.6,
        "rain_raw": 940.0,
        "ldr_raw": 700.0,
        "air_quality_raw": 205.0,
    }
    payload.update(overrides)
    return payload


def post_reading(client, **overrides):
    return client.post(
        "/api/v1/sensors/data",
        json=sample_payload(**overrides),
        headers=auth_headers(),
    )
