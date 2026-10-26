"""Integración real del optimizador con la persistencia de menús (F4.3-F4.5).

Usa el catálogo sintético del optimizador y una SQLite temporal. No llama a
Mercadona ni usa la base real del usuario.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.menu import Menu
from app.schemas.menu import MenuSettings
from app.services.eligibility import PreferenceSnapshot, evaluate_dishes
from app.services.menu_service import MenuService, MenuServiceError
from app.services.optimizer import OPTIMIZER_VERSION, OptimizationRequest, optimize_menu
from app.services.pricing import ProductFormat, price_basket, purchasable_formats
from tests.domain_fixtures import make_profile, make_sync_run
from tests.optimizer_fixtures import OptimizerCatalog, build_balanced_catalog

ALLERGEN_CATALOG = PreferenceSnapshot(allergen_codes=frozenset({"gluten"}))


def _request(
    *,
    days: int,
    budget_cents: int = 1_000_000,
    preferences: PreferenceSnapshot | None = None,
) -> OptimizationRequest:
    return OptimizationRequest(
        people=2,
        days=days,
        budget_cents=budget_cents,
        preferences=preferences or PreferenceSnapshot(),
        stage1_seconds=1.0,
        stage2_seconds=1.0,
        fallback_seconds=0.5,
    )


def _formats_by_ingredient(catalog: OptimizerCatalog) -> dict[int, tuple[ProductFormat, ...]]:
    formats: dict[int, tuple[ProductFormat, ...]] = {}
    for result in catalog.eligibility:
        if not result.eligible:
            continue
        for item in result.ingredients:
            allowed = {mapping.product.id for mapping in item.eligible_products}
            formats[item.ingredient.id] = purchasable_formats(item.ingredient, allowed)
    return formats


def test_optimizer_and_menu_service_match_preview_and_identities(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=2, budget_cents=1_000_000)
        make_sync_run(session)
        catalog = build_balanced_catalog(session, days=2)
        request = _request(days=2)
        result = optimize_menu(catalog.eligibility, request)

        assert result.status in {"optimal", "feasible", "relaxed"}
        assert len(result.assignments) == 4

        service = MenuService(session)
        menu = service.generate(
            profile_id=1,
            people=request.people,
            days=request.days,
            budget_cents=request.budget_cents,
            settings=MenuSettings(optimizer_version=OPTIMIZER_VERSION),
            optimization=result,
        )

        assert menu.status == result.status
        assert menu.ticket_cents <= result.solver_ticket_cents <= menu.budget_cents
        assert len(menu.entries) == 4
        assert sum(item.subtotal_cents for item in menu.shopping_items) == menu.ticket_cents
        assert menu.ticket_cents + menu.pantry_consumption_cents == (
            menu.consumption_cents + menu.leftover_value_cents
        )
        service.verify_identities(menu.id)

        dishes = [entry.dish for entry in menu.entries]
        formats = _formats_by_ingredient(catalog)
        basket = price_basket(dishes, request.people, {}, formats)
        assert basket.ticket_cents == menu.ticket_cents

        original_ticket = menu.ticket_cents
        revalidated = service.revalidate(menu.id)
        assert revalidated.ticket_cents == original_ticket
        service.verify_identities(menu.id)

        session.expire_all()
        reloaded = session.get(Menu, menu.id)
        assert reloaded is not None
        assert reloaded.ticket_cents == original_ticket


def test_service_never_buys_unknown_allergen_product(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=1, budget_cents=1_000_000)
        make_sync_run(session)
        catalog = build_balanced_catalog(
            session,
            days=1,
            preferences=ALLERGEN_CATALOG,
            unknown_chicken=True,
        )
        assert catalog.unknown_product_id is not None
        request = OptimizationRequest(
            people=2,
            days=1,
            budget_cents=1_000_000,
            preferences=ALLERGEN_CATALOG,
            stage1_seconds=1.0,
            stage2_seconds=1.0,
            fallback_seconds=0.5,
        )
        result = optimize_menu(catalog.eligibility, request)
        menu = MenuService(session).generate(
            profile_id=1,
            people=2,
            days=1,
            budget_cents=request.budget_cents,
            settings=MenuSettings(allergen_codes=["gluten"]),
            optimization=result,
        )

        assert catalog.unknown_product_id not in {item.product_id for item in menu.shopping_items}
        assert catalog.unknown_product_id not in result.packages


def test_optimizer_exclusions_are_never_persisted(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=1, budget_cents=1_000_000)
        catalog = build_balanced_catalog(session, days=1)
        excluded = catalog.dishes_with_slot("lunch")[0]
        preferences = PreferenceSnapshot(excluded_dish_ids=frozenset({excluded.id}))
        eligibility = evaluate_dishes(session, preferences)
        result = optimize_menu(
            eligibility,
            _request(days=1, preferences=preferences),
        )

        assert excluded.id not in {assignment.dish_id for assignment in result.assignments}
        assert all(
            assignment.dish_id in result.eligibility.eligible_dish_ids
            for assignment in result.assignments
        )


def test_infeasible_preview_is_not_persisted(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        make_profile(session, people=2, days=1, budget_cents=1)
        catalog = build_balanced_catalog(session, days=1)
        result = optimize_menu(catalog.eligibility, _request(days=1, budget_cents=1))

        assert result.status == "infeasible"
        assert result.is_preview is True
        with pytest.raises(MenuServiceError) as error:
            MenuService(session).generate(
                profile_id=1,
                people=2,
                days=1,
                budget_cents=1,
                settings=MenuSettings(),
                optimization=result,
            )
        assert error.value.code == "INVALID_OPTIMIZATION"
        assert session.scalar(select(func.count()).select_from(Menu)) == 0
