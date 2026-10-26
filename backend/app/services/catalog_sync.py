"""Sincronización del catálogo de Mercadona (F1.4).

Diseño:

- El árbol de secciones se descarga una vez y se hace upsert de categorías.
- Las subcategorías se descargan con concurrencia máxima 4.
- Cada producto se normaliza a céntimos y milésimas y se hace upsert por
  `external_id`, por lo que dos syncs consecutivos no duplican filas.
- Solo se marca `published=False` a productos de subcategorías descargadas
  correctamente; una subcategoría fallida conserva la disponibilidad anterior.
- Un lock de proceso impide solapar sincronizaciones. El estado y el progreso se
  persisten en `sync_runs` y `sync_category_runs` para que la UI pueda consultarlos.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import batched
from typing import Protocol

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.config import POSTAL_CODE
from app.models.catalog import Category, Product, SyncCategoryRun, SyncRun
from app.models.types import utcnow
from app.schemas.mercadona import (
    MercadonaCategoryDetail,
    MercadonaSection,
    MercadonaSubcategory,
)
from app.services.catalog_normalizer import (
    NormalizationError,
    NormalizedProduct,
    is_food_category,
    normalize_product,
)
from app.services.mercadona_client import MercadonaClient, MercadonaError

logger = logging.getLogger(__name__)

SYNC_REFRESH_INTERVAL = timedelta(hours=24)
MAX_CONCURRENCY = 4
_UPSERT_CHUNK_SIZE = 400
_MAX_ERROR_LENGTH = 2_000

_PRODUCT_UPDATE_COLUMNS: tuple[str, ...] = (
    "name",
    "ean",
    "brand",
    "category_id",
    "packaging",
    "package_quantity_milli",
    "package_unit",
    "is_estimated",
    "package_price_cents",
    "reference_price_cents",
    "reference_unit",
    "is_pack",
    "approx_size",
    "selling_method",
    "thumbnail_url",
    "published",
    "unavailable_from",
    "last_seen_at",
    "last_sync_run_id",
)


class CatalogClient(Protocol):
    """Contrato mínimo del cliente usado por la sync (permite dobles en tests)."""

    @property
    def warehouse(self) -> str | None: ...

    async def get_sections(self) -> list[MercadonaSection]: ...

    async def get_subcategory(self, subcategory_id: int) -> MercadonaCategoryDetail: ...

    async def close(self) -> None: ...


class SyncInProgressError(RuntimeError):
    """Ya hay una sincronización en curso en este proceso."""


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Resumen de una sincronización terminada."""

    run_id: int
    status: str
    categories_ok: int
    categories_failed: int
    products_seen: int
    error: str | None


def _clip_error(message: str) -> str:
    return message[:_MAX_ERROR_LENGTH]


class CatalogSyncService:
    """Orquesta la descarga y persistencia del catálogo."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        client_factory: Callable[[], CatalogClient] | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency debe ser mayor que cero")
        self._session_factory = session_factory
        self._client_factory = client_factory or MercadonaClient
        self._max_concurrency = max_concurrency
        self._lock = threading.Lock()
        self._task: asyncio.Task[SyncResult] | None = None
        self._current_run_id: int | None = None

    @property
    def is_running(self) -> bool:
        """Hay una sync en curso en este proceso."""
        return self._lock.locked()

    @property
    def current_run_id(self) -> int | None:
        """Identificador de la sync en curso, si la hay."""
        return self._current_run_id

    def recover_interrupted_runs(self) -> int:
        """Marca como fallidas las syncs que quedaron «running» tras un reinicio."""
        with self._session_factory() as session:
            runs = session.scalars(select(SyncRun).where(SyncRun.status == "running")).all()
            if not runs:
                return 0
            now = utcnow()
            for run in runs:
                run.status = "failed"
                run.finished_at = now
                run.error = "La aplicación se reinició durante la sincronización."
            session.commit()
            return len(runs)

    def should_sync_on_startup(self) -> bool:
        """Sincroniza si el catálogo está vacío o la última copia tiene más de 24 h."""
        with self._session_factory() as session:
            product_count = session.scalar(select(func.count()).select_from(Product)) or 0
            if product_count == 0:
                return True
            last_run = session.scalar(
                select(SyncRun)
                .where(SyncRun.status.in_(("success", "partial")))
                .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
                .limit(1)
            )
        if last_run is None or last_run.finished_at is None:
            return True
        return utcnow() - last_run.finished_at > SYNC_REFRESH_INTERVAL

    def start_if_due(self) -> int | None:
        """Lanza la sync de arranque si toca; devuelve el id o `None`."""
        if not self.should_sync_on_startup():
            return None
        return self.start_background()

    def start_background(self) -> int:
        """Lanza una sync en segundo plano y devuelve su `sync_run_id`.

        El POST manual y el arranque de la app usan este método para no bloquear la
        respuesta HTTP ni el startup.
        """
        if not self._lock.acquire(blocking=False):
            raise SyncInProgressError("Ya hay una sincronización de catálogo en curso.")

        run_id: int | None = None
        try:
            run_id = self._create_run()
            self._current_run_id = run_id
            self._task = asyncio.create_task(self._execute(run_id), name=f"catalog-sync-{run_id}")
        except BaseException:
            try:
                if run_id is not None:
                    self._finish_run(run_id, status="failed", error="No se pudo iniciar la sync.")
            finally:
                self._current_run_id = None
                self._lock.release()
            raise
        return run_id

    async def run_sync(self) -> SyncResult:
        """Ejecuta una sync y espera al resultado (tests y script manual)."""
        if not self._lock.acquire(blocking=False):
            raise SyncInProgressError("Ya hay una sincronización de catálogo en curso.")

        try:
            run_id = self._create_run()
        except BaseException:
            self._lock.release()
            raise
        self._current_run_id = run_id
        return await self._execute(run_id)

    async def shutdown(self) -> None:
        """Cancela la sync en curso al apagar la app."""
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._task = None

    def _create_run(self) -> int:
        with self._session_factory() as session:
            run = SyncRun(
                started_at=utcnow(),
                status="running",
                postal_code=POSTAL_CODE,
                categories_ok=0,
                categories_failed=0,
                products_seen=0,
            )
            session.add(run)
            session.commit()
            return run.id

    def _finish_run(self, run_id: int, *, status: str, error: str | None = None) -> None:
        with self._session_factory() as session:
            run = session.get(SyncRun, run_id)
            if run is None:
                return
            run.status = status
            run.finished_at = utcnow()
            run.error = _clip_error(error) if error else None
            session.commit()

    async def _execute(self, run_id: int) -> SyncResult:
        client: CatalogClient | None = None
        tasks: list[
            asyncio.Task[
                tuple[MercadonaSubcategory, MercadonaCategoryDetail | None, Exception | None]
            ]
        ] = []
        categories_ok = 0
        categories_failed = 0
        products_seen = 0
        error: str | None = None

        try:
            client = self._client_factory()
            sections = await client.get_sections()
            self._update_warehouse(run_id, client.warehouse)
            subcategories = self._upsert_categories(sections)
            if not subcategories:
                raise MercadonaError("Mercadona no devolvió subcategorías.")
            categories_total = len(subcategories)

            semaphore = asyncio.Semaphore(self._max_concurrency)
            tasks = [
                asyncio.create_task(self._fetch_subcategory(client, subcategory, semaphore))
                for subcategory in subcategories
            ]
            successful_category_ids: list[int] = []

            for completed in asyncio.as_completed(tasks):
                subcategory, detail, failure = await completed
                if failure is not None or detail is None:
                    categories_failed += 1
                    self._record_category_failure(run_id, subcategory, failure)
                    continue

                seen, _skipped = self._persist_category(run_id, subcategory, detail)
                categories_ok += 1
                products_seen += seen
                successful_category_ids.append(subcategory.id)
                self._record_category_success(run_id, subcategory, seen)

            tasks = []
            # Una sola pasada al final: un producto duplicado en varias
            # subcategorías debe quedar disponible si aparece en cualquiera.
            self._mark_unavailable(run_id, successful_category_ids)
            if categories_failed == 0:
                status = "success"
            elif categories_ok == 0:
                status = "failed"
                error = (
                    f"Ninguna de las {categories_total} subcategorías se descargó correctamente."
                )
            else:
                status = "partial"
                error = (
                    f"{categories_failed} de {categories_total} subcategorías fallaron; "
                    "sus productos conservan la disponibilidad anterior."
                )
        except asyncio.CancelledError:
            self._finish_run(run_id, status="failed", error="Sincronización interrumpida.")
            raise
        except MercadonaError as exc:
            error = f"{exc.code}: {exc.message}"
            status = "failed"
            logger.warning("Sync de catálogo fallida: %s", error)
        except Exception as exc:  # noqa: BLE001 - el estado de la sync debe quedar cerrado
            error = f"Error inesperado: {exc}"
            status = "failed"
            logger.exception("Error inesperado durante la sync de catálogo")
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await _close_quietly(client)
            self._lock.release()
            self._current_run_id = None
            self._task = None

        self._finish_run(run_id, status=status, error=error)
        if status == "success":
            logger.info(
                "Sync de catálogo completada: %s subcategorías, %s productos vistos",
                categories_ok,
                products_seen,
            )
        else:
            logger.warning(
                "Sync de catálogo %s: %s ok, %s fallidas, %s productos vistos",
                status,
                categories_ok,
                categories_failed,
                products_seen,
            )
        return SyncResult(
            run_id=run_id,
            status=status,
            categories_ok=categories_ok,
            categories_failed=categories_failed,
            products_seen=products_seen,
            error=error,
        )

    async def _fetch_subcategory(
        self,
        client: CatalogClient,
        subcategory: MercadonaSubcategory,
        semaphore: asyncio.Semaphore,
    ) -> tuple[MercadonaSubcategory, MercadonaCategoryDetail | None, Exception | None]:
        async with semaphore:
            try:
                detail = await client.get_subcategory(subcategory.id)
            except Exception as exc:  # noqa: BLE001 - se registra por subcategoría
                return subcategory, None, exc
            return subcategory, detail, None

    def _update_warehouse(self, run_id: int, warehouse: str | None) -> None:
        with self._session_factory() as session:
            run = session.get(SyncRun, run_id)
            if run is not None:
                run.warehouse = warehouse
                session.commit()

    def _upsert_categories(
        self, sections: Sequence[MercadonaSection]
    ) -> list[MercadonaSubcategory]:
        section_rows: list[dict[str, object]] = []
        subcategory_rows: list[dict[str, object]] = []
        subcategories: list[MercadonaSubcategory] = []
        food_by_section: dict[int, bool] = {}

        for section in sections:
            is_food = is_food_category(section.name, level=0)
            food_by_section[section.id] = is_food
            section_rows.append(
                {
                    "id": section.id,
                    "name": section.name,
                    "parent_id": None,
                    "level": 0,
                    "is_food": is_food,
                    "sort_order": section.order,
                }
            )

        for section in sections:
            parent_is_food = food_by_section[section.id]
            for subcategory in section.categories:
                is_food = is_food_category(subcategory.name, level=1, parent_is_food=parent_is_food)
                subcategory_rows.append(
                    {
                        "id": subcategory.id,
                        "name": subcategory.name,
                        "parent_id": section.id,
                        "level": 1,
                        "is_food": is_food,
                        "sort_order": subcategory.order,
                    }
                )
                subcategories.append(subcategory)

        with self._session_factory() as session:
            if section_rows:
                self._upsert_category_rows(session, section_rows)
                session.flush()
            if subcategory_rows:
                self._upsert_category_rows(session, subcategory_rows)
            session.commit()
        return subcategories

    @staticmethod
    def _upsert_category_rows(session: Session, rows: Sequence[dict[str, object]]) -> None:
        statement = sqlite_insert(Category).values(list(rows))
        statement = statement.on_conflict_do_update(
            index_elements=[Category.id],
            set_={
                "name": statement.excluded.name,
                "parent_id": statement.excluded.parent_id,
                "level": statement.excluded.level,
                "is_food": statement.excluded.is_food,
                "sort_order": statement.excluded.sort_order,
            },
        )
        session.execute(statement)

    def _persist_category(
        self,
        run_id: int,
        subcategory: MercadonaSubcategory,
        detail: MercadonaCategoryDetail,
    ) -> tuple[int, int]:
        products = detail.all_products()
        seen_at = utcnow()
        normalized: list[NormalizedProduct] = []
        skipped = 0
        for product in products:
            try:
                normalized.append(normalize_product(product, category_id=subcategory.id))
            except NormalizationError as exc:
                skipped += 1
                logger.warning("Producto omitido en la sync: %s", exc)

        with self._session_factory() as session:
            self._upsert_products(session, normalized, run_id=run_id, seen_at=seen_at)
            session.add(
                SyncCategoryRun(
                    sync_run_id=run_id,
                    category_id=subcategory.id,
                    status="success",
                    products_seen=len(products),
                    error=f"{skipped} productos omitidos" if skipped else None,
                )
            )
            session.commit()
        return len(products), skipped

    def _mark_unavailable(self, run_id: int, category_ids: Sequence[int]) -> None:
        """Marca no disponible solo lo ausente de subcategorías descargadas bien.

        Se ejecuta una vez al final para no depender del orden en que terminen las
        subcategorías: un producto duplicado sigue disponible si aparece en
        cualquiera de ellas.
        """
        if not category_ids:
            return
        with self._session_factory() as session:
            session.execute(
                update(Product)
                .where(Product.category_id.in_(category_ids))
                .where(
                    or_(
                        Product.last_sync_run_id.is_(None),
                        Product.last_sync_run_id != run_id,
                    )
                )
                .values(published=False)
            )
            session.commit()

    @staticmethod
    def _upsert_products(
        session: Session,
        products: Iterable[NormalizedProduct],
        *,
        run_id: int,
        seen_at: datetime,
    ) -> None:
        rows = [
            {
                "external_id": product.external_id,
                "ean": product.ean,
                "name": product.name,
                "brand": product.brand,
                "category_id": product.category_id,
                "packaging": product.packaging,
                "package_quantity_milli": product.package_quantity_milli,
                "package_unit": product.package_unit,
                "is_estimated": product.is_estimated,
                "package_price_cents": product.package_price_cents,
                "reference_price_cents": product.reference_price_cents,
                "reference_unit": product.reference_unit,
                "is_pack": product.is_pack,
                "approx_size": product.approx_size,
                "selling_method": product.selling_method,
                "thumbnail_url": product.thumbnail_url,
                "published": product.published,
                "unavailable_from": product.unavailable_from,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "last_sync_run_id": run_id,
            }
            for product in products
        ]
        for chunk in batched(rows, _UPSERT_CHUNK_SIZE, strict=False):
            statement = sqlite_insert(Product).values(list(chunk))
            set_ = {
                column: getattr(statement.excluded, column) for column in _PRODUCT_UPDATE_COLUMNS
            }
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Product.external_id],
                    set_=set_,
                )
            )

    def _record_category_success(
        self, run_id: int, subcategory: MercadonaSubcategory, products_seen: int
    ) -> None:
        with self._session_factory() as session:
            run = session.get(SyncRun, run_id)
            if run is None:
                return
            run.categories_ok += 1
            run.products_seen += products_seen
            session.commit()

    def _record_category_failure(
        self,
        run_id: int,
        subcategory: MercadonaSubcategory,
        failure: Exception | None,
    ) -> None:
        message = str(failure) if failure is not None else "Subcategoría sin productos."
        with self._session_factory() as session:
            session.add(
                SyncCategoryRun(
                    sync_run_id=run_id,
                    category_id=subcategory.id,
                    status="failed",
                    products_seen=0,
                    error=_clip_error(message),
                )
            )
            run = session.get(SyncRun, run_id)
            if run is not None:
                run.categories_failed += 1
            session.commit()


async def _close_quietly(client: CatalogClient | None) -> None:
    if client is None:
        return
    try:
        await client.close()
    except Exception:  # noqa: BLE001 - cerrar no debe ocultar el resultado real
        logger.debug("Error cerrando el cliente de Mercadona", exc_info=True)
