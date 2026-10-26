"""API de menús (F4.6).

Los tests usan una SQLite temporal y catálogos sintéticos. El solver se
sustituye por un resultado determinista en casi todo el archivo; un test final
usa el optimizador real para demostrar la integración completa. No hay red.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api import menus as menus_module
from app.config import Settings
from app.main import create_app
from app.models.catalog import Category, Product
from app.models.menu import Menu
from app.models.profile import Exclusion, PantryItem, Profile
from app.services import menu_service as menu_service_module
from app.services.optimizer import (
    EligibilityReport,
    OptimizationAssignment,
    OptimizationRequest,
    OptimizationResult,
    OptimizationStatus,
    OptimizerError,
)
from tests.domain_fixtures import (
    make_dish,
    make_ingredient,
    make_mapping,
    make_product,
    make_profile,
    make_sync_run,
)
from tests.optimizer_fixtures import build_balanced_catalog

LOCAL_HOST = "127.0.0.1:8000"
HEADERS = {"Host": LOCAL_HOST}
BUDGET_CENTS = 1000
BASE_TICKET_CENTS = 865
SWAP_TICKET_CENTS = 915


@dataclass(frozen=True, slots=True)
class MenuScenario:
    """Identificadores del catálogo sintético del escenario de menús."""

    chicken_id: int
    rice_id: int
    oil_id: int
    veg_id: int
    chickpea_id: int
    lobster_id: int
    chicken_product_id: int
    rice_product_id: int
    oil_product_id: int
    veg_product_id: int
    chickpea_product_id: int
    lobster_product_id: int
    chicken_rice_id: int
    veg_rice_id: int
    chickpea_rice_id: int
    lobster_rice_id: int
    veg_soup_id: int


def _seed_scenario(session: Session) -> MenuScenario:
    make_profile(session)
    make_sync_run(session)

    fresh = Category(id=10, name="Frescos", level=0, is_food=True, sort_order=1)
    session.add(fresh)
    session.flush()
    butcher = Category(
        id=11,
        name="Carnicería",
        parent_id=fresh.id,
        level=1,
        is_food=True,
        sort_order=1,
    )
    session.add(butcher)
    session.flush()

    chicken = make_ingredient(
        session,
        "chicken",
        name="Pollo",
        category="meat",
        group="protein",
        serving_group="protein",
        protein_source="chicken",
    )
    rice = make_ingredient(
        session,
        "rice",
        name="Arroz",
        category="grains",
        group="carb",
        serving_group="carb",
    )
    oil = make_ingredient(
        session,
        "olive-oil",
        name="Aceite de oliva",
        category="pantry",
        group="fat",
        base_unit="ml",
        serving_group="none",
    )
    veg = make_ingredient(
        session,
        "vegetables",
        name="Verduras",
        category="vegetables",
        group="vegetable",
        serving_group="vegetable",
    )
    chickpea = make_ingredient(
        session,
        "chickpea",
        name="Garbanzos",
        category="legumes",
        group="protein",
        serving_group="protein",
        protein_source="legume",
    )
    lobster = make_ingredient(
        session,
        "lobster",
        name="Bogavante",
        category="fish",
        group="protein",
        serving_group="protein",
        protein_source="lobster",
    )

    chicken_product = make_product(
        session,
        "CHICKEN-500",
        name="Pollo 500 g",
        package_quantity_milli=500_000,
        package_unit="g",
        package_price_cents=450,
        category_id=butcher.id,
    )
    rice_product = make_product(
        session,
        "RICE-1KG",
        name="Arroz 1 kg",
        package_quantity_milli=1_000_000,
        package_unit="g",
        package_price_cents=115,
    )
    oil_product = make_product(
        session,
        "OIL-1L",
        name="Aceite 1 L",
        package_quantity_milli=1_000_000,
        package_unit="ml",
        package_price_cents=200,
    )
    veg_product = make_product(
        session,
        "VEG-1KG",
        name="Verduras 1 kg",
        package_quantity_milli=1_000_000,
        package_unit="g",
        package_price_cents=100,
    )
    chickpea_product = make_product(
        session,
        "CHICKPEA-500",
        name="Garbanzos 500 g",
        package_quantity_milli=500_000,
        package_unit="g",
        package_price_cents=150,
    )
    lobster_product = make_product(
        session,
        "LOBSTER-500",
        name="Bogavante 500 g",
        package_quantity_milli=500_000,
        package_unit="g",
        package_price_cents=3000,
    )

    for ingredient, product in (
        (chicken, chicken_product),
        (rice, rice_product),
        (oil, oil_product),
        (veg, veg_product),
        (chickpea, chickpea_product),
        (lobster, lobster_product),
    ):
        make_mapping(session, ingredient, product, is_default=True)

    chicken_rice = make_dish(
        session,
        "chicken-rice",
        name="Chicken rice",
        meal_types=("lunch",),
        protein_sources=("chicken",),
        ingredients=[(chicken, 300_000), (rice, 160_000), (oil, 15_000)],
    )
    veg_rice = make_dish(
        session,
        "veg-rice",
        name="Vegetable rice",
        meal_types=("dinner",),
        ingredients=[(rice, 120_000), (veg, 200_000), (oil, 10_000)],
    )
    chickpea_rice = make_dish(
        session,
        "chickpea-rice",
        name="Chickpea rice",
        meal_types=("dinner",),
        protein_sources=("legume",),
        ingredients=[(chickpea, 200_000), (rice, 100_000), (oil, 10_000)],
    )
    lobster_rice = make_dish(
        session,
        "lobster-rice",
        name="Lobster rice",
        meal_types=("dinner",),
        protein_sources=("lobster",),
        ingredients=[(lobster, 300_000), (rice, 100_000), (oil, 10_000)],
    )
    veg_soup = make_dish(
        session,
        "veg-soup",
        name="Vegetable soup",
        meal_types=("lunch",),
        ingredients=[(veg, 300_000), (oil, 10_000)],
    )
    session.commit()

    return MenuScenario(
        chicken_id=chicken.id,
        rice_id=rice.id,
        oil_id=oil.id,
        veg_id=veg.id,
        chickpea_id=chickpea.id,
        lobster_id=lobster.id,
        chicken_product_id=chicken_product.id,
        rice_product_id=rice_product.id,
        oil_product_id=oil_product.id,
        veg_product_id=veg_product.id,
        chickpea_product_id=chickpea_product.id,
        lobster_product_id=lobster_product.id,
        chicken_rice_id=chicken_rice.id,
        veg_rice_id=veg_rice.id,
        chickpea_rice_id=chickpea_rice.id,
        lobster_rice_id=lobster_rice.id,
        veg_soup_id=veg_soup.id,
    )


@pytest.fixture
def scenario(catalog_session_factory: sessionmaker[Session]) -> MenuScenario:
    with catalog_session_factory() as session:
        return _seed_scenario(session)


@pytest.fixture
def client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
    scenario: MenuScenario,
) -> Iterator[TestClient]:
    app = create_app(catalog_settings, session_factory=catalog_session_factory)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def optimizer_client(
    catalog_settings: Settings,
    catalog_session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    """Cliente con el catálogo equilibrado del optimizador y sin escenario."""
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=1, budget_cents=1_000_000)
        make_sync_run(session)
        build_balanced_catalog(session, days=1)
        session.commit()
    app = create_app(catalog_settings, session_factory=catalog_session_factory)
    with TestClient(app) as test_client:
        yield test_client


def _assignments(
    scenario: MenuScenario,
    *,
    lunch_dish_id: int | None = None,
    dinner_dish_id: int | None = None,
    lunch_locked: bool = False,
) -> tuple[OptimizationAssignment, ...]:
    return (
        OptimizationAssignment(
            day_index=0,
            slot="lunch",
            dish_id=lunch_dish_id or scenario.chicken_rice_id,
            dish_name="Chicken rice",
            protein_source="chicken",
            locked=lunch_locked,
        ),
        OptimizationAssignment(
            day_index=0,
            slot="dinner",
            dish_id=dinner_dish_id or scenario.veg_rice_id,
            dish_name="Vegetable rice",
            protein_source=None,
        ),
    )


def _result(
    scenario: MenuScenario,
    *,
    assignments: Sequence[OptimizationAssignment] | None = None,
    solver_ticket_cents: int = BUDGET_CENTS,
    status: OptimizationStatus = "optimal",
    is_preview: bool = False,
    reason: str | None = None,
    timed_out: bool = False,
    minimum_ticket_cents: int | None = None,
    minimum_is_estimate: bool = False,
    shortfall_cents: int = 0,
    suggestions: Sequence[str] = (),
) -> OptimizationResult:
    return OptimizationResult(
        status=status,
        is_preview=is_preview,
        reason=reason,
        assignments=tuple(assignments if assignments is not None else _assignments(scenario)),
        packages={},
        solver_ticket_cents=solver_ticket_cents,
        violations=0,
        relaxation_codes=(),
        timed_out=timed_out,
        eligibility=EligibilityReport(
            eligible_dish_ids=(
                scenario.chicken_rice_id,
                scenario.veg_rice_id,
                scenario.chickpea_rice_id,
                scenario.lobster_rice_id,
                scenario.veg_soup_id,
            ),
            lunch_dish_ids=(scenario.chicken_rice_id, scenario.veg_soup_id),
            dinner_dish_ids=(
                scenario.veg_rice_id,
                scenario.chickpea_rice_id,
                scenario.lobster_rice_id,
            ),
            blocked_ingredient_ids=(),
        ),
        minimum_ticket_cents=minimum_ticket_cents,
        minimum_is_estimate=minimum_is_estimate,
        shortfall_cents=shortfall_cents,
        suggestions=tuple(suggestions),
    )


def _install_optimizer(
    monkeypatch: pytest.MonkeyPatch,
    result: OptimizationResult,
) -> None:
    def fake_optimize(
        _eligibility: object,
        _request: OptimizationRequest,
    ) -> OptimizationResult:
        return result

    monkeypatch.setattr(menus_module, "optimize_menu", fake_optimize)


def _generate(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: OptimizationResult | None = None,
    pantry: list[dict[str, int]] | None = None,
    max_repeats: int = 1,
    budget_cents: int = BUDGET_CENTS,
) -> dict[str, object]:
    _install_optimizer(monkeypatch, result or _result(scenario))
    payload: dict[str, object] = {
        "people": 2,
        "days": 1,
        "budget_cents": budget_cents,
        "max_repeats": max_repeats,
    }
    if pantry is not None:
        payload["pantry"] = pantry
    response = client.post("/api/menus/generate", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _menu_id(payload: dict[str, object]) -> int:
    value = payload["menu_id"]
    assert isinstance(value, int)
    return value


def _detail(client: TestClient, menu_id: int) -> dict[str, object]:
    response = client.get(f"/api/menus/{menu_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _entry(detail: dict[str, object], slot: str) -> dict[str, object]:
    entries = detail["entries"]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        if entry["slot"] == slot:
            return entry
    raise AssertionError(f"No hay entrada para {slot}")


def _shopping(client: TestClient, menu_id: int) -> dict[str, object]:
    response = client.get(f"/api/menus/{menu_id}/shopping-list", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _count(factory: sessionmaker[Session], model: type[object]) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


# ----------------------------------------------------------------------
# Generación
# ----------------------------------------------------------------------


def test_generate_persists_menu_and_returns_entries(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    payload = _generate(client, scenario, monkeypatch)

    assert payload["status"] == "optimal"
    assert payload["is_preview"] is False
    assert payload["reason"] is None
    assert payload["menu_id"] is not None
    assert payload["ticket_cents"] == BASE_TICKET_CENTS
    assert payload["consumption_cents"] is not None
    assert payload["pantry_consumption_cents"] == 0
    assert payload["leftover_value_cents"] == (
        payload["ticket_cents"] - payload["consumption_cents"]
    )
    assert payload["price_status"] == "current"
    assert payload["timed_out"] is False
    assert payload["postal_code"] == "22002"
    assert payload["warehouse"] == "4389"
    assert payload["prices_captured_at"] is not None
    assert payload["minimum_ticket_cents"] is None
    assert payload["suggestions"] == []

    entries = payload["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 2
    lunch = _entry(payload, "lunch")
    assert lunch["dish_name"] == "Chicken rice"
    assert lunch["locked"] is False
    ingredients = lunch["ingredients"]
    assert isinstance(ingredients, list)
    assert {row["ingredient_name"] for row in ingredients} == {
        "Pollo",
        "Arroz",
        "Aceite de oliva",
    }
    assert sum(row["consumption_cents"] for row in ingredients) == lunch["entry_consumption_cents"]

    menu_id = _menu_id(payload)
    detail = _detail(client, menu_id)
    assert detail["id"] == menu_id
    assert detail["settings"]["max_repeats"] == 1
    assert detail["settings"]["optimizer_version"] == "1"
    assert len(detail["entries"]) == 2
    assert _count(catalog_session_factory, Menu) == 1


def test_generate_resolves_profile_preferences_and_pantry(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        profile = session.get(Profile, 1)
        assert profile is not None
        profile.allergen_codes_json = ["gluten"]
        session.add(
            Exclusion(profile_id=1, tag="spicy"),
        )
        session.add(
            PantryItem(
                profile_id=1,
                ingredient_id=scenario.rice_id,
                quantity_milli=100_000,
            )
        )
        session.commit()

    payload = _generate(client, scenario, monkeypatch)
    detail = _detail(client, _menu_id(payload))

    settings = detail["settings"]
    assert isinstance(settings, dict)
    assert settings["allergen_codes"] == ["gluten"]
    assert settings["excluded_tags"] == ["spicy"]
    assert settings["excluded_ingredient_ids"] == []
    assert settings["excluded_dish_ids"] == []
    assert settings["pantry"] == [{"ingredient_id": scenario.rice_id, "quantity_milli": 100_000}]

    shopping = _shopping(client, _menu_id(payload))
    assert shopping["pantry_items"] == [
        {
            "ingredient_id": scenario.rice_id,
            "ingredient_name": "Arroz",
            "base_unit": "g",
            "quantity_milli": 100_000,
        }
    ]


def test_generate_infeasible_preview_is_not_persisted(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    infeasible = _result(
        scenario,
        assignments=(),
        status="infeasible",
        is_preview=True,
        reason="budget",
        minimum_ticket_cents=2500,
        minimum_is_estimate=True,
        shortfall_cents=1500,
        suggestions=("Sube el presupuesto.", "Reduce los días."),
    )
    payload = _generate(client, scenario, monkeypatch, result=infeasible)

    assert payload["status"] == "infeasible"
    assert payload["is_preview"] is True
    assert payload["reason"] == "budget"
    assert payload["menu_id"] is None
    assert payload["ticket_cents"] is None
    assert payload["consumption_cents"] is None
    assert payload["pantry_consumption_cents"] is None
    assert payload["leftover_value_cents"] is None
    assert payload["minimum_ticket_cents"] == 2500
    assert payload["minimum_is_estimate"] is True
    assert payload["shortfall_cents"] == 1500
    assert payload["suggestions"] == ["Sube el presupuesto.", "Reduce los días."]
    assert payload["price_status"] is None
    assert payload["entries"] == []
    assert _count(catalog_session_factory, Menu) == 0


def test_generate_timeout_returns_state_without_menu(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    timeout = _result(
        scenario,
        assignments=(),
        status="timeout",
        reason="timeout",
        timed_out=True,
    )
    payload = _generate(client, scenario, monkeypatch, result=timeout)

    assert payload["status"] == "timeout"
    assert payload["is_preview"] is False
    assert payload["reason"] == "timeout"
    assert payload["menu_id"] is None
    assert payload["timed_out"] is True
    assert payload["ticket_cents"] is None
    assert payload["entries"] == []
    assert _count(catalog_session_factory, Menu) == 0


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("NO_ELIGIBLE_DISHES", None),
        ("NO_FEASIBLE_MENU", "locks"),
    ],
)
def test_generate_maps_optimizer_errors(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
    code: str,
    reason: str | None,
) -> None:
    def failing_optimize(
        _eligibility: object,
        _request: OptimizationRequest,
    ) -> OptimizationResult:
        raise OptimizerError(code, "No hay solución.", reason=reason)

    monkeypatch.setattr(menus_module, "optimize_menu", failing_optimize)
    response = client.post(
        "/api/menus/generate",
        headers=HEADERS,
        json={"people": 2, "days": 1, "budget_cents": BUDGET_CENTS},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code
    if reason is not None:
        assert error["details"]["reason"] == reason
    assert _count(catalog_session_factory, Menu) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"people": 0, "days": 1, "budget_cents": 1000},
        {"people": 11, "days": 1, "budget_cents": 1000},
        {"people": 2, "days": 0, "budget_cents": 1000},
        {"people": 2, "days": 15, "budget_cents": 1000},
        {"people": 2, "days": 1, "budget_cents": 0},
        {"people": 2, "days": 1, "budget_cents": 1_000_001},
        {
            "people": 2,
            "days": 1,
            "budget_cents": 1000,
            "allergen_codes": ["inventado"],
        },
        {"people": 2, "days": 1, "budget_cents": 1000, "max_repeats": 15},
    ],
)
def test_generate_validates_input(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    response = client.post("/api/menus/generate", headers=HEADERS, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_rejects_unknown_pantry_ingredient(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_optimizer(monkeypatch, _result(scenario))
    response = client.post(
        "/api/menus/generate",
        headers=HEADERS,
        json={
            "people": 2,
            "days": 1,
            "budget_cents": BUDGET_CENTS,
            "pantry": [{"ingredient_id": 999_999, "quantity_milli": 1}],
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["ingredient_ids"] == [999_999]


def test_generate_with_real_optimizer_persists_valid_menu(
    optimizer_client: TestClient,
    catalog_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        menus_module,
        "get_settings",
        lambda: catalog_settings.model_copy(update={"optimizer_time_limit_seconds": 2}),
    )
    response = optimizer_client.post(
        "/api/menus/generate",
        headers=HEADERS,
        json={"people": 2, "days": 1, "budget_cents": 1_000_000},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in {"optimal", "feasible", "relaxed"}
    assert payload["menu_id"] is not None
    assert payload["is_preview"] is False
    assert payload["ticket_cents"] <= 1_000_000
    assert len(payload["entries"]) == 2

    menu_id = _menu_id(payload)
    shopping = _shopping(optimizer_client, menu_id)
    assert shopping["ticket_cents"] == payload["ticket_cents"]
    assert shopping["ticket_cents"] == sum(
        section["subtotal_cents"] for section in shopping["sections"]
    )
    assert shopping["ticket_cents"] + shopping["pantry_consumption_cents"] == (
        shopping["consumption_cents"] + shopping["leftover_value_cents"]
    )
    assert _detail(optimizer_client, menu_id)["status"] == payload["status"]


# ----------------------------------------------------------------------
# Historial y detalle
# ----------------------------------------------------------------------


def test_list_menus_is_paginated(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [_menu_id(_generate(client, scenario, monkeypatch)) for _ in range(3)]

    default = client.get("/api/menus", headers=HEADERS)
    assert default.status_code == 200
    page = default.json()
    assert page["total"] == 3
    assert page["limit"] == 20
    assert page["offset"] == 0
    assert [item["id"] for item in page["items"]] == list(reversed(ids))

    first = client.get("/api/menus", headers=HEADERS, params={"limit": 2, "offset": 0})
    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == [ids[2], ids[1]]

    second = client.get("/api/menus", headers=HEADERS, params={"limit": 2, "offset": 2})
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == [ids[0]]

    invalid = client.get("/api/menus", headers=HEADERS, params={"limit": 101})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_menu_detail_and_not_found(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    detail = _detail(client, menu_id)

    assert detail["postal_code"] == "22002"
    assert detail["warehouse"] == "4389"
    assert detail["settings"]["max_repeats"] == 1
    lunch = _entry(detail, "lunch")
    assert lunch["dish_id"] == scenario.chicken_rice_id
    assert lunch["protein_source"] == "chicken"
    assert lunch["tags"] == []
    ingredient = next(
        row for row in lunch["ingredients"] if row["ingredient_id"] == scenario.chicken_id
    )
    assert ingredient["base_unit"] == "g"
    assert ingredient["used_milli"] == 300_000
    assert ingredient["product_id"] == scenario.chicken_product_id

    missing = client.get("/api/menus/9999", headers=HEADERS)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


# ----------------------------------------------------------------------
# Bloqueos y ajustes
# ----------------------------------------------------------------------


def test_patch_entry_lock_and_unlock(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    lunch = _entry(_detail(client, menu_id), "lunch")

    locked = client.patch(
        f"/api/menus/{menu_id}/entries/{lunch['id']}",
        headers=HEADERS,
        json={"locked": True},
    )
    assert locked.status_code == 200
    assert _entry(locked.json(), "lunch")["locked"] is True

    unlocked = client.patch(
        f"/api/menus/{menu_id}/entries/{lunch['id']}",
        headers=HEADERS,
        json={"locked": False},
    )
    assert unlocked.status_code == 200
    assert _entry(unlocked.json(), "lunch")["locked"] is False

    missing = client.patch(
        f"/api/menus/{menu_id}/entries/9999",
        headers=HEADERS,
        json={"locked": True},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_patch_entry_from_another_menu_is_not_found(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id = _menu_id(_generate(client, scenario, monkeypatch))
    second_id = _menu_id(_generate(client, scenario, monkeypatch))
    second_lunch = _entry(_detail(client, second_id), "lunch")

    response = client.patch(
        f"/api/menus/{first_id}/entries/{second_lunch['id']}",
        headers=HEADERS,
        json={"locked": True},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_swap_entry_updates_ticket_and_dish(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    dinner = _entry(_detail(client, menu_id), "dinner")

    response = client.post(
        f"/api/menus/{menu_id}/entries/{dinner['id']}/swap",
        headers=HEADERS,
        json={"dish_id": scenario.chickpea_rice_id},
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["ticket_cents"] == SWAP_TICKET_CENTS
    assert _entry(detail, "dinner")["dish_id"] == scenario.chickpea_rice_id
    assert detail["status"] == "feasible"


def test_swap_over_budget_is_rejected_without_changes(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    dinner = _entry(_detail(client, menu_id), "dinner")

    response = client.post(
        f"/api/menus/{menu_id}/entries/{dinner['id']}/swap",
        headers=HEADERS,
        json={"dish_id": scenario.lobster_rice_id},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "BUDGET_EXCEEDED"
    assert error["details"]["reason"] == "budget"
    assert error["details"]["ticket_cents"] > error["details"]["budget_cents"]

    unchanged = _detail(client, menu_id)
    assert unchanged["ticket_cents"] == BASE_TICKET_CENTS
    assert _entry(unchanged, "dinner")["dish_id"] == scenario.veg_rice_id


def test_swap_unknown_dish_is_not_found(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    dinner = _entry(_detail(client, menu_id), "dinner")

    response = client.post(
        f"/api/menus/{menu_id}/entries/{dinner['id']}/swap",
        headers=HEADERS,
        json={"dish_id": 9999},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_exclude_entry_scope_menu(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    dinner = _entry(_detail(client, menu_id), "dinner")

    response = client.post(
        f"/api/menus/{menu_id}/entries/{dinner['id']}/exclude",
        headers=HEADERS,
        json={"scope": "menu"},
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["ticket_cents"] == SWAP_TICKET_CENTS
    assert _entry(detail, "dinner")["dish_id"] == scenario.chickpea_rice_id
    assert scenario.veg_rice_id in detail["settings"]["excluded_dish_ids"]
    assert _count(catalog_session_factory, Exclusion) == 0


def test_exclude_entry_scope_profile_creates_exclusion(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    dinner = _entry(_detail(client, menu_id), "dinner")

    response = client.post(
        f"/api/menus/{menu_id}/entries/{dinner['id']}/exclude",
        headers=HEADERS,
        json={"scope": "profile"},
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert _entry(detail, "dinner")["dish_id"] == scenario.chickpea_rice_id
    with catalog_session_factory() as session:
        exclusion = session.scalar(
            select(Exclusion).where(
                Exclusion.profile_id == 1,
                Exclusion.dish_id == scenario.veg_rice_id,
            )
        )
        assert exclusion is not None


def test_regenerate_respects_locks_and_reports_locks_infeasible(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    lunch = _entry(_detail(client, menu_id), "lunch")
    locked = client.patch(
        f"/api/menus/{menu_id}/entries/{lunch['id']}",
        headers=HEADERS,
        json={"locked": True},
    )
    assert locked.status_code == 200

    captured: list[tuple[object, ...]] = []

    def fake_regenerate(
        _eligibility: object,
        request: OptimizationRequest,
    ) -> OptimizationResult:
        captured.append(request.locks)
        return _result(
            scenario,
            assignments=_assignments(
                scenario,
                dinner_dish_id=scenario.chickpea_rice_id,
                lunch_locked=True,
            ),
        )

    monkeypatch.setattr(menu_service_module, "optimize_menu", fake_regenerate)
    response = client.post(f"/api/menus/{menu_id}/regenerate", headers=HEADERS)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert len(captured) == 1
    locks = captured[0]
    assert len(locks) == 1
    assert locks[0].day_index == 0  # type: ignore[attr-defined]
    assert locks[0].slot == "lunch"  # type: ignore[attr-defined]
    assert locks[0].dish_id == scenario.chicken_rice_id  # type: ignore[attr-defined]
    assert _entry(detail, "lunch")["locked"] is True
    assert _entry(detail, "dinner")["dish_id"] == scenario.chickpea_rice_id
    assert detail["ticket_cents"] == SWAP_TICKET_CENTS

    def failing_regenerate(
        _eligibility: object,
        _request: OptimizationRequest,
    ) -> OptimizationResult:
        raise OptimizerError(
            "NO_FEASIBLE_MENU",
            "Los bloqueos hacen inviable el menú.",
            reason="locks",
        )

    monkeypatch.setattr(menu_service_module, "optimize_menu", failing_regenerate)
    failed = client.post(f"/api/menus/{menu_id}/regenerate", headers=HEADERS)
    assert failed.status_code == 422
    error = failed.json()["error"]
    assert error["code"] == "NO_FEASIBLE_MENU"
    assert error["details"]["reason"] == "locks"

    unchanged = _detail(client, menu_id)
    assert unchanged["ticket_cents"] == SWAP_TICKET_CENTS
    assert _entry(unchanged, "dinner")["dish_id"] == scenario.chickpea_rice_id


def test_regenerate_timeout_returns_solver_timeout_envelope(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))

    def timed_out_regenerate(
        _eligibility: object,
        _request: OptimizationRequest,
    ) -> OptimizationResult:
        return _result(
            scenario,
            assignments=(),
            status="timeout",
            reason="timeout",
            timed_out=True,
        )

    monkeypatch.setattr(menu_service_module, "optimize_menu", timed_out_regenerate)
    response = client.post(f"/api/menus/{menu_id}/regenerate", headers=HEADERS)

    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == "SOLVER_TIMEOUT"
    assert error["details"]["reason"] == "timeout"
    assert _detail(client, menu_id)["ticket_cents"] == BASE_TICKET_CENTS


def test_revalidate_marks_stale_when_prices_rise(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))

    with catalog_session_factory() as session:
        rice = session.get(Product, scenario.rice_product_id)
        assert rice is not None
        rice.package_price_cents = 2000
        session.commit()

    response = client.post(f"/api/menus/{menu_id}/revalidate", headers=HEADERS)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["ticket_cents"] == BASE_TICKET_CENTS
    assert detail["ticket_cents"] <= detail["budget_cents"]
    assert detail["price_status"] == "stale"
    assert detail["revalidated_ticket_cents"] == 2750

    shopping = _shopping(client, menu_id)
    assert shopping["ticket_cents"] == BASE_TICKET_CENTS
    assert shopping["ticket_cents"] == sum(
        section["subtotal_cents"] for section in shopping["sections"]
    )
    assert shopping["price_status"] == "stale"


# ----------------------------------------------------------------------
# Lista de la compra
# ----------------------------------------------------------------------


def test_shopping_list_sections_costs_and_pantry(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _generate(
        client,
        scenario,
        monkeypatch,
        pantry=[{"ingredient_id": scenario.rice_id, "quantity_milli": 100_000}],
    )
    menu_id = _menu_id(payload)

    shopping = _shopping(client, menu_id)
    assert shopping["ticket_cents"] == BASE_TICKET_CENTS
    assert shopping["item_count"] == 4
    assert shopping["checked_count"] == 0
    assert shopping["checked_total_cents"] == 0
    assert shopping["cost_per_meal_cents"] == 433
    assert shopping["cost_per_day_cents"] == BASE_TICKET_CENTS
    assert shopping["cost_per_person_day_cents"] == 433

    sections = shopping["sections"]
    assert [section["section_name"] for section in sections] == [
        "Despensa",
        "Frescos",
    ]
    assert sum(section["subtotal_cents"] for section in sections) == shopping["ticket_cents"]
    assert (
        sum(item["subtotal_cents"] for section in sections for item in section["items"])
        == shopping["ticket_cents"]
    )

    fresh = next(section for section in sections if section["section_name"] == "Frescos")
    assert fresh["section_id"] == 10
    assert [item["product_name"] for item in fresh["items"]] == ["Pollo 500 g"]
    chicken = fresh["items"][0]
    assert chicken["ingredient_name"] == "Pollo"
    assert chicken["packages"] == 1
    assert chicken["package_quantity_milli"] == 500_000
    assert chicken["package_unit"] == "g"
    assert chicken["subtotal_cents"] == 450
    assert chicken["checked"] is False

    assert shopping["pantry_items"] == [
        {
            "ingredient_id": scenario.rice_id,
            "ingredient_name": "Arroz",
            "base_unit": "g",
            "quantity_milli": 100_000,
        }
    ]
    assert shopping["ticket_cents"] + shopping["pantry_consumption_cents"] == (
        shopping["consumption_cents"] + shopping["leftover_value_cents"]
    )

    missing = client.get("/api/menus/9999/shopping-list", headers=HEADERS)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_patch_shopping_item_checked(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    shopping = _shopping(client, menu_id)
    rice_item = next(
        item
        for section in shopping["sections"]
        for item in section["items"]
        if item["product_id"] == scenario.rice_product_id
    )

    response = client.patch(
        f"/api/menus/{menu_id}/shopping-list/items/{rice_item['id']}",
        headers=HEADERS,
        json={"checked": True},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["checked_count"] == 1
    assert updated["checked_total_cents"] == rice_item["subtotal_cents"]
    checked = next(
        item
        for section in updated["sections"]
        for item in section["items"]
        if item["id"] == rice_item["id"]
    )
    assert checked["checked"] is True

    cleared = client.patch(
        f"/api/menus/{menu_id}/shopping-list/items/{rice_item['id']}",
        headers=HEADERS,
        json={"checked": False},
    )
    assert cleared.status_code == 200
    assert cleared.json()["checked_count"] == 0
    assert cleared.json()["checked_total_cents"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"checked": True, "already_have": True},
        {"already_have": False},
    ],
)
def test_patch_shopping_item_requires_exactly_one_action(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    shopping = _shopping(client, menu_id)
    item_id = shopping["sections"][0]["items"][0]["id"]

    response = client.patch(
        f"/api/menus/{menu_id}/shopping-list/items/{item_id}",
        headers=HEADERS,
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_shopping_item_from_another_menu_is_not_found(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id = _menu_id(_generate(client, scenario, monkeypatch))
    second_id = _menu_id(_generate(client, scenario, monkeypatch))
    second_item = _shopping(client, second_id)["sections"][0]["items"][0]

    response = client.patch(
        f"/api/menus/{first_id}/shopping-list/items/{second_item['id']}",
        headers=HEADERS,
        json={"checked": True},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_already_have_reduces_ticket_without_touching_global_pantry(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    shopping = _shopping(client, menu_id)
    chicken_item = next(
        item
        for section in shopping["sections"]
        for item in section["items"]
        if item["ingredient_id"] == scenario.chicken_id
    )

    response = client.patch(
        f"/api/menus/{menu_id}/shopping-list/items/{chicken_item['id']}",
        headers=HEADERS,
        json={"already_have": True},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["ticket_cents"] == 415
    assert updated["ticket_cents"] < BASE_TICKET_CENTS
    assert all(
        item["ingredient_id"] != scenario.chicken_id
        for section in updated["sections"]
        for item in section["items"]
    )
    pantry = next(
        item for item in updated["pantry_items"] if item["ingredient_id"] == scenario.chicken_id
    )
    assert pantry["ingredient_name"] == "Pollo"
    assert pantry["quantity_milli"] == 300_000
    assert updated["ticket_cents"] + updated["pantry_consumption_cents"] == (
        updated["consumption_cents"] + updated["leftover_value_cents"]
    )
    assert _count(catalog_session_factory, PantryItem) == 0


# ----------------------------------------------------------------------
# Exportación
# ----------------------------------------------------------------------


def test_export_markdown_without_cooking_steps(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))

    response = client.get(f"/api/menus/{menu_id}/export", headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert 'filename="menu-' in response.headers["content-disposition"]

    text = response.text
    assert text.startswith(f"# Menú #{menu_id}")
    assert "## Días" in text
    assert "## Lista de la compra" in text
    assert "Chicken rice" in text
    assert "Vegetable rice" in text
    assert "Pollo 500 g" in text
    assert "× 500 g" in text
    assert "500000 g" not in text
    lowered = text.lower()
    assert "receta" not in lowered
    assert "pasos" not in lowered


def test_export_csv_escapes_formulas_quotes_and_commas(
    client: TestClient,
    scenario: MenuScenario,
    monkeypatch: pytest.MonkeyPatch,
    catalog_session_factory: sessionmaker[Session],
) -> None:
    menu_id = _menu_id(_generate(client, scenario, monkeypatch))
    with catalog_session_factory() as session:
        chicken = session.get(Product, scenario.chicken_product_id)
        rice = session.get(Product, scenario.rice_product_id)
        assert chicken is not None and rice is not None
        chicken.name = "=SUM(A1:A2)"
        rice.name = 'Arroz, "extra"'
        session.commit()

    response = client.get(
        f"/api/menus/{menu_id}/export",
        headers=HEADERS,
        params={"format": "csv"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="menu-' in response.headers["content-disposition"]

    lines = response.text.splitlines()
    assert lines[0] == (
        "seccion,producto,ingrediente,paquetes,cantidad_paquete,unidad,"
        "precio_paquete_cents,subtotal_cents,marcado"
    )
    assert "'=SUM(A1:A2)" in response.text
    assert '"Arroz, ""extra"""' in response.text

    invalid = client.get(
        f"/api/menus/{menu_id}/export",
        headers=HEADERS,
        params={"format": "xml"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = client.get("/api/menus/9999/export", headers=HEADERS)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
