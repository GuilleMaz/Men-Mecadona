"""Motor, sesiones y base declarativa de SQLite.

La base vive en `%LOCALAPPDATA%\\Cesta\\cesta.db` (o en `CESTA_DATA_DIR`), fuera de
OneDrive, con WAL, integridad referencial y `busy_timeout`. Ver `PLAN.md` §9.4 y §16.3.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


def _sqlite_pragmas(*, foreign_keys: bool = True) -> Callable[[Any, Any], None]:
    """Devuelve el listener que aplica los PRAGMA obligatorios en cada conexión."""

    def _apply(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA busy_timeout = 5000")
        finally:
            cursor.close()

    return _apply


def create_engine_for_url(database_url: str, *, foreign_keys: bool = True) -> Engine:
    """Crea un motor SQLite para una URL concreta, con los PRAGMA aplicados.

    Se usa tanto desde la app como desde Alembic, que puede recibir una URL
    temporal en los tests sin depender de los ajustes globales. Las migraciones
    que recrean tablas con ``batch_alter_table`` desactivan las claves foráneas
    durante la conexión de migración; la app siempre las activa.
    """
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _sqlite_pragmas(foreign_keys=foreign_keys))
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
