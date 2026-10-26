"""Valida el seed y su mapeo contra el catálogo real (F2.7).

Uso desde la raíz del repositorio:

    cd backend
    uv run python ..\\scripts\\validate_seed.py

Comprueba estructura, referencias, unidades, flags derivados, cobertura,
alérgenos y que cada ingrediente tenga al menos un producto fijo del catálogo.
Devuelve código 1 si hay errores.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.services.seed import (  # noqa: E402
    SeedValidationError,
    load_seed_documents,
    validate_catalog_mappings,
)


def main() -> int:
    settings = get_settings()
    try:
        documents = load_seed_documents()
    except SeedValidationError as exc:
        print(f"ERROR de estructura: {exc}")
        return 1

    print(f"Seed: {len(documents.ingredients)} ingredientes, {len(documents.dishes)} platos")
    print(f"Versión: {documents.version}")

    engine = create_db_engine(settings)
    try:
        if not inspect(engine).has_table("products"):
            print("ERROR: faltan las tablas. Ejecuta primero: uv run alembic upgrade head")
            return 2
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            issues = validate_catalog_mappings(session, documents)
    finally:
        engine.dispose()

    for issue in issues:
        print(f"{issue.level.upper()}: [{issue.code}] {issue.message}")

    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]
    if errors:
        print(f"RESULTADO: FALLO ({len(errors)} errores, {len(warnings)} avisos)")
        return 1
    print(f"RESULTADO: OK ({len(warnings)} avisos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
