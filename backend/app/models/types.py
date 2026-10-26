"""Tipos reutilizables de SQLAlchemy."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Instante actual en UTC."""
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """Guarda `datetime` en UTC y los devuelve con `tzinfo`.

    SQLite no conserva la zona horaria. El decorador normaliza a UTC al escribir y
    vuelve a marcar el valor como UTC al leer, para que la API no publique fechas
    ambiguas.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
