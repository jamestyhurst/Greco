"""Alembic environment — wires the migration runner to the Greco models and DB.

Run from the repo root (where alembic.ini lives):
    venv\\Scripts\\python -m alembic upgrade head     # apply pending migrations
    venv\\Scripts\\python -m alembic revision --autogenerate -m "describe change"
    venv\\Scripts\\python -m alembic stamp head       # mark existing DB as current
    venv\\Scripts\\python -m alembic history          # show migration history
    venv\\Scripts\\python -m alembic current          # show applied revision
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure the repo root is on sys.path so 'web' imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.db import _DB_URL          # the SQLite URL (or PostgreSQL URL in Phase 7)
from web.models import Base         # all ORM metadata lives here

# Override the placeholder URL in alembic.ini with the real one.
context.config.set_main_option("sqlalchemy.url", _DB_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL without a live DB connection (useful for review)."""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live DB connection."""
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
