"""Sincroniza el catálogo real de Mercadona y muestra el resumen (F1).

Uso desde la raíz del repositorio:

    cd backend
    uv run alembic upgrade head
    uv run python ..\\scripts\\sync_catalog.py

No se ejecuta en tests: los tests usan fixtures sintéticas y `respx`.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.models.catalog import Category, Product  # noqa: E402
from app.services.allergen_sync import AllergenSyncService  # noqa: E402
from app.services.catalog_sync import CatalogSyncService  # noqa: E402
from app.services.seed import SeedService  # noqa: E402


async def _run() -> int:
    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        if not inspect(engine).has_table("products"):
            print("ERROR: faltan las tablas. Ejecuta primero: uv run alembic upgrade head")
            return 2

        factory = sessionmaker(bind=engine, expire_on_commit=False)
        service = CatalogSyncService(factory)
        started = time.perf_counter()
        result = await service.run_sync()
        elapsed = time.perf_counter() - started

        with factory() as session:
            product_count = session.scalar(sa.select(sa.func.count()).select_from(Product)) or 0
            category_count = session.scalar(sa.select(sa.func.count()).select_from(Category)) or 0

        print(f"Base de datos: {settings.database_path}")
        print(f"Estado: {result.status}")
        print(f"Sync run: {result.run_id}")
        print(f"Subcategorías OK: {result.categories_ok}")
        print(f"Subcategorías fallidas: {result.categories_failed}")
        print(f"Productos vistos: {result.products_seen}")
        print(f"Productos en base de datos: {product_count}")
        print(f"Categorías en base de datos: {category_count}")
        print(f"Tiempo: {elapsed:.2f} s")
        if result.error:
            print(f"Error: {result.error}")

        if result.status in {"success", "partial"}:
            seed_result = SeedService(factory).load()
            print(
                f"Seed cargado: {seed_result.ingredients} ingredientes, {seed_result.dishes} platos"
            )
            if seed_result.missing_products or seed_result.skipped_products:
                print(
                    "AVISO: "
                    f"{len(seed_result.missing_products)} productos ausentes y "
                    f"{len(seed_result.skipped_products)} no mapeables."
                )
            allergen_result = await AllergenSyncService(factory).run()
            print(
                "Alérgenos actualizados: "
                f"{allergen_result.updated}/{allergen_result.products_seen} "
                f"({len(allergen_result.failed)} fallos)"
            )
        return 0 if result.status in {"success", "partial"} else 1
    finally:
        engine.dispose()


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
