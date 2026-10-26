"""Esquemas de la API de catálogo (F1.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AllergenStatus = Literal["known", "partial", "unknown"]
SyncStatus = Literal["running", "success", "partial", "failed"]


class CategoryOut(BaseModel):
    """Sección o subcategoría del árbol de Mercadona."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    level: int
    is_food: bool
    sort_order: int
    children: list[CategoryOut] = Field(default_factory=list)


class ProductSummary(BaseModel):
    """Producto para listados y búsqueda."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    brand: str | None
    category_id: int
    category_name: str | None = None
    package_quantity_milli: int | None
    package_unit: str | None
    package_price_cents: int | None
    reference_price_cents: int | None
    reference_unit: str | None
    is_pack: bool
    approx_size: bool
    allergen_status: AllergenStatus
    thumbnail_url: str | None
    published: bool
    last_seen_at: datetime


class ProductDetail(ProductSummary):
    """Detalle de producto. Nunca expone `raw_json` ni datos internos de la API."""

    ean: str | None
    packaging: str | None
    is_estimated: bool
    selling_method: int | None
    unavailable_from: str | None
    first_seen_at: datetime


class ProductPage(BaseModel):
    """Listado paginado de productos."""

    items: list[ProductSummary]
    total: int
    limit: int
    offset: int


class SyncRunOut(BaseModel):
    """Estado de una ejecución de sincronización."""

    id: int
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None
    postal_code: str
    warehouse: str | None
    categories_ok: int
    categories_failed: int
    categories_total: int
    products_seen: int
    error: str | None
    progress: float = Field(ge=0.0, le=1.0)


class CatalogStatusOut(BaseModel):
    """Estado agregado que consume la pantalla de ajustes."""

    schema_ready: bool
    is_syncing: bool
    product_count: int
    category_count: int
    food_category_count: int
    last_sync: SyncRunOut | None
    last_success_at: datetime | None
    prices_captured_at: datetime | None
    postal_code: str
    warehouse: str | None


class SyncStartedOut(BaseModel):
    """Respuesta del POST que lanza una sync en segundo plano."""

    sync_run_id: int
    status: Literal["running"] = "running"
