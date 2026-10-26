"""Enriquece los alérgenos de los productos mapeados (F2.4).

Uso desde la raíz del repositorio:

    cd backend
    uv run python ..\\scripts\\sync_allergens.py

Solo descarga el detalle de los productos que pertenecen a algún ingrediente.
No se ejecuta en tests; usa un cliente real y no persiste el JSON completo.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.services.allergen_sync import AllergenSyncService  # noqa: E402


async def _run() -> int:
    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        if not inspect(engine).has_table("ingredient_products"):
            print("ERROR: faltan las tablas. Ejecuta primero: uv run alembic upgrade head")
            return 2
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        result = await AllergenSyncService(factory).run()
        print(f"Productos mapeados: {result.products_seen}")
        print(f"Productos actualizados: {result.updated}")
        print(f"Sin confirmar: {result.unknown}")
        print(f"Parciales: {result.partial}")
        print(f"Fallos: {len(result.failed)}")
        for external_id, message in result.failed[:20]:
            print(f"  - {external_id}: {message}")
        return 0 if result.updated > 0 else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
