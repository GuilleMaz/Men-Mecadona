"""Horizontes, presupuestos, exclusiones y bloqueos reales del menú (F4.9).

Todos los escenarios usan el catálogo sintético de ``optimizer_fixtures`` y una
SQLite temporal. No se llama a Mercadona, no se usa la base real y no se
persisten menús fuera de la sesión de cada test.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace

import pytest
from ortools.sat.python import cp_model
from sqlalchemy.orm import Session, sessionmaker

from app.models.dishes import Dish
from app.schemas.menu import MenuSettings
from app.schemas.seed import SeedIngredient, SeedProduct
from app.services import optimizer as optimizer_module
from app.services.eligibility import DishEligibility, PreferenceSnapshot, evaluate_dishes
from app.services.menu_service import MenuService
from app.services.optimizer import (
    SOLVER_SEED,
    OptimizationLock,
    OptimizationRequest,
    OptimizationResult,
    optimize_menu,
)
from app.services.pricing import ProductFormat, price_basket, purchasable_formats, scale_quantity
from app.services.seed import SeedDocuments, validate_catalog_mappings
from tests.domain_fixtures import make_product, make_profile, make_sync_run
from tests.optimizer_fixtures import OptimizerCatalog, build_balanced_catalog

HORIZONS: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 10),
    (2, 2),
    (3, 4),
    (7, 2),
    (7, 4),
    (14, 4),
    (14, 10),
)


def _request(
    *,
    people: int,
    days: int,
    budget_cents: int = 1_000_000,
    preferences: PreferenceSnapshot | None = None,
    max_repeats: int = 1,
    locks: Sequence[OptimizationLock] = (),
) -> OptimizationRequest:
    return OptimizationRequest(
        people=people,
        days=days,
        budget_cents=budget_cents,
        preferences=preferences or PreferenceSnapshot(),
        max_repeats=max_repeats,
        locks=tuple(locks),
        stage1_seconds=0.9,
        stage2_seconds=0.9,
        fallback_seconds=0.45,
    )


def _assert_menu_shape(
    catalog: OptimizerCatalog,
    result: OptimizationResult,
    *,
    people: int,
    days: int,
    max_repeats: int,
    budget_cents: int,
) -> None:
    assignments = result.assignments
    assert len(assignments) == days * 2
    assert result.solver_ticket_cents <= budget_cents
    assert result.status != "timeout"
    assert result.violations == 0

    dishes_by_id = {dish.id: dish for dish in catalog.dishes}
    ingredients_by_id = {ingredient.id: ingredient for ingredient in catalog.ingredients}
    counts = Counter(assignment.dish_id for assignment in assignments)
    assert counts
    assert max(counts.values()) <= max_repeats

    for day in range(days):
        day_assignments = [item for item in assignments if item.day_index == day]
        assert {item.slot for item in day_assignments} == {"lunch", "dinner"}
        assert len({item.dish_id for item in day_assignments}) == 2
        for assignment in day_assignments:
            dish = dishes_by_id[assignment.dish_id]
            assert assignment.slot in dish.meal_types_json
        for group in ("vegetable", "protein", "carb"):
            rations_milli = 0
            for assignment in day_assignments:
                dish = dishes_by_id[assignment.dish_id]
                for link in dish.ingredients:
                    ingredient = ingredients_by_id[link.ingredient_id]
                    if ingredient.serving_group != group:
                        continue
                    coef = scale_quantity(link.quantity_milli, people, dish.base_servings)
                    rations_milli += (coef * 1_000_000) // ingredient.serving_size_milli
            assert rations_milli >= people * 1_000_000


@pytest.fixture
def session(catalog_session_factory: sessionmaker[Session]) -> Session:
    with catalog_session_factory() as db_session:
        yield db_session


@pytest.mark.parametrize(("days", "people"), HORIZONS)
def test_horizons_and_people_cover_the_menu_and_stay_under_ten_seconds(
    session: Session,
    days: int,
    people: int,
) -> None:
    catalog = build_balanced_catalog(session, days=days)
    started = time.perf_counter()

    result = optimize_menu(catalog.eligibility, _request(people=people, days=days))

    elapsed = time.perf_counter() - started
    assert elapsed < 10.0
    _assert_menu_shape(
        catalog,
        result,
        people=people,
        days=days,
        max_repeats=1,
        budget_cents=1_000_000,
    )


def test_exact_budget_fits_and_one_cent_less_is_infeasible(session: Session) -> None:
    """Con un único menú posible, el ticket es su mínimo real."""

    catalog = build_balanced_catalog(session, days=1)
    fish_lunch = next(
        dish for dish in catalog.dishes_with_slot("lunch") if "fish" in dish.protein_sources_json
    )
    legume_dinner = next(
        dish
        for dish in catalog.dishes_with_slot("dinner")
        if "legumes" in dish.protein_sources_json
    )
    preferences = PreferenceSnapshot(
        excluded_dish_ids=frozenset(
            dish.id for dish in catalog.dishes if dish.id not in {fish_lunch.id, legume_dinner.id}
        )
    )
    eligibility = evaluate_dishes(session, preferences)

    wide = optimize_menu(
        eligibility,
        _request(people=2, days=1, budget_cents=1_000_000, preferences=preferences),
    )
    ticket_cents = wide.solver_ticket_cents
    assert wide.status in {"optimal", "feasible"}
    assert ticket_cents > 0

    exact = optimize_menu(
        eligibility,
        _request(people=2, days=1, budget_cents=ticket_cents, preferences=preferences),
    )
    assert exact.status in {"optimal", "feasible"}
    assert exact.solver_ticket_cents == ticket_cents

    tight = optimize_menu(
        eligibility,
        _request(people=2, days=1, budget_cents=ticket_cents - 1, preferences=preferences),
    )
    assert tight.status == "infeasible"
    assert tight.is_preview is True
    assert tight.reason == "budget"
    assert tight.minimum_ticket_cents is not None
    assert tight.minimum_ticket_cents >= ticket_cents
    assert tight.minimum_ticket_cents > ticket_cents - 1
    assert tight.shortfall_cents == tight.minimum_ticket_cents - (ticket_cents - 1)


def test_tight_budget_on_balanced_catalog_is_coherent(session: Session) -> None:
    """Con variedad relajable, un céntimo menos puede devolver ``relaxed``."""

    catalog = build_balanced_catalog(session, days=2)
    wide = optimize_menu(catalog.eligibility, _request(people=2, days=2))
    ticket_cents = wide.solver_ticket_cents

    exact = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=2, budget_cents=ticket_cents),
    )
    assert exact.status != "timeout"
    assert exact.status != "infeasible"
    assert exact.solver_ticket_cents <= ticket_cents

    tight = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=2, budget_cents=ticket_cents - 1),
    )
    assert tight.status in {"relaxed", "infeasible"}
    if tight.status == "infeasible":
        assert tight.minimum_ticket_cents is not None
        assert tight.minimum_ticket_cents > ticket_cents - 1
        assert tight.shortfall_cents == tight.minimum_ticket_cents - (ticket_cents - 1)
    else:
        assert tight.violations > 0
        assert tight.solver_ticket_cents <= ticket_cents - 1


@pytest.mark.parametrize("mode", ["tag", "ingredient"])
def test_fish_exclusion_never_leaves_fish_in_the_menu(session: Session, mode: str) -> None:
    catalog = build_balanced_catalog(session, days=2)
    fish = catalog.ingredients_by_slug["fish"]
    fish_product_id = fish.products[0].product.id
    if mode == "tag":
        preferences = PreferenceSnapshot(excluded_tags=frozenset({"fish"}))
    else:
        preferences = PreferenceSnapshot(excluded_ingredient_ids=frozenset({fish.id}))
    eligibility = evaluate_dishes(session, preferences)

    result = optimize_menu(
        eligibility,
        _request(people=2, days=2, preferences=preferences),
    )

    assert result.status != "timeout"
    assert len(result.assignments) == 4
    dishes_by_id = {dish.id: dish for dish in catalog.dishes}
    for assignment in result.assignments:
        dish = dishes_by_id[assignment.dish_id]
        assert "fish" not in dish.protein_sources_json
        assert "fish" not in (dish.tags_json or [])
        assert fish.id not in {link.ingredient_id for link in dish.ingredients}
    assert fish_product_id not in result.packages


def test_unknown_product_is_excluded_with_a_declared_allergen(session: Session) -> None:
    preferences = PreferenceSnapshot(allergen_codes=frozenset({"gluten"}))
    catalog = build_balanced_catalog(
        session,
        days=1,
        preferences=preferences,
        unknown_chicken=True,
    )
    assert catalog.unknown_product_id is not None

    result = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=1, preferences=preferences),
    )

    assert result.status != "timeout"
    assert catalog.unknown_product_id not in result.packages
    chicken = catalog.ingredients_by_slug["chicken"]
    for dish_result in catalog.eligibility:
        for ingredient_result in dish_result.ingredients:
            if ingredient_result.ingredient.id != chicken.id:
                continue
            assert catalog.unknown_product_id not in {
                mapping.product.id for mapping in ingredient_result.eligible_products
            }


def test_shared_catalog_product_is_detected_by_the_validator(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_product(session, "shared-ext")
        documents = SeedDocuments(
            ingredients=[
                _seed_ingredient("rice", "shared-ext"),
                _seed_ingredient("pasta", "shared-ext"),
            ],
            dishes=[],
            version="test",
        )

        issues = validate_catalog_mappings(session, documents)

    codes = [issue.code for issue in issues if issue.level == "error"]
    assert "SHARED_CATALOG_PRODUCT" in codes


def _seed_ingredient(slug: str, external_id: str) -> SeedIngredient:
    return SeedIngredient(
        slug=slug,
        name=slug.replace("-", " ").title(),
        category="grains",
        group="carb",
        base_unit="g",
        serving_group="carb",
        serving_size_milli=60_000,
        products=[SeedProduct(external_id=external_id, priority=1, is_default=True)],
    )


def test_different_base_servings_sharing_an_ingredient_match_preview_ticket(
    session: Session,
) -> None:
    catalog = build_balanced_catalog(session, days=1)
    pair = _lunch_and_dinner_with_different_servings(catalog)
    lunch, dinner = pair
    preferences = PreferenceSnapshot(
        excluded_dish_ids=frozenset(
            dish.id for dish in catalog.dishes if dish.id not in {lunch.id, dinner.id}
        )
    )
    eligibility = evaluate_dishes(session, preferences)
    result = optimize_menu(
        eligibility,
        _request(people=2, days=1, preferences=preferences),
    )
    assert {assignment.dish_id for assignment in result.assignments} == {lunch.id, dinner.id}

    make_profile(session, people=2, days=1, budget_cents=1_000_000)
    make_sync_run(session)
    service = MenuService(session)
    menu = service.generate(
        profile_id=1,
        people=2,
        days=1,
        budget_cents=1_000_000,
        settings=MenuSettings(),
        optimization=result,
    )

    assert lunch.base_servings != dinner.base_servings
    formats = _formats_by_ingredient(eligibility)
    basket = price_basket(
        [entry.dish for entry in menu.entries],
        people=2,
        pantry={},
        formats_by_ingredient=formats,
    )
    assert basket.ticket_cents == menu.ticket_cents
    service.verify_identities(menu.id)


def _lunch_and_dinner_with_different_servings(
    catalog: OptimizerCatalog,
) -> tuple[Dish, Dish]:
    for lunch in catalog.dishes_with_slot("lunch"):
        for dinner in catalog.dishes_with_slot("dinner"):
            if lunch.base_servings == dinner.base_servings:
                continue
            lunch_ingredients = {link.ingredient_id for link in lunch.ingredients}
            dinner_ingredients = {link.ingredient_id for link in dinner.ingredients}
            if lunch_ingredients & dinner_ingredients:
                return lunch, dinner
    raise AssertionError(
        "El catálogo no tiene una pareja con raciones distintas y un ingrediente común."
    )


def _formats_by_ingredient(
    eligibility: Sequence[DishEligibility],
) -> dict[int, tuple[ProductFormat, ...]]:
    formats: dict[int, tuple[ProductFormat, ...]] = {}
    for result in eligibility:
        if not result.eligible:
            continue
        for item in result.ingredients:
            allowed = {mapping.product.id for mapping in item.eligible_products}
            formats[item.ingredient.id] = purchasable_formats(item.ingredient, allowed)
    return formats


def test_locks_survive_regeneration_and_unlock_regenerates(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=2, budget_cents=1_000_000)
        make_sync_run(session)
        catalog = build_balanced_catalog(session, days=2)
        request = _request(people=2, days=2)
        result = optimize_menu(catalog.eligibility, request)
        service = MenuService(session)
        menu = service.generate(
            profile_id=1,
            people=2,
            days=2,
            budget_cents=1_000_000,
            settings=MenuSettings(),
            optimization=result,
        )

        lunch = next(
            entry for entry in menu.entries if entry.day_index == 0 and entry.slot == "lunch"
        )
        locked_dish_id = lunch.dish_id
        lunch.locked = True
        session.commit()

        locked_request = replace(
            request,
            locks=(OptimizationLock(day_index=0, slot="lunch", dish_id=locked_dish_id),),
        )
        regenerated = service.regenerate(menu.id, request=locked_request)

        locked_entry = next(
            entry for entry in regenerated.entries if entry.day_index == 0 and entry.slot == "lunch"
        )
        assert locked_entry.dish_id == locked_dish_id
        assert locked_entry.locked is True
        assert regenerated.ticket_cents <= regenerated.budget_cents

        locked_entry.locked = False
        session.commit()
        unlocked = service.regenerate(menu.id, request=replace(request, locks=()))

        assert len(unlocked.entries) == 4
        assert unlocked.ticket_cents <= unlocked.budget_cents
        service.verify_identities(unlocked.id)


def test_solver_uses_one_worker_and_the_fixed_seed(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = build_balanced_catalog(session, days=1)
    captured: list[cp_model.CpSolver] = []

    class SpySolver(cp_model.CpSolver):
        def __init__(self) -> None:
            super().__init__()
            captured.append(self)

    monkeypatch.setattr(optimizer_module.cp_model, "CpSolver", SpySolver)

    optimize_menu(catalog.eligibility, _request(people=2, days=1))

    assert len(captured) >= 2
    assert all(solver.parameters.num_search_workers == 1 for solver in captured)
    assert all(solver.parameters.random_seed == SOLVER_SEED for solver in captured)
