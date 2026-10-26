"""Carga idempotente del seed de ingredientes y platos (F2.6).

Uso desde la raíz del repositorio:

    cd backend
    uv run alembic upgrade head
    uv run python ..\\scripts\\load_seed.py
    uv run python ..\\scripts\\load_seed.py --dry-run

El cargador no borra datos de usuario. Si el catálogo está vacío, crea los
ingredientes y platos y deja los mapeos pendientes; el validador de F2.7 los
señalará.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.services.seed import SeedService, SeedValidationError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga el seed de Cesta.")
    parser.add_argument("--dry-run", action="store_true", help="No persiste cambios.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Falla si algún producto del seed no está en el catálogo.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        if not inspect(engine).has_table("dishes"):
            print("ERROR: faltan las tablas. Ejecuta primero: uv run alembic upgrade head")
            return 2
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            result = SeedService(factory).load(dry_run=args.dry_run)
        except SeedValidationError as exc:
            print(f"ERROR: {exc}")
            return 1

        print(f"Base de datos: {settings.database_path}")
        print(f"Versión del seed: {result.version}")
        print(f"Modo: {'dry-run' if result.dry_run else 'persistente'}")
        print(f"Ingredientes cargados: {result.ingredients}")
        print(f"Productos mapeados: {result.products}")
        print(f"Platos cargados: {result.dishes}")
        print(f"Ingredientes desactivados: {result.deactivated_ingredients}")
        print(f"Platos desactivados: {result.deactivated_dishes}")
        if result.missing_products:
            print(
                f"AVISO: {len(result.missing_products)} productos del seed no están en el catálogo."
            )
        if result.skipped_products:
            print(f"AVISO: {len(result.skipped_products)} productos no son mapeables.")
        for issue in result.issues:
            print(f"{issue.level.upper()}: [{issue.code}] {issue.message}")
        if args.strict and (result.missing_products or result.skipped_products):
            return 1
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
