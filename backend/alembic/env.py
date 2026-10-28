"""Entorno de migraciones de Cesta.

La URL se toma de `-x`/`sqlalchemy.url` si está definida (tests) o de `Settings`
en caso contrario. `render_as_batch=True` permite que SQLite evolucione tablas
con ALTER TABLE limitado. Ver `PLAN.md` §9.4 y §16.3.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.db import create_engine_for_url  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Genera SQL sin conectarse a la base de datos."""
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
    """Aplica las migraciones sobre SQLite con los PRAGMA de la app."""
    # Las tablas se recrean con batch_alter_table; con las claves foráneas
    # activas, SQLite rechaza el DROP de la tabla antigua si tiene filas
    # referenciadas. La app vuelve a activarlas en cada conexión.
    connectable = create_engine_for_url(_database_url(), foreign_keys=False)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
