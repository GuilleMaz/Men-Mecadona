"""Motor de costes puro (F3.1-F3.4 y F3.7).

Los casos usan productos y platos sintéticos: no se llama a Mercadona ni se
depende del catálogo real. Todos los importes son céntimos enteros.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.dishes import Dish
from app.models.ingredients import Ingredient
from app.services.pricing import (
    PricingError,
    plan_purchase,
    price_basket,
    price_ingredient,
    purchasable_formats,
    scale_dish,
    scale_quantity,
)
from tests.domain_fixtures import make_dish, make_ingredient, make_mapping, make_product


def _ingredient(
    session: Session,
    slug: str,
    *,
    base_unit: str = "g",
    group: str = "pantry",
) -> Ingredient:
    return make_ingredient(
        session,
        slug,
        base_unit=base_unit,
        group=group,
        serving_group="none",
    )


def _format(
    session: Session,
    ingredient: Ingredient,
    external_id: str,
    *,
    quantity_milli: int | None,
    price_cents: int | None,
    unit: str | None = None,
    priority: int = 1,
    is_default: bool = False,
    published: bool = True,
    approx_size: bool = False,
    selling_method: int = 0,
) -> None:
    product = make_product(
        session,
        external_id,
        package_quantity_milli=quantity_milli,
        package_unit=unit or ingredient.base_unit,
        package_price_cents=price_cents,
        published=published,
        approx_size=approx_size,
        selling_method=selling_method,
    )
    make_mapping(
        session,
        ingredient,
        product,
        priority=priority,
        is_default=is_default,
    )


def _dish(session: Session, slug: str, links: Sequence[tuple[Ingredient, int]]) -> Dish:
    return make_dish(
        session,
        slug,
        base_servings=2,
        ingredients=[(ingredient, quantity) for ingredient, quantity in links],
    )


def test_scale_quantity_golden_cases() -> None:
    # Huevos: 2 unidades por ración base, 4 personas.
    assert scale_quantity(2_000, 4, 2) == 4_000
    # Cebolla: 100 g para 2 raciones, 1 persona.
    assert scale_quantity(100_000, 1, 2) == 50_000
    # Pollo: 300 g para 2 raciones, 2 personas.
    assert scale_quantity(300_000, 2, 2) == 300_000
    # Aceite: 15 ml para 2 raciones, 4 personas.
    assert scale_quantity(15_000, 4, 2) == 30_000
    # Una cantidad pequeña puede redondear a cero.
    assert scale_quantity(1_000, 1, 20) == 50


def test_scale_quantity_rejects_invalid_input() -> None:
    with pytest.raises(PricingError) as error:
        scale_quantity(1_000, 0, 2)
    assert error.value.code == "INVALID_INPUT"

    with pytest.raises(PricingError) as error:
        scale_quantity(1_000, 2, 0)
    assert error.value.code == "INVALID_INPUT"

    with pytest.raises(PricingError) as error:
        scale_quantity(-1, 2, 2)
    assert error.value.code == "INVALID_INPUT"


def test_purchasable_formats_requires_matching_unit(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "rice")
        _format(
            session,
            ingredient,
            "MISMATCH",
            quantity_milli=1_000_000,
            price_cents=100,
            unit="ml",
            is_default=True,
        )
        assert purchasable_formats(ingredient) == ()
        with pytest.raises(PricingError) as error:
            plan_purchase(ingredient, 1_000)
        assert error.value.code == "PRODUCT_UNAVAILABLE"
        assert error.value.details["ingredient_id"] == ingredient.id


def test_purchasable_formats_filters_unpublished_and_variable_weight(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "chicken")
        _format(
            session,
            ingredient,
            "UNPUBLISHED",
            quantity_milli=500_000,
            price_cents=100,
            priority=1,
            is_default=True,
            published=False,
        )
        _format(
            session,
            ingredient,
            "VARIABLE",
            quantity_milli=500_000,
            price_cents=100,
            priority=2,
            approx_size=True,
        )
        _format(
            session,
            ingredient,
            "COUNTER",
            quantity_milli=500_000,
            price_cents=100,
            priority=3,
            selling_method=1,
        )
        _format(
            session,
            ingredient,
            "NO_PRICE",
            quantity_milli=500_000,
            price_cents=None,
            priority=4,
        )
        assert purchasable_formats(ingredient) == ()

        _format(
            session,
            ingredient,
            "VALID",
            quantity_milli=500_000,
            price_cents=450,
            priority=5,
        )
        session.expire(ingredient, ["products"])
        assert [fmt.external_id for fmt in purchasable_formats(ingredient)] == ["VALID"]


def test_plan_purchase_single_format_rounds_up(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "chicken")
        _format(
            session,
            ingredient,
            "CHICKEN-500",
            quantity_milli=500_000,
            price_cents=450,
            is_default=True,
        )
        plan = plan_purchase(ingredient, 1_001_000)
        assert plan.purchased_milli == 1_500_000
        assert plan.ticket_cents == 1_350
        assert len(plan.lines) == 1
        assert plan.lines[0].packages == 3
        assert plan.lines[0].leftover_milli == 1_500_000


def test_plan_purchase_mixes_formats_at_minimum_cost(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "olive-oil", base_unit="ml", group="fat")
        _format(
            session,
            ingredient,
            "OIL-1L",
            quantity_milli=1_000_000,
            price_cents=200,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "OIL-5L",
            quantity_milli=5_000_000,
            price_cents=800,
            priority=2,
        )

        six_litres = plan_purchase(ingredient, 6_000_000)
        assert six_litres.ticket_cents == 1_000
        assert sum(line.packages for line in six_litres.lines) == 2
        assert [(line.product.external_id, line.packages) for line in six_litres.lines] == [
            ("OIL-5L", 1),
            ("OIL-1L", 1),
        ]

        # Para 2 L sale más barato comprar dos botellas pequeñas que una grande.
        two_litres = plan_purchase(ingredient, 2_000_000)
        assert two_litres.ticket_cents == 400
        assert [(line.product.external_id, line.packages) for line in two_litres.lines] == [
            ("OIL-1L", 2),
        ]


def test_plan_purchase_tie_breaks_fewer_packages(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "rice")
        _format(
            session,
            ingredient,
            "RICE-500",
            quantity_milli=500_000,
            price_cents=100,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "RICE-1KG",
            quantity_milli=1_000_000,
            price_cents=200,
            priority=2,
        )
        plan = plan_purchase(ingredient, 1_000_000)
        assert plan.ticket_cents == 200
        assert len(plan.lines) == 1
        assert plan.lines[0].product.external_id == "RICE-1KG"


def test_plan_purchase_tie_breaks_product_id(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "milk", base_unit="ml", group="dairy")
        _format(
            session,
            ingredient,
            "MILK-FIRST",
            quantity_milli=1_000_000,
            price_cents=95,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "MILK-SECOND",
            quantity_milli=1_000_000,
            price_cents=95,
            priority=2,
        )
        plan = plan_purchase(ingredient, 1_000_000)
        assert len(plan.lines) == 1
        assert plan.lines[0].product.external_id == "MILK-FIRST"
        assert plan.ticket_cents == 95


def test_plan_purchase_exact_cover_leaves_no_leftover(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "onion")
        _format(
            session,
            ingredient,
            "ONION-500",
            quantity_milli=500_000,
            price_cents=120,
            is_default=True,
        )
        plan = plan_purchase(ingredient, 1_000_000)
        assert plan.purchased_milli == 1_000_000
        assert plan.ticket_cents == 240
        cost = price_ingredient(ingredient, need_milli=1_000_000)
        assert cost.leftover_milli == 0
        assert cost.lines[0].leftover_milli == 0


def test_plan_purchase_zero_need_returns_empty_plan(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "garlic")
        plan = plan_purchase(ingredient, 0)
        assert plan.lines == ()
        assert plan.ticket_cents == 0
        assert plan.purchased_milli == 0


def test_plan_purchase_falls_back_to_dynamic_programming(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    """Formatos con cocientes enormes usan el respaldo exacto, no la enumeración."""
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "weird-pack")
        _format(
            session,
            ingredient,
            "C",
            quantity_milli=991_000,
            price_cents=98,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "A",
            quantity_milli=1_009_000,
            price_cents=100,
            priority=2,
        )
        _format(
            session,
            ingredient,
            "B",
            quantity_milli=997_000,
            price_cents=99,
            priority=3,
        )
        plan = plan_purchase(ingredient, 1_900_000)
        assert plan.ticket_cents == 196
        assert sum(line.packages for line in plan.lines) == 2
        assert [(line.product.external_id, line.packages) for line in plan.lines] == [("C", 2)]


def test_price_ingredient_with_partial_pantry(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "chicken")
        _format(
            session,
            ingredient,
            "CHICKEN-500",
            quantity_milli=500_000,
            price_cents=200,
            is_default=True,
        )
        cost = price_ingredient(ingredient, need_milli=1_000_000, pantry_milli=400_000)
        assert cost.net_need_milli == 600_000
        assert cost.ticket_cents == 400
        assert cost.purchased_milli == 1_000_000
        assert cost.leftover_milli == 400_000
        assert cost.pantry_consumption_cents == 160
        assert cost.consumption_cents == 400
        assert cost.leftover_value_cents == 160
        assert cost.ticket_cents + cost.pantry_consumption_cents == (
            cost.consumption_cents + cost.leftover_value_cents
        )


def test_price_ingredient_with_full_and_over_pantry(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "rice")
        _format(
            session,
            ingredient,
            "RICE-500",
            quantity_milli=500_000,
            price_cents=200,
            is_default=True,
        )
        for pantry_milli in (1_000_000, 1_500_000):
            cost = price_ingredient(
                ingredient,
                need_milli=1_000_000,
                pantry_milli=pantry_milli,
            )
            assert cost.pantry_used_milli == 1_000_000
            assert cost.net_need_milli == 0
            assert cost.ticket_cents == 0
            assert cost.purchased_milli == 0
            assert cost.leftover_milli == 0
            assert cost.pantry_consumption_cents == 400
            assert cost.consumption_cents == 400
            assert cost.leftover_value_cents == 0
            assert cost.ticket_cents + cost.pantry_consumption_cents == (
                cost.consumption_cents + cost.leftover_value_cents
            )


def test_pantry_is_valued_at_the_cheapest_eligible_format(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    """La despensa usa el coste unitario del formato elegible más barato."""
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "olive-oil", base_unit="ml", group="fat")
        _format(
            session,
            ingredient,
            "OIL-1L",
            quantity_milli=1_000_000,
            price_cents=300,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "OIL-5L",
            quantity_milli=5_000_000,
            price_cents=1_000,
            priority=2,
        )
        # La compra elige la botella de 1 L, pero la despensa se valora al
        # coste unitario del formato de 5 L, que es el más barato por ml.
        cost = price_ingredient(
            ingredient,
            need_milli=2_000_000,
            pantry_milli=1_000_000,
        )
        assert cost.ticket_cents == 300
        assert cost.pantry_consumption_cents == 200
        assert cost.consumption_cents == 500
        assert cost.leftover_value_cents == 0
        assert cost.ticket_cents + cost.pantry_consumption_cents == (
            cost.consumption_cents + cost.leftover_value_cents
        )


def test_price_ingredient_assigns_consumption_to_cheapest_format(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "olive-oil", base_unit="ml", group="fat")
        _format(
            session,
            ingredient,
            "OIL-1L",
            quantity_milli=1_000_000,
            price_cents=300,
            priority=1,
            is_default=True,
        )
        _format(
            session,
            ingredient,
            "OIL-5L",
            quantity_milli=5_000_000,
            price_cents=1_000,
            priority=2,
        )
        cost = price_ingredient(ingredient, need_milli=5_500_000)
        assert cost.ticket_cents == 1_300
        assert cost.purchased_milli == 6_000_000
        assert cost.leftover_milli == 500_000
        assert cost.consumption_cents == 1_150
        assert cost.leftover_value_cents == 150
        assert [line.used_milli for line in cost.lines] == [5_000_000, 500_000]


def test_price_pack_of_six_by_125g(catalog_session_factory: sessionmaker[Session]) -> None:
    """Un pack 6 × 125 g es un único formato de 750 g."""
    with catalog_session_factory() as session:
        ingredient = _ingredient(session, "yogurt", base_unit="g", group="dairy")
        _format(
            session,
            ingredient,
            "YOGURT-6X125",
            quantity_milli=750_000,
            price_cents=300,
            is_default=True,
        )
        cost = price_ingredient(ingredient, need_milli=250_000)
        assert cost.ticket_cents == 300
        assert cost.purchased_milli == 750_000
        assert cost.consumption_cents == 100
        assert cost.leftover_milli == 500_000
        assert cost.leftover_value_cents == 200
        assert cost.ticket_cents + cost.pantry_consumption_cents == (
            cost.consumption_cents + cost.leftover_value_cents
        )


def test_price_one_person_versus_four_people(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        chicken = _ingredient(session, "chicken", group="protein")
        _format(
            session,
            chicken,
            "CHICKEN-500",
            quantity_milli=500_000,
            price_cents=450,
            is_default=True,
        )
        dish = _dish(session, "chicken", [(chicken, 300_000)])

        one_person = price_basket([dish], people=1)
        four_people = price_basket([dish], people=4)

        assert one_person.ingredients[0].need_milli == 150_000
        assert one_person.ticket_cents == 450
        assert one_person.dishes[0].per_serving_cents == 135
        assert four_people.ingredients[0].need_milli == 600_000
        assert four_people.ticket_cents == 900
        assert four_people.dishes[0].per_serving_cents == 135
        assert four_people.consumption_cents == one_person.consumption_cents * 4


def test_price_basket_accounting_identity_and_entry_allocation(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        chicken = _ingredient(session, "chicken", group="protein")
        rice = _ingredient(session, "rice", group="carb")
        _format(
            session,
            chicken,
            "CHICKEN-500",
            quantity_milli=500_000,
            price_cents=450,
            is_default=True,
        )
        _format(
            session,
            rice,
            "RICE-1KG",
            quantity_milli=1_000_000,
            price_cents=115,
            is_default=True,
        )
        first = _dish(session, "chicken-rice", [(chicken, 300_000), (rice, 160_000)])
        second = _dish(session, "rice-chicken", [(chicken, 100_000), (rice, 60_000)])

        basket = price_basket([first, second], people=2)

        assert basket.ticket_cents == 565
        assert basket.consumption_cents == 385
        assert basket.pantry_consumption_cents == 0
        assert basket.leftover_value_cents == 180
        assert basket.ticket_cents + basket.pantry_consumption_cents == (
            basket.consumption_cents + basket.leftover_value_cents
        )
        assert sum(dish.consumption_cents for dish in basket.dishes) == 385
        assert [dish.consumption_cents for dish in basket.dishes] == [288, 97]
        assert sum(line.subtotal_cents for cost in basket.ingredients for line in cost.lines) == 565


def test_price_basket_shares_ingredient_with_different_base_servings(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        chicken = _ingredient(session, "chicken", group="protein")
        _format(
            session,
            chicken,
            "CHICKEN-500",
            quantity_milli=500_000,
            price_cents=450,
            is_default=True,
        )
        two_servings = make_dish(
            session,
            "two-servings",
            base_servings=2,
            ingredients=[(chicken, 300_000)],
        )
        four_servings = make_dish(
            session,
            "four-servings",
            base_servings=4,
            ingredients=[(chicken, 300_000)],
        )
        assert scale_dish(two_servings, people=2) == {chicken.id: 300_000}
        assert scale_dish(four_servings, people=2) == {chicken.id: 150_000}

        basket = price_basket([two_servings, four_servings], people=2)
        chicken_cost = basket.ingredients[0]
        assert chicken_cost.need_milli == 450_000
        assert chicken_cost.ticket_cents == 450


def test_price_basket_uses_pantry_before_buying(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        rice = _ingredient(session, "rice", group="carb")
        _format(
            session,
            rice,
            "RICE-1KG",
            quantity_milli=1_000_000,
            price_cents=115,
            is_default=True,
        )
        dish = _dish(session, "rice-only", [(rice, 600_000)])

        without_pantry = price_basket([dish], people=2)
        with_pantry = price_basket([dish], people=2, pantry={rice.id: 600_000})

        assert without_pantry.ticket_cents == 115
        assert with_pantry.ticket_cents == 0
        assert with_pantry.consumption_cents == without_pantry.consumption_cents
        assert with_pantry.pantry_consumption_cents == without_pantry.consumption_cents
        assert with_pantry.ticket_cents + with_pantry.pantry_consumption_cents == (
            with_pantry.consumption_cents + with_pantry.leftover_value_cents
        )
