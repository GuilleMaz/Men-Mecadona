"""Sync de catálogo: upsert idempotente, fallo parcial, lock y concurrencia (F1.4)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import Category, Product, SyncCategoryRun, SyncRun
from app.models.types import utcnow
from app.schemas.mercadona import (
    MercadonaCategoryDetail,
    MercadonaSection,
    MercadonaSubcategory,
)
from app.services.catalog_sync import CatalogSyncService, SyncInProgressError
from app.services.mercadona_client import WarehouseUnavailableError
from tests.catalog_fixtures import detail_payload, product_payload, section_payload


class FakeClient:
    """Cliente de catálogo sintético, sin red."""

    def __init__(
        self,
        sections: list[MercadonaSection],
        details: dict[int, MercadonaCategoryDetail],
        *,
        delay: float = 0.0,
        failures: set[int] | None = None,
        sections_error: Exception | None = None,
    ) -> None:
        self.sections = sections
        self.details = details
        self.delay = delay
        self.failures = failures or set()
        self.sections_error = sections_error
        self.warehouse: str | None = "4389"
        self.active = 0
        self.max_active = 0
        self.closed = False

    async def get_sections(self) -> list[MercadonaSection]:
        if self.sections_error is not None:
            raise self.sections_error
        return self.sections

    async def get_subcategory(self, subcategory_id: int) -> MercadonaCategoryDetail:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if subcategory_id in self.failures:
                raise WarehouseUnavailableError("Fallo sintético de subcategoría")
            return self.details[subcategory_id]
        finally:
            self.active -= 1

    async def close(self) -> None:
        self.closed = True


def _base_catalog() -> tuple[list[MercadonaSection], dict[int, MercadonaCategoryDetail]]:
    section = section_payload(
        12,
        "Aceite, especias y salsas",
        [
            MercadonaSubcategory(id=112, name="Aceite, vinagre y sal", order=1),
            MercadonaSubcategory(id=113, name="Especias", order=2),
        ],
    )
    details = {
        112: detail_payload(
            112,
            "Aceite, vinagre y sal",
            [
                product_payload(
                    "9001",
                    "Aceite de oliva sintético 5 L",
                    unit_price="17.25",
                    unit_size=5.0,
                    size_format="l",
                    reference_price="3.450",
                    reference_format="L",
                ),
                product_payload(
                    "9003",
                    "Pack 6 × 125 g sintético",
                    unit_price="4.50",
                    unit_size=750.0,
                    size_format="g",
                    is_pack=True,
                    pack_size=6,
                    total_units=6,
                ),
            ],
        ),
        113: detail_payload(
            113,
            "Especias",
            [
                product_payload(
                    "9002",
                    "Vinagre sintético 1 L",
                    unit_price="1.20",
                    unit_size=1.0,
                    size_format="l",
                    reference_price="1.200",
                    reference_format="L",
                )
            ],
        ),
    }
    return [section], details


def _service(
    factory: sessionmaker[Session], client: FakeClient, *, max_concurrency: int = 4
) -> CatalogSyncService:
    return CatalogSyncService(
        factory,
        client_factory=lambda: client,
        max_concurrency=max_concurrency,
    )


def _product(factory: sessionmaker[Session], external_id: str) -> Product:
    with factory() as session:
        product = session.scalar(select(Product).where(Product.external_id == external_id))
        assert product is not None
        return product


async def test_sync_persists_catalog_and_normalized_values(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    client = FakeClient(sections, details)
    service = _service(catalog_session_factory, client)

    result = await service.run_sync()

    assert result.status == "success"
    assert result.categories_ok == 2
    assert result.categories_failed == 0
    assert result.products_seen == 3
    assert client.closed is True

    with catalog_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 3
        assert session.scalar(select(func.count()).select_from(Category)) == 3
        run = session.get(SyncRun, result.run_id)
        assert run is not None
        assert run.status == "success"
        assert run.warehouse == "4389"
        assert run.finished_at is not None
        category_runs = session.scalars(
            select(SyncCategoryRun).where(SyncCategoryRun.sync_run_id == result.run_id)
        ).all()
        assert {category_run.status for category_run in category_runs} == {"success"}

    oil = _product(catalog_session_factory, "9001")
    assert oil.package_price_cents == 1725
    assert oil.package_quantity_milli == 5_000_000
    assert oil.package_unit == "ml"
    assert oil.reference_price_cents == 345
    assert oil.reference_unit == "l"
    assert oil.allergen_status == "unknown"
    assert oil.first_seen_at == oil.last_seen_at

    pack = _product(catalog_session_factory, "9003")
    assert pack.is_pack is True
    assert pack.package_quantity_milli == 750_000


async def test_second_sync_is_idempotent(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    first_service = _service(catalog_session_factory, FakeClient(sections, details))
    first = await first_service.run_sync()
    oil_first = _product(catalog_session_factory, "9001")
    oil_id = oil_first.id
    first_seen = oil_first.first_seen_at

    second_service = _service(catalog_session_factory, FakeClient(sections, details))
    second = await second_service.run_sync()

    with catalog_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 3
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
    oil_second = _product(catalog_session_factory, "9001")
    assert oil_second.id == oil_id
    assert oil_second.first_seen_at == first_seen
    assert first.run_id != second.run_id


async def test_failed_subcategory_does_not_mark_its_products_unavailable(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    first_service = _service(catalog_session_factory, FakeClient(sections, details))
    await first_service.run_sync()

    partial_details = {
        112: detail_payload(
            112,
            "Aceite, vinagre y sal",
            [
                product_payload(
                    "9001",
                    "Aceite de oliva sintético 5 L",
                    unit_price="18.00",
                    unit_size=5.0,
                    size_format="l",
                )
            ],
        )
    }
    second_service = _service(
        catalog_session_factory,
        FakeClient(sections, partial_details, failures={113}),
    )

    result = await second_service.run_sync()

    assert result.status == "partial"
    assert result.categories_ok == 1
    assert result.categories_failed == 1
    assert result.products_seen == 1
    assert result.error is not None
    assert "subcategorías fallaron" in result.error

    oil = _product(catalog_session_factory, "9001")
    pack = _product(catalog_session_factory, "9003")
    vinegar = _product(catalog_session_factory, "9002")
    assert oil.published is True
    assert oil.package_price_cents == 1800
    assert pack.published is False
    assert vinegar.published is True

    with catalog_session_factory() as session:
        category_runs = session.scalars(
            select(SyncCategoryRun)
            .where(SyncCategoryRun.sync_run_id == result.run_id)
            .order_by(SyncCategoryRun.category_id)
        ).all()
        assert [(run.category_id, run.status) for run in category_runs] == [
            (112, "success"),
            (113, "failed"),
        ]
        assert category_runs[1].error is not None


async def test_subcategories_are_downloaded_with_concurrency_at_most_four(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    subcategories = [
        MercadonaSubcategory(id=200 + index, name=f"Subcategoría {index}", order=index)
        for index in range(8)
    ]
    sections = [section_payload(20, "Sección sintética", subcategories)]
    details = {
        subcategory.id: detail_payload(
            subcategory.id,
            subcategory.name,
            [product_payload(str(2000 + index), f"Producto {index}")],
        )
        for index, subcategory in enumerate(subcategories)
    }
    client = FakeClient(sections, details, delay=0.02)
    service = _service(catalog_session_factory, client, max_concurrency=4)

    result = await service.run_sync()

    assert result.status == "success"
    assert client.max_active == 4
    assert result.products_seen == 8


async def test_sync_lock_prevents_overlapping_runs(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    service = _service(catalog_session_factory, FakeClient(sections, details, delay=0.05))

    first_task = asyncio.create_task(service.run_sync())
    await asyncio.sleep(0)
    with pytest.raises(SyncInProgressError):
        await service.run_sync()

    result = await first_task
    assert result.status == "success"


async def test_warehouse_failure_marks_run_failed(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    client = FakeClient(
        [],
        {},
        sections_error=WarehouseUnavailableError("No se pudo confirmar el almacén 4389."),
    )
    service = _service(catalog_session_factory, client)

    result = await service.run_sync()

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.startswith("WAREHOUSE_UNAVAILABLE")
    with catalog_session_factory() as session:
        run = session.get(SyncRun, result.run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.finished_at is not None


async def test_invalid_products_are_skipped_without_failing_the_subcategory(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    section = section_payload(30, "Sección", [MercadonaSubcategory(id=301, name="Sub")])
    details = {
        301: detail_payload(
            301,
            "Sub",
            [
                product_payload("9101", "Producto válido"),
                product_payload("9102", "Producto inválido", unit_price="1.2.3"),
            ],
        )
    }
    service = _service(catalog_session_factory, FakeClient([section], details))

    result = await service.run_sync()

    assert result.status == "success"
    assert result.products_seen == 2
    with catalog_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 1
        category_run = session.scalar(select(SyncCategoryRun))
        assert category_run is not None
        assert category_run.status == "success"
        assert category_run.error == "1 productos omitidos"


async def test_duplicate_product_stays_available_if_seen_in_any_subcategory(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    section = section_payload(
        60,
        "Sección con duplicados",
        [
            MercadonaSubcategory(id=601, name="Primera", order=1),
            MercadonaSubcategory(id=602, name="Segunda", order=2),
        ],
    )
    product = product_payload("9301", "Producto compartido")
    first_details = {
        601: detail_payload(601, "Primera", []),
        602: detail_payload(602, "Segunda", [product]),
    }
    await _service(catalog_session_factory, FakeClient([section], first_details)).run_sync()

    second_details = {
        601: detail_payload(601, "Primera", [product]),
        602: detail_payload(602, "Segunda", []),
    }
    result = await _service(
        catalog_session_factory, FakeClient([section], second_details)
    ).run_sync()

    assert result.status == "success"
    assert _product(catalog_session_factory, "9301").published is True

    empty_details = {
        601: detail_payload(601, "Primera", []),
        602: detail_payload(602, "Segunda", []),
    }
    await _service(catalog_session_factory, FakeClient([section], empty_details)).run_sync()
    assert _product(catalog_session_factory, "9301").published is False


def test_startup_sync_is_due_for_empty_and_stale_catalog(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    service = CatalogSyncService(catalog_session_factory, client_factory=FakeClient)

    assert service.should_sync_on_startup() is True

    with catalog_session_factory() as session:
        session.add(Category(id=1, name="Sección", level=0))
        session.add(
            Product(
                external_id="9001",
                name="Producto",
                category_id=1,
                package_quantity_milli=1_000,
                package_unit="unit",
                package_price_cents=100,
            )
        )
        run = SyncRun(
            started_at=utcnow() - timedelta(hours=1),
            finished_at=utcnow() - timedelta(hours=1),
            status="success",
            postal_code="22002",
            warehouse="4389",
        )
        session.add(run)
        session.commit()
        assert service.should_sync_on_startup() is False
        run.finished_at = utcnow() - timedelta(hours=25)
        session.commit()

    assert service.should_sync_on_startup() is True


async def test_start_if_due_starts_background_sync_for_empty_catalog(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    service = _service(catalog_session_factory, FakeClient(sections, details))

    run_id = service.start_if_due()

    assert run_id is not None
    for _ in range(200):
        if not service.is_running:
            break
        await asyncio.sleep(0.01)
    assert service.is_running is False
    with catalog_session_factory() as session:
        run = session.get(SyncRun, run_id)
        assert run is not None
        assert run.status == "success"


async def test_client_creation_failure_releases_the_lock(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    def _broken_client() -> FakeClient:
        raise RuntimeError("sin cliente")

    service = CatalogSyncService(catalog_session_factory, client_factory=_broken_client)

    result = await service.run_sync()

    assert result.status == "failed"
    assert result.error is not None
    assert "sin cliente" in result.error
    assert service.is_running is False


def test_recover_interrupted_runs_marks_them_failed(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        run = SyncRun(started_at=utcnow(), status="running", postal_code="22002")
        session.add(run)
        session.commit()
        run_id = run.id

    service = CatalogSyncService(catalog_session_factory, client_factory=FakeClient)
    recovered = service.recover_interrupted_runs()

    assert recovered == 1
    with catalog_session_factory() as session:
        run = session.get(SyncRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.finished_at is not None
        assert "reinició" in (run.error or "")


async def test_category_food_flags_are_persisted(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections = [
        section_payload(40, "Limpieza y hogar", [MercadonaSubcategory(id=401, name="Baño")]),
        section_payload(41, "Bebé", [MercadonaSubcategory(id=411, name="Toallitas y pañales")]),
    ]
    details: dict[int, MercadonaCategoryDetail] = {
        401: detail_payload(401, "Baño", [product_payload("9201", "Lejía")]),
        411: detail_payload(411, "Toallitas y pañales", [product_payload("9202", "Toallitas")]),
    }
    service = _service(catalog_session_factory, FakeClient(sections, details))

    await service.run_sync()

    with catalog_session_factory() as session:
        categories = {category.id: category for category in session.scalars(select(Category)).all()}
    assert categories[40].is_food is False
    assert categories[401].is_food is False
    assert categories[41].is_food is True
    assert categories[411].is_food is False


async def test_products_are_marked_unavailable_only_after_successful_download(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    sections, details = _base_catalog()
    await _service(catalog_session_factory, FakeClient(sections, details)).run_sync()

    empty_details = {
        112: detail_payload(112, "Aceite, vinagre y sal", []),
        113: detail_payload(113, "Especias", []),
    }
    result = await _service(catalog_session_factory, FakeClient(sections, empty_details)).run_sync()

    assert result.status == "success"
    with catalog_session_factory() as session:
        published = session.scalars(select(Product).order_by(Product.external_id)).all()
    assert [product.published for product in published] == [False, False, False]
