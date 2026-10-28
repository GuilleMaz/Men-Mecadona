"""Migración de menús, entradas y lista de la compra (F4.1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.db import create_engine_for_url
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MENU_TABLES = ("menus", "menu_entries", "menu_entry_ingredients", "shopping_items")


def _config(database_path: Path) -> Config:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "datos" / "cesta.db"
    command.upgrade(_config(database_path), "head")
    engine = create_engine_for_url(f"sqlite:///{database_path.as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_base_rows(connection: Connection) -> None:
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


def _insert_menu(connection: Connection, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "id": 1,
        "profile_id": 1,
        "people": 2,
        "days": 7,
        "budget_cents": 7000,
        "status": "optimal",
        "price_status": "current",
        "ticket_cents": 5000,
        "consumption_cents": 4500,
        "pantry_consumption_cents": 300,
        "leftover_value_cents": 200,
        "violations": 0,
    }
    values.update(overrides)
    connection.execute(
        text(
            "insert into menus (id, profile_id, people, days, budget_cents, status, "
            "price_status, ticket_cents, consumption_cents, pantry_consumption_cents, "
            "leftover_value_cents, violations) values (:id, :profile_id, :people, :days, "
            ":budget_cents, :status, :price_status, :ticket_cents, :consumption_cents, "
            ":pantry_consumption_cents, :leftover_value_cents, :violations)"
        ),
        values,
    )


def _insert_entry(
    connection: Connection,
    *,
    entry_id: int = 1,
    menu_id: int = 1,
    day_index: int = 0,
    slot: str = "lunch",
    course: str = "main",
    dish_id: int = 1,
    dish_name: str = "Arroz",
) -> None:
    connection.execute(
        text(
            "insert into menu_entries "
            "(id, menu_id, day_index, slot, course, dish_id, dish_name) "
            "values (:entry_id, :menu_id, :day_index, :slot, :course, :dish_id, :dish_name)"
        ),
        {
            "entry_id": entry_id,
            "menu_id": menu_id,
            "day_index": day_index,
            "slot": slot,
            "course": course,
            "dish_id": dish_id,
            "dish_name": dish_name,
        },
    )


def _insert_entry_ingredient(
    connection: Connection,
    *,
    entry_id: int = 1,
    ingredient_id: int = 1,
    product_id: int = 1,
    used_milli: int = 120_000,
    consumption_cents: int = 90,
) -> None:
    connection.execute(
        text(
            "insert into menu_entry_ingredients "
            "(entry_id, ingredient_id, product_id, used_milli, consumption_cents) "
            "values (:entry_id, :ingredient_id, :product_id, :used_milli, :consumption_cents)"
        ),
        {
            "entry_id": entry_id,
            "ingredient_id": ingredient_id,
            "product_id": product_id,
            "used_milli": used_milli,
            "consumption_cents": consumption_cents,
        },
    )


def _insert_shopping_item(connection: Connection, **overrides: Any) -> None:
    values: dict[str, Any] = {
        "menu_id": 1,
        "product_id": 1,
        "ingredient_id": 1,
        "packages": 1,
        "package_quantity_milli": 1_000_000,
        "package_price_cents": 150,
        "subtotal_cents": 150,
    }
    values.update(overrides)
    connection.execute(
        text(
            "insert into shopping_items (menu_id, product_id, ingredient_id, packages, "
            "package_quantity_milli, package_price_cents, subtotal_cents) values "
            "(:menu_id, :product_id, :ingredient_id, :packages, :package_quantity_milli, "
            ":package_price_cents, :subtotal_cents)"
        ),
        values,
    )


def test_menu_migration_creates_tables_constraints_and_version(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    tables = set(inspector.get_table_names())
    unique_constraints = {
        table: {item["name"] for item in inspector.get_unique_constraints(table)}
        for table in MENU_TABLES
    }
    checks = {
        table: {item["name"] for item in inspector.get_check_constraints(table)}
        for table in MENU_TABLES
    }
    menu_columns = {item["name"] for item in inspector.get_columns("menus")}
    with migrated_engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version")).scalar_one()

    assert set(MENU_TABLES) <= tables
    assert {"violations", "relaxation_codes_json"} <= menu_columns
    assert "uq_menu_entries_menu_slot_course" in unique_constraints["menu_entries"]
    assert (
        "uq_menu_entry_ingredients_entry_ingredient" in unique_constraints["menu_entry_ingredients"]
    )
    assert "uq_shopping_items_menu_product" in unique_constraints["shopping_items"]
    assert "ck_menus_status" in checks["menus"]
    assert "ck_menus_price_status" in checks["menus"]
    assert "ck_menu_entries_slot" in checks["menu_entries"]
    assert "ck_menu_entries_course" in checks["menu_entries"]
    assert "ck_shopping_items_packages" in checks["shopping_items"]
    assert "ck_menus_amounts" in checks["menus"]
    assert "ck_menus_violations" in checks["menus"]
    assert "ck_menus_ticket_within_budget" in checks["menus"]
    assert "ck_menus_previous_ticket" in checks["menus"]
    assert {"previous_ticket_cents", "revalidated_at"} <= menu_columns
    assert "course" in {item["name"] for item in inspector.get_columns("menu_entries")}
    assert "role" in {item["name"] for item in inspector.get_columns("dishes")}
    assert version == "20261026_0006"


def test_menu_migration_matches_models(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_unique_constraints_reject_duplicate_rows(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)
        _insert_entry(connection)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_entry(connection, entry_id=2)

    with migrated_engine.begin() as connection:
        _insert_shopping_item(connection)
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_shopping_item(connection)

    with migrated_engine.begin() as connection:
        _insert_entry_ingredient(connection)
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_entry_ingredient(connection)


def test_complement_course_allows_one_extra_entry_per_slot(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)
        _insert_entry(connection, course="main")
        _insert_entry(connection, entry_id=2, course="complement")

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_entry(connection, entry_id=3, course="complement")

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_entry(connection, entry_id=4, course="snack")


def test_legacy_menu_entries_default_to_main_course(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)
        connection.execute(
            text(
                "insert into menu_entries (id, menu_id, day_index, slot, dish_id, dish_name) "
                "values (1, 1, 0, 'lunch', 1, 'Arroz')"
            )
        )

    with migrated_engine.connect() as connection:
        course = connection.execute(
            text("select course from menu_entries where id = 1")
        ).scalar_one()
        dish_role = connection.execute(text("select role from dishes where id = 1")).scalar_one()

    assert course == "main"
    assert dish_role == "main"


def test_dish_roles_reject_invalid_values(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(text("update dishes set role = 'snack' where id = 1"))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("status", "invalid"),
        ("price_status", "expired"),
        ("people", 0),
        ("people", 11),
        ("days", 0),
        ("days", 15),
        ("budget_cents", 0),
        ("ticket_cents", -1),
        ("ticket_cents", 8000),
        ("violations", -1),
    ],
)
def test_menus_reject_invalid_values(migrated_engine: Engine, column: str, value: Any) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_menu(connection, **{column: value})


@pytest.mark.parametrize(
    ("day_index", "slot"),
    [(-1, "lunch"), (0, "breakfast")],
)
def test_menu_entries_reject_invalid_day_and_slot(
    migrated_engine: Engine, day_index: int, slot: str
) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_entry(connection, day_index=day_index, slot=slot)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("packages", 0),
        ("package_quantity_milli", 0),
        ("subtotal_cents", -1),
    ],
)
def test_shopping_items_reject_invalid_values(
    migrated_engine: Engine, column: str, value: Any
) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        _insert_shopping_item(connection, **{column: value})


def test_menu_entry_keeps_dish_name_snapshot_and_restricts_dish_delete(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _insert_base_rows(connection)
        _insert_menu(connection)
        _insert_entry(connection, dish_name="Nombre original")

    with migrated_engine.begin() as connection:
        connection.execute(text("update dishes set name = 'Nombre nuevo' where id = 1"))

    with migrated_engine.connect() as connection:
        stored_name = connection.execute(
            text("select dish_name from menu_entries where id = 1")
        ).scalar_one()
        current_dish_name = connection.execute(
            text("select name from dishes where id = 1")
        ).scalar_one()

    assert stored_name == "Nombre original"
    assert current_dish_name == "Nombre nuevo"

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(text("delete from dishes where id = 1"))


def test_menu_migration_downgrade_drops_menu_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "datos" / "cesta.db"
    config = _config(database_path)
    command.upgrade(config, "head")

    command.downgrade(config, "20261026_0002")

    engine = create_engine_for_url(f"sqlite:///{database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            version = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert set(MENU_TABLES).isdisjoint(tables)
    assert version == "20261026_0002"
