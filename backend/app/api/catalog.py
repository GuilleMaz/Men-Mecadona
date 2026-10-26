"""Endpoints de catálogo (F1.5): estado, sync, categorías y productos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.errors import ApiError
from app.config import POSTAL_CODE
from app.db import get_session
from app.models.catalog import Category, Product, SyncRun
from app.schemas.catalog import (
    CatalogStatusOut,
    CategoryOut,
    ProductDetail,
    ProductPage,
    ProductSummary,
    SyncRunOut,
    SyncStartedOut,
)
from app.services.catalog_sync import CatalogSyncService, SyncInProgressError

router = APIRouter(prefix="/catalog", tags=["catálogo"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_catalog_sync(request: Request) -> CatalogSyncService:
    """Servicio de sync ligado a la app (inyectable en tests)."""
    service: CatalogSyncService = request.app.state.catalog_sync
    return service


SyncServiceDep = Annotated[CatalogSyncService, Depends(get_catalog_sync)]


def _schema_ready(session: Session) -> bool:
    return inspect(session.get_bind()).has_table("products")


def _require_schema(session: Session) -> None:
    if not _schema_ready(session):
        raise ApiError(
            "CATALOG_EMPTY",
            "El catálogo no está inicializado. Ejecuta las migraciones y sincroniza.",
            status_code=503,
        )


def _to_sync_run_out(run: SyncRun, categories_total: int) -> SyncRunOut:
    completed = run.categories_ok + run.categories_failed
    progress = 1.0 if categories_total == 0 else min(1.0, completed / categories_total)
    return SyncRunOut(
        id=run.id,
        status=run.status,  # type: ignore[arg-type]
        started_at=run.started_at,
        finished_at=run.finished_at,
        postal_code=run.postal_code,
        warehouse=run.warehouse,
        categories_ok=run.categories_ok,
        categories_failed=run.categories_failed,
        categories_total=categories_total,
        products_seen=run.products_seen,
        error=run.error,
        progress=progress,
    )


@router.get("/status", response_model=CatalogStatusOut)
def catalog_status(session: SessionDep, service: SyncServiceDep) -> CatalogStatusOut:
    """Última sync, progreso, conteos y errores del catálogo."""
    if not _schema_ready(session):
        return CatalogStatusOut(
            schema_ready=False,
            is_syncing=service.is_running,
            product_count=0,
            category_count=0,
            food_category_count=0,
            last_sync=None,
            last_success_at=None,
            prices_captured_at=None,
            postal_code=POSTAL_CODE,
            warehouse=None,
        )

    product_count = session.scalar(select(func.count()).select_from(Product)) or 0
    category_count = session.scalar(select(func.count()).select_from(Category)) or 0
    food_category_count = (
        session.scalar(select(func.count()).select_from(Category).where(Category.is_food.is_(True)))
        or 0
    )
    subcategory_count = (
        session.scalar(select(func.count()).select_from(Category).where(Category.level == 1)) or 0
    )
    last_run = session.scalar(
        select(SyncRun).order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).limit(1)
    )
    last_success = session.scalar(
        select(SyncRun)
        .where(SyncRun.status.in_(("success", "partial")))
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
        .limit(1)
    )
    prices_captured_at = session.scalar(select(func.max(Product.last_seen_at)))

    return CatalogStatusOut(
        schema_ready=True,
        is_syncing=service.is_running,
        product_count=product_count,
        category_count=category_count,
        food_category_count=food_category_count,
        last_sync=_to_sync_run_out(last_run, subcategory_count) if last_run else None,
        last_success_at=(
            (last_success.finished_at or last_success.started_at) if last_success else None
        ),
        prices_captured_at=prices_captured_at,
        postal_code=last_run.postal_code if last_run else POSTAL_CODE,
        warehouse=last_run.warehouse if last_run else None,
    )


@router.post("/sync", response_model=SyncStartedOut, status_code=status.HTTP_202_ACCEPTED)
def start_catalog_sync(session: SessionDep, service: SyncServiceDep) -> SyncStartedOut:
    """Lanza una sincronización en segundo plano (202)."""
    _require_schema(session)
    try:
        run_id = service.start_background()
    except SyncInProgressError as exc:
        raise ApiError("SYNC_IN_PROGRESS", str(exc), status_code=409) from exc
    return SyncStartedOut(sync_run_id=run_id)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: SessionDep) -> list[CategoryOut]:
    """Árbol de secciones con sus subcategorías."""
    _require_schema(session)
    sections = session.scalars(
        select(Category)
        .where(Category.level == 0)
        .options(selectinload(Category.children))
        .order_by(Category.sort_order, Category.name)
    ).all()
    return [CategoryOut.model_validate(section) for section in sections]


@router.get("/products", response_model=ProductPage)
def list_products(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    only_available: bool = True,
) -> ProductPage:
    """Búsqueda por nombre y filtro por categoría (incluye subárbol)."""
    _require_schema(session)
    conditions = []
    if only_available:
        conditions.append(Product.published.is_(True))

    if q is not None and q.strip():
        term = q.strip()
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Product.name.ilike(f"%{escaped}%", escape="\\"))

    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None:
            raise ApiError("NOT_FOUND", "La categoría no existe.", status_code=404)
        category_ids = [category.id]
        if category.level == 0:
            category_ids.extend(
                session.scalars(select(Category.id).where(Category.parent_id == category.id)).all()
            )
        conditions.append(Product.category_id.in_(category_ids))

    total = session.scalar(select(func.count()).select_from(Product).where(*conditions)) or 0
    products = session.scalars(
        select(Product)
        .where(*conditions)
        .options(joinedload(Product.category))
        .order_by(Product.name, Product.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items: list[ProductSummary] = []
    for product in products:
        summary = ProductSummary.model_validate(product)
        summary.category_name = product.category.name if product.category else None
        items.append(summary)

    return ProductPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: int, session: SessionDep) -> ProductDetail:
    """Detalle de un producto por su id interno."""
    _require_schema(session)
    product = session.scalar(
        select(Product).where(Product.id == product_id).options(joinedload(Product.category))
    )
    if product is None:
        raise ApiError("NOT_FOUND", "El producto no existe.", status_code=404)
    detail = ProductDetail.model_validate(product)
    detail.category_name = product.category.name if product.category else None
    return detail
