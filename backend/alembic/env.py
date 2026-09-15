"""Alembic environment - wired to the application's own configuration.

Key properties:

* the database URL comes from ``app.core.config`` (so ``DATABASE_URL`` in
  ``backend/.env`` is honoured and migrations and the API can never disagree)
* ``target_metadata`` is the real ORM metadata, so ``alembic revision
  --autogenerate`` produces a faithful diff
* ``render_as_batch`` is enabled for SQLite: dropping/altering a column on
  SQLite requires a table rebuild, and batch mode emits that correctly
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
from app import models  # noqa: F401  (registers every ORM class on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: The schema Alembic diffs against.
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL the application itself would use.

    ``ALEMBIC_DATABASE_URL`` overrides it for one invocation without touching the
    application settings (used by the migration tests and by operators running a
    migration against a specific database, e.g. a backup copy before a deploy).
    """
    import os

    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    return get_settings().resolve_database_url()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run the migrations against the configured database."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
