"""Origen y frescura de los precios usados por Cesta (F5.1).

La app siempre lee de su copia local de SQLite. La copia solo es apta para
precios actuales si la última sincronización completa corresponde al CP 22002 y
al almacén 4389. Una sync fallida posterior no borra la copia válida: sirve
para consultar y revalidar menús guardados, pero no para generar menús nuevos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE
from app.models.catalog import Product, SyncRun
from app.models.types import utcnow

PriceSource = Literal["current", "local_copy", "unavailable"]

_VALID_SYNC_STATUSES = ("success", "partial")
_FAILED_SYNC_STATUSES = ("failed", "running")


@dataclass(frozen=True, slots=True)
class PriceSourceStatus:
    """Diagnóstico reproducible del origen de los precios locales."""

    latest_attempt: SyncRun | None
    latest_completed: SyncRun | None
    latest_valid: SyncRun | None
    product_count: int
    prices_captured_at: datetime | None
    price_source: PriceSource
    using_local_copy: bool
    fallback_reason: str | None
    price_age_hours: int | None


def _is_expected_warehouse(run: SyncRun) -> bool:
    return run.postal_code == POSTAL_CODE and run.warehouse == EXPECTED_WAREHOUSE


def get_price_source_status(session: Session) -> PriceSourceStatus:
    """Resuelve si la copia local puede usarse para precios actuales."""
    latest_attempt = session.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
    latest_completed = session.scalar(
        select(SyncRun)
        .where(SyncRun.status.in_(_VALID_SYNC_STATUSES))
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    product_count = int(session.scalar(select(func.count()).select_from(Product)) or 0)
    prices_captured_at = session.scalar(select(func.max(Product.last_seen_at)))
    if not isinstance(prices_captured_at, datetime):
        prices_captured_at = None

    price_age_hours: int | None = None
    if prices_captured_at is not None:
        age = utcnow() - prices_captured_at
        price_age_hours = max(0, int(age.total_seconds() // 3600))

    latest_valid = (
        latest_completed
        if latest_completed is not None and _is_expected_warehouse(latest_completed)
        else None
    )

    if product_count == 0:
        return PriceSourceStatus(
            latest_attempt=latest_attempt,
            latest_completed=latest_completed,
            latest_valid=None,
            product_count=0,
            prices_captured_at=None,
            price_source="unavailable",
            using_local_copy=False,
            fallback_reason="El catálogo local está vacío.",
            price_age_hours=None,
        )

    if latest_completed is None:
        return PriceSourceStatus(
            latest_attempt=latest_attempt,
            latest_completed=None,
            latest_valid=None,
            product_count=product_count,
            prices_captured_at=prices_captured_at,
            price_source="unavailable",
            using_local_copy=False,
            fallback_reason="No hay una copia de precios completa.",
            price_age_hours=price_age_hours,
        )

    if latest_valid is None:
        return PriceSourceStatus(
            latest_attempt=latest_attempt,
            latest_completed=latest_completed,
            latest_valid=None,
            product_count=product_count,
            prices_captured_at=prices_captured_at,
            price_source="unavailable",
            using_local_copy=False,
            fallback_reason=(
                "La última copia es del CP "
                f"{latest_completed.postal_code} / almacén "
                f"{latest_completed.warehouse or 'sin confirmar'}; no se mezclan almacenes."
            ),
            price_age_hours=price_age_hours,
        )

    fallback_reason: str | None = None
    source: PriceSource = "current"
    if (
        latest_attempt is not None
        and latest_attempt.id > latest_valid.id
        and latest_attempt.status in _FAILED_SYNC_STATUSES
    ):
        source = "local_copy"
        fallback_reason = (
            latest_attempt.error
            or "La última sincronización no terminó; se usa la última copia válida."
        )

    return PriceSourceStatus(
        latest_attempt=latest_attempt,
        latest_completed=latest_completed,
        latest_valid=latest_valid,
        product_count=product_count,
        prices_captured_at=prices_captured_at,
        price_source=source,
        using_local_copy=source == "local_copy",
        fallback_reason=fallback_reason,
        price_age_hours=price_age_hours,
    )
