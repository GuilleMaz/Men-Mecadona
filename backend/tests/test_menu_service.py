"""Servicio transaccional de menús (F4.5).

Los tests usan platos, ingredientes y productos sintéticos y construyen a mano
el ``OptimizationResult``; no llaman al solver ni a Mercadona. El solver solo se
simula con ``monkeypatch`` en los tests de regeneración.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import Product
from app.models.dishes import DishIngredient
from app.models.ingredients import Ingredient
from app.models.menu import Menu
from app.models.profile import Exclusion, PantryItem
from app.schemas.menu import MenuSettings, PantrySnapshot
from app.services import menu_service as menu_service_module
from app.services.eligibility import PreferenceSnapshot, evaluate_dishes
from app.services.menu_service import MenuService, MenuServiceError
from app.services.optimizer import (
    EligibilityReport,
    OptimizationAssignment,
    OptimizationLock,
    OptimizationRequest,
    OptimizationResult,
    OptimizationStatus,
    OptimizerError,
)
from app.services.pricing import price_basket, purchasable_formats
from tests.domain_fixtures import (
    make_dish,
    make_ingredient,
    make_mapping,
    make_product,
    make_profile,
    make_sync_run,
)

BUDGET_CENTS = 1000
BASE_TICKET_CENTS = 865
SWAP_TICKET_CENTS = 915


@dataclass(frozen=True, slots=True)
class MenuEnv:
    """Identificadores sintéticos necesarios para construir menús en los tests."""

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


def _seed_menu_env(session: Session, *, with_sync: bool = True) -> MenuEnv:
    make_profile(session)
    if with_sync:
        make_sync_run(session)

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

    return MenuEnv(
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


def _assignments(
    env: MenuEnv,
    *,
    lunch_dish_id: int | None = None,
    dinner_dish_id: int | None = None,
) -> tuple[OptimizationAssignment, ...]:
    return (
        OptimizationAssignment(
            day_index=0,
            slot="lunch",
            dish_id=lunch_dish_id or env.chicken_rice_id,
            dish_name="Chicken rice",
            protein_source="chicken",
            locked=False,
        ),
        OptimizationAssignment(
            day_index=0,
            slot="dinner",
            dish_id=dinner_dish_id or env.veg_rice_id,
            dish_name="Vegetable rice",
            protein_source=None,
            locked=False,
        ),
    )


def _result(
    env: MenuEnv,
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
        assignments=tuple(assignments or _assignments(env)),
        packages={},
        solver_ticket_cents=solver_ticket_cents,
        violations=0,
        relaxation_codes=(),
        timed_out=timed_out,
        eligibility=EligibilityReport(
            eligible_dish_ids=(
                env.chicken_rice_id,
                env.veg_rice_id,
                env.chickpea_rice_id,
                env.lobster_rice_id,
                env.veg_soup_id,
            ),
            lunch_dish_ids=(env.chicken_rice_id, env.veg_soup_id),
            dinner_dish_ids=(
                env.veg_rice_id,
                env.chickpea_rice_id,
                env.lobster_rice_id,
            ),
            blocked_ingredient_ids=(),
        ),
        minimum_ticket_cents=minimum_ticket_cents,
        minimum_is_estimate=minimum_is_estimate,
        shortfall_cents=shortfall_cents,
        suggestions=tuple(suggestions),
    )


def _generate(
    session: Session,
    env: MenuEnv,
    *,
    budget_cents: int = BUDGET_CENTS,
    settings: MenuSettings | None = None,
) -> Menu:
    service = MenuService(session)
    return service.generate(
        profile_id=1,
        people=2,
        days=1,
        budget_cents=budget_cents,
        settings=settings or MenuSettings(),
        optimization=_result(env, solver_ticket_cents=budget_cents),
    )


def _preview_ticket(session: Session, menu: Menu) -> int:
    """Ticket que calcularía F3 con los mismos platos, formatos y despensa."""
    settings = MenuSettings.model_validate(menu.settings_json)
    preferences = PreferenceSnapshot(
        allergen_codes=frozenset(settings.allergen_codes),
        excluded_ingredient_ids=frozenset(settings.excluded_ingredient_ids),
        excluded_dish_ids=frozenset(settings.excluded_dish_ids),
        excluded_tags=frozenset(settings.excluded_tags),
    )
    eligibility = evaluate_dishes(session, preferences)
    dish_by_id = {item.dish.id: item.dish for item in eligibility if item.eligible}
    ingredients: dict[int, Ingredient] = {}
    allowed: dict[int, set[int]] = {}
    for item in eligibility:
        for ingredient_eligibility in item.ingredients:
            ingredient_id = ingredient_eligibility.ingredient.id
            ingredients[ingredient_id] = ingredient_eligibility.ingredient
            allowed.setdefault(ingredient_id, set()).update(
                mapping.product_id for mapping in ingredient_eligibility.eligible_products
            )
    formats_by_ingredient = {
        ingredient_id: purchasable_formats(
            ingredient,
            allowed_product_ids=allowed[ingredient_id],
        )
        for ingredient_id, ingredient in ingredients.items()
    }
    pantry = {item.ingredient_id: item.quantity_milli for item in settings.pantry}
    basket = price_basket(
        [dish_by_id[entry.dish_id] for entry in menu.entries],
        menu.people,
        pantry,
        formats_by_ingredient,
    )
    return basket.ticket_cents


def test_generate_persists_menu_and_verifies_identities(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        menu = _generate(session, env)

        assert menu.id is not None
        assert menu.status == "optimal"
        assert menu.price_status == "current"
        assert menu.timed_out is False
        assert menu.postal_code == "22002"
        assert menu.warehouse == "4389"
        assert menu.ticket_cents == BASE_TICKET_CENTS
        assert len(menu.entries) == 2
        assert len(menu.shopping_items) == 4
        assert {item.product_id for item in menu.shopping_items} == {
            env.chicken_product_id,
            env.rice_product_id,
            env.oil_product_id,
            env.veg_product_id,
        }
        assert sum(item.subtotal_cents for item in menu.shopping_items) == (menu.ticket_cents)
        assert sum(entry.entry_consumption_cents for entry in menu.entries) == (
            menu.consumption_cents
        )
        assert menu.ticket_cents + menu.pantry_consumption_cents == (
            menu.consumption_cents + menu.leftover_value_cents
        )
        for entry in menu.entries:
            assert (
                sum(row.consumption_cents for row in entry.ingredients)
                == entry.entry_consumption_cents
            )

        assert _preview_ticket(session, menu) == menu.ticket_cents
        MenuService(session).verify_identities(menu.id)


def test_generate_multi_day_with_partial_and_full_pantry(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        assignments = (
            OptimizationAssignment(0, "lunch", env.chicken_rice_id, "Chicken rice", "chicken"),
            OptimizationAssignment(0, "dinner", env.veg_rice_id, "Vegetable rice"),
            OptimizationAssignment(1, "lunch", env.chicken_rice_id, "Chicken rice", "chicken"),
            OptimizationAssignment(1, "dinner", env.veg_rice_id, "Vegetable rice"),
        )
        settings = MenuSettings(
            pantry=[
                PantrySnapshot(ingredient_id=env.rice_id, quantity_milli=100_000),
                PantrySnapshot(ingredient_id=env.veg_id, quantity_milli=500_000),
            ],
            max_repeats=2,
        )

        menu = service.generate(
            profile_id=1,
            people=2,
            days=2,
            budget_cents=2000,
            settings=settings,
            optimization=_result(
                env,
                assignments=assignments,
                solver_ticket_cents=2000,
            ),
        )

        assert len(menu.entries) == 4
        assert menu.ticket_cents == 1215
        assert all(item.ingredient_id != env.veg_id for item in menu.shopping_items)
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        assert rice_item.pantry_quantity_milli == 100_000
        assert sum(item.subtotal_cents for item in menu.shopping_items) == (menu.ticket_cents)
        assert sum(entry.entry_consumption_cents for entry in menu.entries) == (
            menu.consumption_cents
        )
        assert menu.ticket_cents + menu.pantry_consumption_cents == (
            menu.consumption_cents + menu.leftover_value_cents
        )
        service.verify_identities(menu.id)


def test_swap_cheap_keeps_checked_state_and_recalculates(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        menu = service.set_shopping_item_checked(menu.id, rice_item.id, True)
        dinner = next(entry for entry in menu.entries if entry.slot == "dinner")

        menu = service.swap_entry(menu.id, dinner.id, env.chickpea_rice_id)

        assert menu.ticket_cents == SWAP_TICKET_CENTS
        assert (
            next(entry for entry in menu.entries if entry.slot == "dinner").dish_id
            == env.chickpea_rice_id
        )
        assert all(item.ingredient_id != env.veg_id for item in menu.shopping_items)
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        assert rice_item.checked is True
        service.verify_identities(menu.id)


def test_swap_expensive_returns_budget_exceeded_without_changes(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        service.set_shopping_item_checked(menu_id, rice_item.id, True)
        dinner = next(entry for entry in menu.entries if entry.slot == "dinner")

        with pytest.raises(MenuServiceError) as error:
            service.swap_entry(menu_id, dinner.id, env.lobster_rice_id)

        assert error.value.code == "BUDGET_EXCEEDED"
        assert error.value.status_code == 422
        assert error.value.details["ticket_cents"] > error.value.details["budget_cents"]

        session.expire_all()
        unchanged = session.get(Menu, menu_id)
        assert unchanged is not None
        assert unchanged.ticket_cents == BASE_TICKET_CENTS
        assert (
            next(entry for entry in unchanged.entries if entry.slot == "dinner").dish_id
            == env.veg_rice_id
        )
        rice_item = next(
            item for item in unchanged.shopping_items if item.product_id == env.rice_product_id
        )
        assert rice_item.checked is True


def test_recalculate_updates_ticket_and_revalidate_marks_stale(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id

        rice_product = session.get(Product, env.rice_product_id)
        assert rice_product is not None
        rice_product.package_price_cents = 200
        session.commit()

        menu = service.recalculate(menu_id)
        assert menu.ticket_cents == 950
        assert menu.price_status == "current"
        assert menu.revalidated_ticket_cents is None
        service.verify_identities(menu_id)

        rice_product = session.get(Product, env.rice_product_id)
        assert rice_product is not None
        rice_product.package_price_cents = 2000
        session.commit()

        menu = service.revalidate(menu_id)
        assert menu.ticket_cents == 950
        assert menu.ticket_cents <= menu.budget_cents
        assert menu.price_status == "stale"
        assert menu.revalidated_ticket_cents == 2750
        assert sum(item.subtotal_cents for item in menu.shopping_items) == menu.ticket_cents
        service.verify_identities(menu_id)

        # La lista persistida es la del último snapshot válido, no la calculada
        # con el precio que rompe el presupuesto.
        session.expire_all()
        unchanged = session.get(Menu, menu_id)
        assert unchanged is not None
        assert unchanged.ticket_cents == 950
        assert unchanged.revalidated_ticket_cents == 2750


def test_recalculate_uses_persisted_composition_of_the_entry(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        lunch = next(entry for entry in menu.entries if entry.slot == "lunch")
        original_chicken = next(
            row.used_milli for row in lunch.ingredients if row.ingredient_id == env.chicken_id
        )

        link = session.scalar(
            select(DishIngredient).where(
                DishIngredient.dish_id == env.chicken_rice_id,
                DishIngredient.ingredient_id == env.chicken_id,
            )
        )
        assert link is not None
        link.quantity_milli = 600_000
        session.commit()

        revalidated = service.revalidate(menu.id)

        assert revalidated.ticket_cents == BASE_TICKET_CENTS
        lunch = next(entry for entry in revalidated.entries if entry.slot == "lunch")
        assert (
            next(row.used_milli for row in lunch.ingredients if row.ingredient_id == env.chicken_id)
            == original_chicken
        )
        service.verify_identities(menu.id)


def test_revalidate_reports_product_unavailable_without_breaking_snapshot(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id
        chicken_product = session.get(Product, env.chicken_product_id)
        assert chicken_product is not None
        chicken_product.published = False
        session.commit()

        with pytest.raises(MenuServiceError) as error:
            service.revalidate(menu_id)

        assert error.value.code == "PRODUCT_UNAVAILABLE"
        assert error.value.status_code == 409
        session.expire_all()
        unchanged = session.get(Menu, menu_id)
        assert unchanged is not None
        assert unchanged.ticket_cents == BASE_TICKET_CENTS
        service.verify_identities(menu_id)


def test_set_pantry_sufficient_reduces_ticket_without_touching_global_pantry(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)

        menu = service.set_pantry_sufficient(menu.id, env.chicken_id)

        assert menu.ticket_cents == 415
        assert menu.ticket_cents < BASE_TICKET_CENTS
        assert all(item.ingredient_id != env.chicken_id for item in menu.shopping_items)
        settings = MenuSettings.model_validate(menu.settings_json)
        assert any(
            item.ingredient_id == env.chicken_id and item.quantity_milli == 300_000
            for item in settings.pantry
        )
        global_pantry = session.scalar(select(func.count()).select_from(PantryItem))
        assert global_pantry == 0
        service.verify_identities(menu.id)


def test_exclude_entry_scope_menu_replaces_and_keeps_exclusion_in_snapshot(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        service.set_shopping_item_checked(menu_id, rice_item.id, True)
        dinner = next(entry for entry in menu.entries if entry.slot == "dinner")

        menu = service.exclude_entry(menu_id, dinner.id, "menu")

        assert menu.ticket_cents == SWAP_TICKET_CENTS
        assert (
            next(entry for entry in menu.entries if entry.slot == "dinner").dish_id
            == env.chickpea_rice_id
        )
        settings = MenuSettings.model_validate(menu.settings_json)
        assert env.veg_rice_id in settings.excluded_dish_ids
        assert session.scalar(select(func.count()).select_from(Exclusion)) == 0
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        assert rice_item.checked is True
        service.verify_identities(menu_id)


def test_exclude_entry_scope_profile_creates_profile_exclusion(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        dinner = next(entry for entry in menu.entries if entry.slot == "dinner")

        menu = service.exclude_entry(menu.id, dinner.id, "profile")

        assert (
            next(entry for entry in menu.entries if entry.slot == "dinner").dish_id
            == env.chickpea_rice_id
        )
        settings = MenuSettings.model_validate(menu.settings_json)
        assert env.veg_rice_id in settings.excluded_dish_ids
        exclusion = session.scalar(
            select(Exclusion).where(
                Exclusion.profile_id == 1,
                Exclusion.dish_id == env.veg_rice_id,
            )
        )
        assert exclusion is not None
        service.verify_identities(menu.id)


def test_regenerate_respects_locks_and_propagates_locks_reason(
    catalog_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id
        lunch = next(entry for entry in menu.entries if entry.slot == "lunch")
        lunch.locked = True
        session.commit()
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        service.set_shopping_item_checked(menu_id, rice_item.id, True)
        captured_locks: list[tuple[OptimizationLock, ...]] = []

        def fake_optimize(
            _eligibility: object,
            request: OptimizationRequest,
        ) -> OptimizationResult:
            captured_locks.append(request.locks)
            return _result(
                env,
                assignments=(
                    OptimizationAssignment(
                        0,
                        "lunch",
                        env.chicken_rice_id,
                        "Chicken rice",
                        "chicken",
                        locked=True,
                    ),
                    OptimizationAssignment(
                        0,
                        "dinner",
                        env.chickpea_rice_id,
                        "Chickpea rice",
                        "legume",
                    ),
                ),
                solver_ticket_cents=BUDGET_CENTS,
            )

        monkeypatch.setattr(menu_service_module, "optimize_menu", fake_optimize)
        menu = service.regenerate(menu_id)

        assert captured_locks == [(OptimizationLock(0, "lunch", env.chicken_rice_id),)]
        lunch = next(entry for entry in menu.entries if entry.slot == "lunch")
        assert lunch.locked is True
        assert (
            next(entry for entry in menu.entries if entry.slot == "dinner").dish_id
            == env.chickpea_rice_id
        )
        assert menu.ticket_cents == SWAP_TICKET_CENTS
        assert menu.status == "optimal"
        rice_item = next(
            item for item in menu.shopping_items if item.product_id == env.rice_product_id
        )
        assert rice_item.checked is True

        def failing_optimize(
            _eligibility: object,
            _request: object,
        ) -> OptimizationResult:
            raise OptimizerError(
                "NO_FEASIBLE_MENU",
                "Los bloqueos hacen inviable el menú.",
                reason="locks",
            )

        monkeypatch.setattr(menu_service_module, "optimize_menu", failing_optimize)
        with pytest.raises(MenuServiceError) as error:
            service.regenerate(menu_id)

        assert error.value.code == "NO_FEASIBLE_MENU"
        assert error.value.reason == "locks"
        session.expire_all()
        unchanged = session.get(Menu, menu_id)
        assert unchanged is not None
        assert unchanged.ticket_cents == SWAP_TICKET_CENTS
        assert (
            next(entry for entry in unchanged.entries if entry.slot == "dinner").dish_id
            == env.chickpea_rice_id
        )


@pytest.mark.parametrize(
    ("optimizer_status", "expected_code", "expected_status", "expected_reason"),
    [
        ("timeout", "SOLVER_TIMEOUT", 200, "timeout"),
        ("infeasible", "BUDGET_EXCEEDED", 422, "budget"),
    ],
)
def test_regenerate_maps_terminal_optimizer_states(
    catalog_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    optimizer_status: OptimizationStatus,
    expected_code: str,
    expected_status: int,
    expected_reason: str,
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id

        def fake_optimize(
            _eligibility: object,
            _request: OptimizationRequest,
        ) -> OptimizationResult:
            return _result(
                env,
                status=optimizer_status,
                is_preview=optimizer_status == "infeasible",
                reason=expected_reason,
                minimum_ticket_cents=2500,
                minimum_is_estimate=True,
                shortfall_cents=1500,
            )

        monkeypatch.setattr(menu_service_module, "optimize_menu", fake_optimize)
        with pytest.raises(MenuServiceError) as error:
            service.regenerate(menu_id)

        assert error.value.code == expected_code
        assert error.value.status_code == expected_status
        assert error.value.reason == expected_reason
        if optimizer_status == "infeasible":
            assert error.value.details["minimum_ticket_cents"] == 2500
            assert error.value.details["shortfall_cents"] == 1500
        session.expire_all()
        unchanged = session.get(Menu, menu_id)
        assert unchanged is not None
        assert unchanged.ticket_cents == BASE_TICKET_CENTS


@pytest.mark.parametrize(
    ("status", "is_preview"),
    [("infeasible", True), ("timeout", False)],
)
def test_generate_rejects_non_persistible_results(
    catalog_session_factory: sessionmaker[Session],
    status: OptimizationStatus,
    is_preview: bool,
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)

        with pytest.raises(MenuServiceError) as error:
            service.generate(
                profile_id=1,
                people=2,
                days=1,
                budget_cents=BUDGET_CENTS,
                settings=MenuSettings(),
                optimization=_result(env, status=status, is_preview=is_preview),
            )

        assert error.value.code == "INVALID_OPTIMIZATION"
        assert error.value.status_code == 422
        assert session.scalar(select(func.count()).select_from(Menu)) == 0


def test_generate_rejects_assignments_above_max_repeats(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        assignments = (
            OptimizationAssignment(0, "lunch", env.chicken_rice_id, "Chicken rice", "chicken"),
            OptimizationAssignment(0, "dinner", env.veg_rice_id, "Vegetable rice"),
            OptimizationAssignment(1, "lunch", env.chicken_rice_id, "Chicken rice", "chicken"),
            OptimizationAssignment(1, "dinner", env.veg_rice_id, "Vegetable rice"),
        )

        with pytest.raises(MenuServiceError) as error:
            service.generate(
                profile_id=1,
                people=2,
                days=2,
                budget_cents=2000,
                settings=MenuSettings(max_repeats=1),
                optimization=_result(
                    env,
                    assignments=assignments,
                    solver_ticket_cents=2000,
                ),
            )

        assert error.value.code == "INVALID_OPTIMIZATION"
        assert error.value.status_code == 422
        assert session.scalar(select(func.count()).select_from(Menu)) == 0


def test_generate_rejects_sync_from_another_warehouse(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        bad_run = make_sync_run(session, postal_code="28001", warehouse="9999")

        with pytest.raises(MenuServiceError) as error:
            service.generate(
                profile_id=1,
                people=2,
                days=1,
                budget_cents=BUDGET_CENTS,
                settings=MenuSettings(),
                optimization=_result(env),
                sync_run_id=bad_run.id,
            )

        assert error.value.code == "WAREHOUSE_UNAVAILABLE"
        assert error.value.status_code == 503
        assert session.scalar(select(func.count()).select_from(Menu)) == 0


def test_generate_requires_a_confirmed_sync(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session, with_sync=False)
        service = MenuService(session)

        with pytest.raises(MenuServiceError) as error:
            service.generate(
                profile_id=1,
                people=2,
                days=1,
                budget_cents=BUDGET_CENTS,
                settings=MenuSettings(),
                optimization=_result(env),
            )

        assert error.value.code == "WAREHOUSE_UNAVAILABLE"
        assert session.scalar(select(func.count()).select_from(Menu)) == 0


def test_generate_rejects_inconsistent_solver_ticket(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)

        with pytest.raises(MenuServiceError) as error:
            service.generate(
                profile_id=1,
                people=2,
                days=1,
                budget_cents=BUDGET_CENTS,
                settings=MenuSettings(),
                optimization=_result(env, solver_ticket_cents=BUDGET_CENTS + 1),
            )

        assert error.value.code == "INCONSISTENT_MENU"
        assert error.value.status_code == 500
        assert session.scalar(select(func.count()).select_from(Menu)) == 0


def test_not_found_for_menu_entry_and_shopping_item(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu_id = menu.id
        dinner = next(entry for entry in menu.entries if entry.slot == "dinner")
        item = menu.shopping_items[0]

        with pytest.raises(MenuServiceError) as missing_menu:
            service.swap_entry(menu_id + 999, dinner.id, env.chickpea_rice_id)
        assert missing_menu.value.code == "NOT_FOUND"

        with pytest.raises(MenuServiceError) as missing_entry:
            service.swap_entry(menu_id, dinner.id + 999, env.chickpea_rice_id)
        assert missing_entry.value.code == "NOT_FOUND"

        with pytest.raises(MenuServiceError) as missing_item:
            service.set_shopping_item_checked(menu_id + 999, item.id, True)
        assert missing_item.value.code == "NOT_FOUND"

        with pytest.raises(MenuServiceError) as unknown_item:
            service.set_shopping_item_checked(menu_id, item.id + 999, True)
        assert unknown_item.value.code == "NOT_FOUND"


def test_verify_identities_detects_corruption(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        env = _seed_menu_env(session)
        service = MenuService(session)
        menu = _generate(session, env)
        menu.entries[0].entry_consumption_cents += 1
        session.flush()

        with pytest.raises(MenuServiceError) as error:
            service.verify_identities(menu.id)

        assert error.value.code == "INCONSISTENT_MENU"
        assert error.value.status_code == 500
        assert error.value.details["failures"]
