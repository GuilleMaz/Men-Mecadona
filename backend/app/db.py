"""Motor, sesiones y base declarativa de SQLite.

La base vive en `%LOCALAPPDATA%\\Cesta\\cesta.db` (o en `CESTA_DATA_DIR`), fuera de
OneDrive, con WAL, integridad referencial y `busy_timeout`. Ver `PLAN.md` §9.4 y §16.3.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


def _apply_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Aplica los PRAGMA obligatorios en cada conexión."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
    finally:
        cursor.close()


def create_engine_for_url(database_url: str) -> Engine:
    """Crea un motor SQLite para una URL concreta, con los PRAGMA aplicados.

    Se usa tanto desde la app como desde Alembic, que puede recibir una URL
    temporal en los tests sin depender de los ajustes globales.
    """
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Crea un motor SQLite con los PRAGMA aplicados y el directorio de datos listo."""
    resolved = settings or get_settings()
    resolved.data_dir.mkdir(parents=True, exist_ok=True)
    return create_engine_for_url(resolved.database_url)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Motor del proceso."""
    return create_db_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Factoría de sesiones ligada al motor del proceso."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI que abre una sesión por petición."""
    with get_session_factory()() as session:
        yield session
