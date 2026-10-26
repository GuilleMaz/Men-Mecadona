"""Optimizador CP-SAT: elegibilidad, modelo y objetivo lexicográfico (F4.2-F4.4).

Todos los tests usan platos e ingredientes sintéticos y una base SQLite temporal.
No hay llamadas a Mercadona ni se persiste ningún menú.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import Product
from app.models.dishes import Dish
from app.models.ingredients import Ingredient
from app.services.eligibility import (
    DishEligibility,
    PreferenceSnapshot,
    evaluate_dishes,
)
from app.services.optimizer import (
    EligibilityReport,
    OptimizationLock,
    OptimizationRequest,
    OptimizationResult,
    OptimizerError,
    build_eligibility_report,
    optimize_menu,
)
from app.services.pricing import (
    ProductFormat,
    plan_purchase,
    price_basket,
    purchasable_formats,
    scale_quantity,
)
from tests.domain_fixtures import make_dish, make_ingredient, make_mapping, make_product
from tests.optimizer_fixtures import OptimizerCatalog, build_balanced_catalog


@pytest.fixture
def session(catalog_session_factory: sessionmaker[Session]) -> Session:
    with catalog_session_factory() as db_session:
        yield db_session


def _request(
    *,
    people: int,
    days: int,
    budget_cents: int = 1_000_000,
    preferences: PreferenceSnapshot | None = None,
    pantry: dict[int, int] | None = None,
    max_repeats: int = 1,
    locks: Sequence[OptimizationLock] = (),
    stage1_seconds: float = 2.0,
    stage2_seconds: float = 2.0,
    fallback_seconds: float = 1.0,
) -> OptimizationRequest:
    return OptimizationRequest(
        people=people,
        days=days,
        budget_cents=budget_cents,
        preferences=preferences or PreferenceSnapshot(),
        pantry=pantry or {},
        max_repeats=max_repeats,
        locks=tuple(locks),
        stage1_seconds=stage1_seconds,
        stage2_seconds=stage2_seconds,
        fallback_seconds=fallback_seconds,
    )


def _ingredient_with_product(
    session: Session,
    slug: str,
    *,
    group: str,
    serving_group: str,
    serving_size_milli: int,
    price_cents: int,
    package_quantity_milli: int = 1_000_000,
    protein_source: str | None = None,
) -> tuple[Ingredient, Product]:
    ingredient = make_ingredient(
        session,
        slug,
        group=group,
        serving_group=serving_group,
        serving_size_milli=serving_size_milli,
        protein_source=protein_source,
    )
    product = make_product(
        session,
        f"p-{slug}",
        package_quantity_milli=package_quantity_milli,
        package_unit=ingredient.base_unit,
        package_price_cents=price_cents,
    )
    make_mapping(session, ingredient, product)
    return ingredient, product


def _full_meal(
    session: Session,
    slug: str,
    *,
    ingredients: Sequence[tuple[Ingredient, int]],
    meal_types: Sequence[str],
    protein_source: str,
    carbs: str,
    light: bool = False,
    tags: Sequence[str] = (),
    base_servings: int = 2,
) -> Dish:
    return make_dish(
        session,
        slug,
        base_servings=base_servings,
        meal_types=meal_types,
        protein_sources=[protein_source],
        carbs=carbs,
        light=light,
        tags=tags,
        ingredients=ingredients,
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

    dishes_by_id = {dish.id: dish for dish in catalog.dishes}
    ingredients_by_id = {ingredient.id: ingredient for ingredient in catalog.ingredients}
    counts = Counter(assignment.dish_id for assignment in assignments)
    assert counts
    assert max(counts.values()) <= max_repeats

    for day in range(days):
        day_assignments = [assignment for assignment in assignments if assignment.day_index == day]
        assert {assignment.slot for assignment in day_assignments} == {"lunch", "dinner"}
        assert len({assignment.dish_id for assignment in day_assignments}) == len(day_assignments)
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


def _menu_ticket(
    menu: Sequence[Dish],
    *,
    people: int,
    ingredients_by_id: dict[int, Ingredient],
    formats: dict[int, tuple[ProductFormat, ...]],
) -> int:
    needs: dict[int, int] = {}
    for dish in menu:
        for link in dish.ingredients:
            coef = scale_quantity(link.quantity_milli, people, dish.base_servings)
            needs[link.ingredient_id] = needs.get(link.ingredient_id, 0) + coef
    return sum(
        plan_purchase(
            ingredients_by_id[ingredient_id],
            need_milli,
            formats.get(ingredient_id),
        ).ticket_cents
        for ingredient_id, need_milli in needs.items()
        if need_milli > 0
    )


def _variety_violations(menu: Sequence[tuple[Dish, str]], days: int) -> int:
    dishes = [dish for dish, _ in menu]
    protein_sources = {source for dish in dishes for source in dish.protein_sources_json}
    fish = sum(
        1
        for dish in dishes
        if "fish" in (dish.tags_json or []) or "fish" in dish.protein_sources_json
    )
    legumes = sum(
        1
        for dish in dishes
        if "legume" in (dish.tags_json or []) or "legumes" in dish.protein_sources_json
    )
    red_meat = sum(
        1
        for dish in dishes
        if "red_meat" in (dish.tags_json or [])
        or bool({"beef", "pork"} & set(dish.protein_sources_json))
    )
    light_dinners = sum(1 for dish, slot in menu if slot == "dinner" and dish.light)
    carb_sources = {dish.carbs for dish in dishes if dish.carbs is not None}

    return (
        max(0, min(3, days) - len(protein_sources))
        + max(0, -(-days // 7) - fish)
        + max(0, -(-days // 7) - legumes)
        + max(0, red_meat - -(-(days * 3) // 7))
        + max(0, -(-days // 2) - light_dinners)
        + max(0, min(2, days) - len(carb_sources))
    )


def test_build_eligibility_report_explains_exclusions(session: Session) -> None:
    onion, _ = _ingredient_with_product(
        session,
        "onion",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    chicken, _ = _ingredient_with_product(
        session,
        "chicken",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=350,
        protein_source="chicken",
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=130,
    )
    empty_ingredient = make_ingredient(session, "unavailable", group="other")

    eligible_lunch = _full_meal(
        session,
        "eligible-lunch",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
    )
    eligible_dinner = _full_meal(
        session,
        "eligible-dinner",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["dinner"],
        protein_source="chicken",
        carbs="rice",
        light=True,
    )
    excluded_dish = _full_meal(
        session,
        "excluded-dish",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
    )
    excluded_tag = _full_meal(
        session,
        "excluded-tag",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
        tags=["spicy"],
    )
    excluded_ingredient = _full_meal(
        session,
        "excluded-ingredient",
        ingredients=[(onion, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
    )
    blocked_ingredient = _full_meal(
        session,
        "blocked-ingredient",
        ingredients=[(empty_ingredient, 10_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
    )

    preferences = PreferenceSnapshot(
        excluded_dish_ids=frozenset({excluded_dish.id}),
        excluded_tags=frozenset({"spicy"}),
        excluded_ingredient_ids=frozenset({onion.id}),
    )
    report = build_eligibility_report(evaluate_dishes(session, preferences))

    assert report.eligible_dish_ids == tuple(sorted((eligible_lunch.id, eligible_dinner.id)))
    assert report.lunch_dish_ids == (eligible_lunch.id,)
    assert report.dinner_dish_ids == (eligible_dinner.id,)
    assert report.blocked_ingredient_ids == tuple(sorted((onion.id, empty_ingredient.id)))
    assert report.dish_reasons[excluded_dish.id] == ("dish_excluded",)
    assert report.dish_reasons[excluded_tag.id] == ("tag_excluded",)
    assert report.dish_reasons[excluded_ingredient.id] == ("ingredient_excluded",)
    assert report.dish_reasons[blocked_ingredient.id] == ("no_eligible_product",)
    assert set(report.dish_reasons) == {
        excluded_dish.id,
        excluded_tag.id,
        excluded_ingredient.id,
        blocked_ingredient.id,
    }


def test_both_meal_type_is_expanded_to_lunch_and_dinner(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    dish = make_dish(
        session,
        "both",
        meal_types=["both"],
        ingredients=[(carrot, 300_000)],
    )

    report = build_eligibility_report(evaluate_dishes(session, PreferenceSnapshot()))

    assert dish.id in report.eligible_dish_ids
    assert dish.id in report.lunch_dish_ids
    assert dish.id in report.dinner_dish_ids


def test_optimize_two_days_two_people(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=2)

    result = optimize_menu(catalog.eligibility, _request(people=2, days=2))

    assert result.status in {"optimal", "feasible"}
    assert result.violations == 0
    assert result.relaxation_codes == ()
    _assert_menu_shape(
        catalog,
        result,
        people=2,
        days=2,
        max_repeats=1,
        budget_cents=1_000_000,
    )


@pytest.mark.parametrize(("days", "people"), [(7, 2), (14, 4)])
def test_long_horizons_resolve_under_ten_seconds(
    session: Session,
    days: int,
    people: int,
) -> None:
    catalog = build_balanced_catalog(session, days=days)
    started = time.perf_counter()

    result = optimize_menu(
        catalog.eligibility,
        _request(
            people=people,
            days=days,
            stage1_seconds=1.0,
            stage2_seconds=1.0,
            fallback_seconds=0.5,
        ),
    )

    elapsed = time.perf_counter() - started
    assert elapsed < 10.0
    assert result.status != "timeout"
    assert result.violations == 0
    _assert_menu_shape(
        catalog,
        result,
        people=people,
        days=days,
        max_repeats=1,
        budget_cents=1_000_000,
    )


def test_demand_uses_per_dish_base_servings(session: Session) -> None:
    tomato, tomato_product = _ingredient_with_product(
        session,
        "tomato",
        group="other",
        serving_group="none",
        serving_size_milli=100_000,
        price_cents=100,
        package_quantity_milli=100_000,
    )
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    chicken, _ = _ingredient_with_product(
        session,
        "chicken",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=350,
        protein_source="chicken",
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=130,
    )
    lunch = _full_meal(
        session,
        "lunch",
        ingredients=[
            (tomato, 100_000),
            (carrot, 300_000),
            (chicken, 200_000),
            (rice, 120_000),
        ],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
        base_servings=2,
    )
    dinner = _full_meal(
        session,
        "dinner",
        ingredients=[
            (tomato, 100_000),
            (carrot, 600_000),
            (chicken, 400_000),
            (rice, 240_000),
        ],
        meal_types=["dinner"],
        protein_source="chicken",
        carbs="rice",
        light=True,
        base_servings=4,
    )
    assert lunch.id != dinner.id

    eligibility = evaluate_dishes(session, PreferenceSnapshot())
    result = optimize_menu(eligibility, _request(people=2, days=1))

    assert {assignment.dish_id for assignment in result.assignments} == {lunch.id, dinner.id}
    # 100 g × 2 / 2 + 100 g × 2 / 4 = 150 g; el paquete es de 100 g.
    assert result.packages[tomato_product.id] == 2


def test_declared_allergen_excludes_unknown_product(session: Session) -> None:
    preferences = PreferenceSnapshot(allergen_codes=frozenset({"gluten"}))
    catalog = build_balanced_catalog(
        session,
        days=1,
        preferences=preferences,
        unknown_chicken=True,
    )
    assert catalog.unknown_product_id is not None
    chicken = catalog.ingredients_by_slug["chicken"]
    chicken_result = next(
        result
        for result in catalog.eligibility
        if result.eligible and result.dish.slug == "lunch-chicken-0"
    )
    chicken_eligibility = next(
        item for item in chicken_result.ingredients if item.ingredient.id == chicken.id
    )
    known_product_id = next(
        mapping.product.id
        for mapping in chicken_eligibility.eligible_products
        if mapping.product.id != catalog.unknown_product_id
    )

    lock = OptimizationLock(day_index=0, slot="lunch", dish_id=chicken_result.dish.id)
    result = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=1, locks=(lock,)),
    )

    assert catalog.unknown_product_id not in {
        mapping.product.id for mapping in chicken_eligibility.eligible_products
    }
    assert catalog.unknown_product_id not in result.packages
    assert known_product_id in result.packages


def test_impossible_budget_returns_infeasible_preview(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=1)

    result = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=1, budget_cents=1),
    )

    assert result.status == "infeasible"
    assert result.is_preview is True
    assert result.reason == "budget"
    assert result.minimum_ticket_cents is not None
    assert result.minimum_ticket_cents > 1
    assert result.shortfall_cents == result.minimum_ticket_cents - 1
    assert len(result.suggestions) == 4
    assert len(result.assignments) == 2
    assert result.packages
    assert result.eligibility.eligible_dish_ids
    assert result.timed_out is False

    # El mínimo debe ser el plan canónico del propio menú preview, no las q
    # arbitrarias del fallback.
    dishes_by_id = {dish.id: dish for dish in catalog.dishes}
    formats = _formats_by_ingredient(catalog.eligibility)
    preview = price_basket(
        [dishes_by_id[assignment.dish_id] for assignment in result.assignments],
        2,
        {},
        formats,
    )
    assert result.minimum_ticket_cents == preview.ticket_cents
    assert result.solver_ticket_cents == preview.ticket_cents


def test_stage_one_timeout_falls_back_to_a_budget_menu(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=7)

    result = optimize_menu(
        catalog.eligibility,
        _request(
            people=2,
            days=7,
            budget_cents=100_000,
            stage1_seconds=0.001,
            stage2_seconds=0.2,
            fallback_seconds=1.0,
        ),
    )

    assert result.status in {"feasible", "relaxed"}
    assert result.timed_out is True
    assert len(result.assignments) == 14
    assert result.solver_ticket_cents <= 100_000
    _assert_menu_shape(
        catalog,
        result,
        people=2,
        days=7,
        max_repeats=1,
        budget_cents=100_000,
    )


def test_locks_are_respected_and_incompatible_lock_is_rejected(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=2)
    locked_dish = catalog.dishes_with_slot("lunch")[2]
    lock = OptimizationLock(day_index=0, slot="lunch", dish_id=locked_dish.id)

    result = optimize_menu(
        catalog.eligibility,
        _request(people=2, days=2, locks=(lock,)),
    )

    assignment = next(
        item for item in result.assignments if item.day_index == 0 and item.slot == "lunch"
    )
    assert assignment.dish_id == locked_dish.id
    assert assignment.locked is True
    _assert_menu_shape(
        catalog,
        result,
        people=2,
        days=2,
        max_repeats=1,
        budget_cents=1_000_000,
    )

    dinner_dish = catalog.dishes_with_slot("dinner")[0]
    invalid_lock = OptimizationLock(
        day_index=0,
        slot="lunch",
        dish_id=dinner_dish.id,
    )
    with pytest.raises(OptimizerError) as error:
        optimize_menu(
            catalog.eligibility,
            _request(people=2, days=2, locks=(invalid_lock,)),
        )
    assert error.value.code == "NO_FEASIBLE_MENU"
    assert error.value.reason == "locks"


def test_pantry_covers_ingredient_without_buying_it(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=1)
    carrot = catalog.ingredients_by_slug["carrot"]
    carrot_product_id = carrot.products[0].product.id
    locked_dish = catalog.dishes_with_slot("lunch")[0]

    result = optimize_menu(
        catalog.eligibility,
        _request(
            people=2,
            days=1,
            pantry={carrot.id: 10_000_000},
            locks=(OptimizationLock(0, "lunch", locked_dish.id),),
        ),
    )

    assert result.status in {"optimal", "feasible", "relaxed"}
    assert carrot_product_id not in result.packages
    _assert_menu_shape(
        catalog,
        result,
        people=2,
        days=1,
        max_repeats=1,
        budget_cents=1_000_000,
    )


def test_three_days_ten_people(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=3)

    result = optimize_menu(
        catalog.eligibility,
        _request(people=10, days=3, stage1_seconds=1.0, stage2_seconds=1.0),
    )

    assert result.status in {"optimal", "feasible", "relaxed"}
    _assert_menu_shape(
        catalog,
        result,
        people=10,
        days=3,
        max_repeats=1,
        budget_cents=1_000_000,
    )


def test_impossible_repeats_report_reason_repeats(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    chicken, _ = _ingredient_with_product(
        session,
        "chicken",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=350,
        protein_source="chicken",
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=130,
    )
    meals = [
        _full_meal(
            session,
            f"both-{index}",
            ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
            meal_types=["lunch", "dinner"],
            protein_source="chicken",
            carbs="rice",
            light=index > 0,
        )
        for index in range(3)
    ]
    assert len(meals) == 3

    with pytest.raises(OptimizerError) as error:
        optimize_menu(
            evaluate_dishes(session, PreferenceSnapshot()),
            _request(people=2, days=2, max_repeats=1),
        )

    assert error.value.code == "NO_FEASIBLE_MENU"
    assert error.value.reason == "repeats"


def test_lock_that_breaks_budget_reports_locks(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    chicken, _ = _ingredient_with_product(
        session,
        "chicken",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=100,
        protein_source="chicken",
    )
    beef, _ = _ingredient_with_product(
        session,
        "beef",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=2_000,
        protein_source="beef",
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=100,
    )
    lunch_cheap = _full_meal(
        session,
        "lunch-cheap",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="chicken",
        carbs="rice",
    )
    lunch_expensive = _full_meal(
        session,
        "lunch-expensive",
        ingredients=[(carrot, 300_000), (beef, 200_000), (rice, 120_000)],
        meal_types=["lunch"],
        protein_source="beef",
        carbs="rice",
        tags=["red_meat"],
    )
    _full_meal(
        session,
        "dinner-cheap",
        ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
        meal_types=["dinner"],
        protein_source="chicken",
        carbs="rice",
        light=True,
    )
    _full_meal(
        session,
        "dinner-expensive",
        ingredients=[(carrot, 300_000), (beef, 200_000), (rice, 120_000)],
        meal_types=["dinner"],
        protein_source="beef",
        carbs="rice",
        tags=["red_meat"],
    )
    eligibility = evaluate_dishes(session, PreferenceSnapshot())
    assert lunch_cheap.id != lunch_expensive.id

    unlocked = optimize_menu(
        eligibility,
        _request(people=2, days=1, budget_cents=500),
    )
    assert unlocked.status in {"optimal", "feasible", "relaxed"}
    assert unlocked.solver_ticket_cents <= 500

    lock = OptimizationLock(
        day_index=0,
        slot="lunch",
        dish_id=lunch_expensive.id,
    )
    with pytest.raises(OptimizerError) as error:
        optimize_menu(
            eligibility,
            _request(people=2, days=1, budget_cents=500, locks=(lock,)),
        )

    assert error.value.code == "NO_FEASIBLE_MENU"
    assert error.value.reason == "locks"


def test_missing_daily_minimum_reports_minimums(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=130,
    )
    for slot in ("lunch", "dinner"):
        _full_meal(
            session,
            f"{slot}-without-protein",
            ingredients=[(carrot, 300_000), (rice, 120_000)],
            meal_types=[slot],
            protein_source="chicken",
            carbs="rice",
        )

    with pytest.raises(OptimizerError) as error:
        optimize_menu(
            evaluate_dishes(session, PreferenceSnapshot()),
            _request(people=2, days=1),
        )

    assert error.value.code == "NO_FEASIBLE_MENU"
    assert error.value.reason == "minimums"


def test_brute_force_matches_cheapest_menu(session: Session) -> None:
    catalog = build_balanced_catalog(session, days=1)
    ingredients_by_id = {ingredient.id: ingredient for ingredient in catalog.ingredients}
    formats = _formats_by_ingredient(catalog.eligibility)
    lunches = catalog.dishes_with_slot("lunch")
    dinners = catalog.dishes_with_slot("dinner")

    candidates: list[tuple[int, int]] = []
    for lunch in lunches:
        for dinner in dinners:
            menu = ((lunch, "lunch"), (dinner, "dinner"))
            candidates.append(
                (
                    _variety_violations(menu, days=1),
                    _menu_ticket(
                        [lunch, dinner],
                        people=2,
                        ingredients_by_id=ingredients_by_id,
                        formats=formats,
                    ),
                )
            )
    best = min(candidates)

    result = optimize_menu(catalog.eligibility, _request(people=2, days=1))

    assert result.status == "optimal"
    assert (result.violations, result.solver_ticket_cents) == best


def test_variety_impossible_is_reported_as_relaxed(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    chicken, _ = _ingredient_with_product(
        session,
        "chicken",
        group="protein",
        serving_group="protein",
        serving_size_milli=100_000,
        price_cents=350,
        protein_source="chicken",
    )
    rice, _ = _ingredient_with_product(
        session,
        "rice",
        group="carb",
        serving_group="carb",
        serving_size_milli=60_000,
        price_cents=130,
    )
    for index, slot in enumerate(("lunch", "dinner")):
        _full_meal(
            session,
            f"{slot}-chicken",
            ingredients=[(carrot, 300_000), (chicken, 200_000), (rice, 120_000)],
            meal_types=[slot],
            protein_source="chicken",
            carbs="rice",
            light=index == 1,
        )

    result = optimize_menu(
        evaluate_dishes(session, PreferenceSnapshot()),
        _request(people=2, days=1),
    )

    assert result.status == "relaxed"
    assert result.violations == 2
    assert result.relaxation_codes == ("fish", "legumes")


def test_no_eligible_dishes_raises(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    dish = make_dish(
        session,
        "excluded",
        meal_types=["lunch"],
        ingredients=[(carrot, 300_000)],
    )
    preferences = PreferenceSnapshot(excluded_dish_ids=frozenset({dish.id}))
    eligibility = evaluate_dishes(session, preferences)

    with pytest.raises(OptimizerError) as error:
        optimize_menu(eligibility, _request(people=2, days=1))

    assert error.value.code == "NO_ELIGIBLE_DISHES"


def test_empty_slot_raises_no_assignment(session: Session) -> None:
    carrot, _ = _ingredient_with_product(
        session,
        "carrot",
        group="vegetable",
        serving_group="vegetable",
        serving_size_milli=150_000,
        price_cents=100,
    )
    make_dish(
        session,
        "lunch-only",
        meal_types=["lunch"],
        ingredients=[(carrot, 300_000)],
    )
    eligibility = evaluate_dishes(session, PreferenceSnapshot())
    report: EligibilityReport = build_eligibility_report(eligibility)
    assert report.eligible_dish_ids

    with pytest.raises(OptimizerError) as error:
        optimize_menu(eligibility, _request(people=2, days=1))

    assert error.value.code == "NO_FEASIBLE_MENU"
    assert error.value.reason == "no_assignment"
