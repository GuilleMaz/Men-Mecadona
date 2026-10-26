"""API de catálogo: estado, árbol, búsqueda, filtros, sync y errores (F1.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import create_db_engine
from app.main import create_app
from app.models.catalog import Category, Product, SyncRun
from app.models.types import utcnow
from app.services.catalog_sync import SyncInProgressError

LOCAL_HOST = "127.0.0.1:8000"


def _seed_catalog(factory: sessionmaker[Session]) -> None:
    now = utcnow()
    with factory() as session:
        session.add(Category(id=1, name="Despensa", level=0, is_food=True, sort_order=1))
        session.add(
            Category(
                id=11,
                name="Aceites",
                parent_id=1,
                level=1,
                is_food=True,
                sort_order=1,
            )
        )
        session.add(
            Category(
                id=12,
                name="Vinagres",
                parent_id=1,
                level=1,
                is_food=True,
                sort_order=2,
            )
        )
        run = SyncRun(
            started_at=now,
            finished_at=now,
            status="success",
            postal_code="22002",
            warehouse="4389",
            categories_ok=2,
            categories_failed=0,
            products_seen=3,
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                Product(
                    external_id="9001",
                    name="Aceite de oliva virgen",
                    brand="Hacendado",
                    category_id=11,
                    package_quantity_milli=5_000_000,
                    package_unit="ml",
                    package_price_cents=1725,
                    reference_price_cents=345,
                    reference_unit="l",
                    allergen_status="unknown",
                    published=True,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_sync_run_id=run.id,
                ),
                Product(
                    external_id="9002",
                    name="Vinagre de vino",
                    category_id=12,
                    package_quantity_milli=1_000_000,
                    package_unit="ml",
                    package_price_cents=120,
                    reference_price_cents=120,
                    reference_unit="l",
                    allergen_status="known",
                    published=True,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_sync_run_id=run.id,
                ),
                Product(
                    external_id="9003",
                    name="Producto no disponible",
                    category_id=11,
                    package_quantity_milli=1_000,
                    package_unit="unit",
                    package_price_cents=100,
                    allergen_status="unknown",
                    published=False,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_sync_run_id=run.id,
                ),
            ]
        )
        session.commit()


@pytest.fixture
def catalog_client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
) -> Any:
    _seed_catalog(catalog_session_factory)
    app = create_app(catalog_settings, session_factory=catalog_session_factory)
    with TestClient(app) as client:
        yield client


def _get(client: TestClient, url: str, **params: Any) -> Any:
    return client.get(url, headers={"Host": LOCAL_HOST}, params=params)


def test_status_returns_counts_and_last_sync(catalog_client: TestClient) -> None:
    response = _get(catalog_client, "/api/catalog/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_ready"] is True
    assert payload["is_syncing"] is False
    assert payload["product_count"] == 3
    assert payload["category_count"] == 3
    assert payload["food_category_count"] == 3
    assert payload["postal_code"] == "22002"
    assert payload["warehouse"] == "4389"
    assert payload["prices_captured_at"] is not None
    assert payload["last_sync"]["status"] == "success"
    assert payload["last_sync"]["categories_ok"] == 2
    assert payload["last_sync"]["categories_total"] == 2
    assert payload["last_sync"]["progress"] == 1.0
    assert payload["last_success_at"] is not None


def test_categories_are_returned_as_a_tree(catalog_client: TestClient) -> None:
    response = _get(catalog_client, "/api/catalog/categories")

    assert response.status_code == 200
    sections = response.json()
    assert len(sections) == 1
    assert sections[0]["id"] == 1
    assert sections[0]["name"] == "Despensa"
    assert [child["id"] for child in sections[0]["children"]] == [11, 12]


def test_products_search_filter_and_pagination(catalog_client: TestClient) -> None:
    default = _get(catalog_client, "/api/catalog/products")
    assert default.status_code == 200
    assert default.json()["total"] == 2
    assert [item["external_id"] for item in default.json()["items"]] == ["9001", "9002"]

    search = _get(catalog_client, "/api/catalog/products", q="ACEITE")
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["name"] == "Aceite de oliva virgen"
    assert search.json()["items"][0]["category_name"] == "Aceites"
    assert search.json()["items"][0]["package_price_cents"] == 1725
    assert isinstance(search.json()["items"][0]["package_price_cents"], int)

    by_section = _get(catalog_client, "/api/catalog/products", category_id=1)
    assert by_section.json()["total"] == 2

    by_subcategory = _get(catalog_client, "/api/catalog/products", category_id=11)
    assert by_subcategory.json()["total"] == 1

    paged = _get(catalog_client, "/api/catalog/products", limit=1, offset=1)
    assert paged.json()["total"] == 2
    assert paged.json()["limit"] == 1
    assert paged.json()["offset"] == 1
    assert [item["external_id"] for item in paged.json()["items"]] == ["9002"]

    all_products = _get(catalog_client, "/api/catalog/products", only_available=False)
    assert all_products.json()["total"] == 3


def test_wildcards_in_search_are_escaped(catalog_client: TestClient) -> None:
    response = _get(catalog_client, "/api/catalog/products", q="%")

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_product_detail_and_not_found(catalog_client: TestClient) -> None:
    listing = _get(catalog_client, "/api/catalog/products", q="Aceite")
    product_id = listing.json()["items"][0]["id"]

    response = _get(catalog_client, f"/api/catalog/products/{product_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["external_id"] == "9001"
    assert payload["package_quantity_milli"] == 5_000_000
    assert payload["allergen_status"] == "unknown"
    assert "raw_json" not in json.dumps(payload)

    missing = _get(catalog_client, "/api/catalog/products/99999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_missing_category_returns_not_found(catalog_client: TestClient) -> None:
    response = _get(catalog_client, "/api/catalog/products", category_id=999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_validation_errors_use_the_error_envelope(catalog_client: TestClient) -> None:
    response = _get(catalog_client, "/api/catalog/products", limit=0)

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["details"]["errors"]


class _FakeSyncService:
    is_running = False

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = 0

    def start_background(self) -> int:
        if self.fail:
            raise SyncInProgressError("Ya hay una sincronización de catálogo en curso.")
        self.started += 1
        return 42


def test_manual_sync_starts_in_background(catalog_client: TestClient) -> None:
    fake = _FakeSyncService()
    catalog_client.app.state.catalog_sync = fake

    response = catalog_client.post("/api/catalog/sync", headers={"Host": LOCAL_HOST})

    assert response.status_code == 202
    assert response.json() == {"sync_run_id": 42, "status": "running"}
    assert fake.started == 1


def test_manual_sync_conflict_returns_409(catalog_client: TestClient) -> None:
    catalog_client.app.state.catalog_sync = _FakeSyncService(fail=True)

    response = catalog_client.post("/api/catalog/sync", headers={"Host": LOCAL_HOST})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SYNC_IN_PROGRESS"


def test_status_without_schema_reports_not_ready(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        sync_on_startup=False,
        cesta_data_dir=tmp_path / "vacia",
    )
    engine = create_db_engine(settings)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        app = create_app(settings, session_factory=factory)
        with TestClient(app) as client:
            status = client.get("/api/catalog/status", headers={"Host": LOCAL_HOST})
            sync = client.post("/api/catalog/sync", headers={"Host": LOCAL_HOST})
    finally:
        engine.dispose()

    assert status.status_code == 200
    assert status.json()["schema_ready"] is False
    assert status.json()["product_count"] == 0
    assert sync.status_code == 503
    assert sync.json()["error"]["code"] == "CATALOG_EMPTY"
