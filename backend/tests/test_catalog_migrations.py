"""Migración inicial: tablas, constraints, SQLite WAL y downgrade (F1.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _config(database_path: Path) -> Config:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_initial_migration_creates_catalog_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "datos" / "cesta.db"
    config = _config(database_path)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        product_checks = {check["name"] for check in inspector.get_check_constraints("products")}
        sync_checks = {check["name"] for check in inspector.get_check_constraints("sync_runs")}
        product_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("products")
        }
        with engine.connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar()
    finally:
        engine.dispose()

    assert {
        "categories",
        "products",
        "sync_runs",
        "sync_category_runs",
        "product_allergens",
        "alembic_version",
    } <= tables
    assert "ck_products_allergen_status" in product_checks
    assert "ck_products_package_price" in product_checks
    assert "ck_products_package_quantity" in product_checks
    assert "ck_sync_runs_status" in sync_checks
    assert "uq_products_external_id" in product_uniques
    assert version == "20261026_0002"


def test_migration_enforces_constraints_and_can_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "datos" / "cesta.db"
    config = _config(database_path)
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into categories (id, name, level, is_food, sort_order) "
                    "values (1, 'Sección', 0, 1, 0)"
                )
            )
            connection.execute(
                text("insert into sync_runs (postal_code, status) values ('22002', 'success')")
            )
            connection.execute(
                text(
                    "insert into products (external_id, name, category_id, allergen_status) "
                    "values ('9001', 'Producto', 1, 'unknown')"
                )
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "insert into products (external_id, name, category_id, allergen_status) "
                    "values ('9002', 'Producto inválido', 1, 'quizá')"
                )
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "insert into products (external_id, name, category_id, allergen_status) "
                    "values ('9001', 'Duplicado', 1, 'unknown')"
                )
            )
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert "products" not in tables
    assert "categories" not in tables
