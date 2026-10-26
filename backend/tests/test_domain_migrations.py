"""Migración de dominio: ingredientes, platos, perfil, exclusiones y despensa (F2.1)."""

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


def _insert_base_rows(connection: object) -> None:
    connection.execute(
        text(
            "insert into categories (id, name, level, is_food, sort_order) "
            "values (1, 'Cat', 0, 1, 0)"
        )
    )
    connection.execute(
        text(
            "insert into products (external_id, name, category_id, allergen_status) "
            "values ('9001', 'Producto', 1, 'unknown')"
        )
    )
    connection.execute(
        text(
            'insert into ingredients (slug, name, category, "group", base_unit, '
            "serving_group, serving_size_milli) values "
            "('rice', 'Arroz', 'grains', 'carb', 'g', 'carb', 60000)"
        )
    )
    connection.execute(
        text(
            "insert into dishes (slug, name, base_servings, seed_version) "
            "values ('rice-dish', 'Arroz', 2, 'test')"
        )
    )
    connection.execute(
        text("insert into profiles (id, people, days, budget_cents) values (1, 2, 7, 7000)")
    )


def test_domain_migration_creates_constraints_and_partial_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "datos" / "cesta.db"
    config = _config(database_path)
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        indexes = {index["name"] for index in inspector.get_indexes("exclusions")}
        ingredient_indexes = {
            index["name"] for index in inspector.get_indexes("ingredient_products")
        }
        profile_checks = {check["name"] for check in inspector.get_check_constraints("profiles")}
        with engine.connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar()
    finally:
        engine.dispose()

    assert {
        "ingredients",
        "ingredient_products",
        "dishes",
        "dish_ingredients",
        "profiles",
        "exclusions",
        "pantry_items",
    } <= tables
    assert {
        "uq_exclusions_profile_ingredient",
        "uq_exclusions_profile_dish",
        "uq_exclusions_profile_tag",
    } <= indexes
    assert "uq_ingredient_products_default" in ingredient_indexes
    assert "ck_profiles_single_row" in profile_checks
    assert version == "20261026_0004"


def test_domain_constraints_reject_invalid_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "datos" / "cesta.db"
    config = _config(database_path)
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            _insert_base_rows(connection)

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("insert into profiles (id, people, days, budget_cents) values (2, 2, 7, 7000)")
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("insert into exclusions (profile_id, ingredient_id, dish_id) values (1, 1, 1)")
            )

        with engine.begin() as connection:
            connection.execute(
                text("insert into exclusions (profile_id, ingredient_id) values (1, 1)")
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("insert into exclusions (profile_id, ingredient_id) values (1, 1)")
            )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into ingredient_products "
                    "(ingredient_id, product_id, is_default, priority) "
                    "values (1, 1, 1, 1)"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "insert into ingredient_products "
                    "(ingredient_id, product_id, is_default, priority) "
                    "values (1, 1, 0, 2)"
                )
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "insert into dish_ingredients (dish_id, ingredient_id, quantity_milli) "
                    "values (1, 1, 0)"
                )
            )
    finally:
        engine.dispose()

    command.downgrade(config, "20261026_0001")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert "ingredients" not in tables
    assert "dishes" not in tables
