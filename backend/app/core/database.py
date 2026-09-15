"""Database engine, session factory and declarative base.

SQLite is used for local development because it needs no server, but every
query in the application goes through the repository layer and SQLAlchemy Core
expressions, so switching ``DATABASE_URL`` to PostgreSQL is a configuration
change rather than a rewrite.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import BACKEND_DIR, get_settings
from .logging import get_logger

logger = get_logger("app.database")


class UTCDateTime(TypeDecorator):
    """Timezone-safe datetime column.

    SQLite has no native timezone support and silently drops tzinfo, which would
    make aware/naive comparisons explode later. This type always stores naive UTC
    and always returns aware UTC, so the same code works on SQLite and PostgreSQL.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        aware = aware.astimezone(UTC)
        if dialect.name == "sqlite":
            return aware.replace(tzinfo=None)
        return aware

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _prepare_sqlite_path(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    raw_path = url.split("///", 1)[-1]
    if raw_path and raw_path != ":memory:":
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.resolve_database_url()
        _prepare_sqlite_path(url)
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False, "timeout": 15}
        _engine = create_engine(
            url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, _record) -> None:  # pragma: no cover
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        logger.info("database_engine_created", dialect=_engine.dialect.name)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def session_dependency() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background tasks and services."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def describe_database() -> dict[str, Any]:
    """Human readable summary of the active database connection (no secrets)."""
    engine = get_engine()
    url = engine.url
    return {
        "dialect": engine.dialect.name,
        "database": url.database,
        "driver": engine.dialect.driver,
        "tables": sorted(Base.metadata.tables.keys()),
    }


def run_migrations() -> None:
    """Apply every pending Alembic migration, or raise.

    Used when ``RUN_MIGRATIONS_ON_STARTUP=true``. A failure is fatal on purpose:
    serving requests against a half-migrated schema is worse than not starting.
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig

    ini_path = BACKEND_DIR / "alembic.ini"
    if not ini_path.exists():  # pragma: no cover - packaging mistake
        raise RuntimeError(f"alembic.ini not found at {ini_path}; cannot migrate.")
    alembic_config = AlembicConfig(str(ini_path))
    # The URL itself is resolved inside alembic/env.py from the app settings, so
    # migrations and the API can never target different databases.
    command.upgrade(alembic_config, "head")
    logger.info("database_migrations_applied", revision="head")


def init_db() -> None:
    """Prepare the schema: Alembic migrations, or ``create_all`` for development.

    Two deliberate paths:

    * ``RUN_MIGRATIONS_ON_STARTUP=true`` -> ``alembic upgrade head`` (production;
      upgrade path, downgrade available, no silent destructive change)
    * default -> ``Base.metadata.create_all`` (zero-setup development and tests),
      logged as such so the difference is never a surprise
    """
    from .. import models  # noqa: F401  (registers ORM classes)

    settings = get_settings()
    if settings.run_migrations_on_startup:
        run_migrations()
        return
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info(
        "database_initialised",
        tables=len(Base.metadata.tables),
        note=(
            "create_all (development default). Set RUN_MIGRATIONS_ON_STARTUP=true (or "
            "run `alembic upgrade head`) for a managed, upgradeable schema."
        ),
    )


def reset_engine() -> None:
    """Dispose the engine (used by tests to switch databases)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
