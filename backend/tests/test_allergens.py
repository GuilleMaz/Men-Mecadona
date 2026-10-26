"""Alérgenos: parser, fail-closed, producto de respaldo y sincronización (F2.4)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.allergens import ALLERGEN_CODES
from app.models.catalog import Product, ProductAllergen
from app.schemas.mercadona import MercadonaNutritionInformation, MercadonaProductDetail
from app.services.allergen_sync import (
    ALLERGEN_KEYWORDS,
    AllergenSyncService,
    parse_allergen_info,
)
from app.services.eligibility import (
    PreferenceSnapshot,
    evaluate_dish,
    ingredient_eligibility,
)
from tests.domain_fixtures import (
    make_dish,
    make_ingredient,
    make_mapping,
    make_product,
    make_profile,
)


@pytest.mark.parametrize("code", sorted(ALLERGEN_KEYWORDS))
def test_all_canonical_allergens_are_detected(code: str) -> None:
    keyword = ALLERGEN_KEYWORDS[code][0]
    extraction = parse_allergen_info(
        f"Contiene <strong>{keyword}</strong>.", "Ingrediente sintético"
    )

    assert extraction.status == "known"
    assert code in {allergen.code for allergen in extraction.allergens}


def test_x99_without_data_is_unknown() -> None:
    extraction = parse_allergen_info(" <strong>x99</strong>.", "")

    assert extraction.status == "unknown"
    assert extraction.allergens == ()


def test_x99_with_clean_ingredients_is_known_without_allergens() -> None:
    extraction = parse_allergen_info(" <strong>x99</strong>.", "<p>Patata</p>")

    assert extraction.status == "known"
    assert extraction.allergens == ()


def test_x99_with_an_allergen_in_ingredients_is_partial() -> None:
    extraction = parse_allergen_info(
        " <strong>x99</strong>.", "Garbanzos, agua, sal y disulfito sódico."
    )

    assert extraction.status == "partial"
    assert [(item.code, item.source) for item in extraction.allergens] == [
        ("sulphites", "ingredients")
    ]


def test_declared_and_ingredient_allergens_are_merged() -> None:
    extraction = parse_allergen_info("Contiene <strong>leche</strong>.", "Leche, soja y sal.")

    assert extraction.status == "partial"
    assert {item.code for item in extraction.allergens} == {"milk", "soybeans"}


def test_may_contain_is_recorded() -> None:
    extraction = parse_allergen_info(
        "Puede contener <strong>mostaza</strong>.", "Ingrediente sintético."
    )

    assert extraction.status == "known"
    assert "mustard" in {item.code for item in extraction.allergens}


def test_allergen_list_is_canonical() -> None:
    assert ALLERGEN_CODES[-1] == "unknown"
    assert len(ALLERGEN_CODES) == 15


class FakeDetailClient:
    """Cliente de detalle sintético."""

    def __init__(self, details: dict[str, MercadonaProductDetail], failures: set[str]) -> None:
        self.details = details
        self.failures = failures
        self.closed = False

    async def get_product(self, product_id: str) -> MercadonaProductDetail:
        if product_id in self.failures:
            raise RuntimeError("detalle no disponible")
        return self.details[product_id]

    async def close(self) -> None:
        self.closed = True


def _mapped_products(factory: sessionmaker[Session]) -> list[int]:
    with factory() as session:
        from app.models.catalog import Product

        return list(session.scalars(__import__("sqlalchemy").select(Product.id)).all())


async def test_allergen_sync_updates_only_mapped_products(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = make_ingredient(session, "potato", group="carb", serving_group="carb")
        potato = make_product(session, "1001", name="Patata", package_unit="g")
        milk = make_product(session, "1002", name="Leche", package_unit="ml")
        unmapped = make_product(
            session, "1003", name="Producto sin mapear", allergen_status="unknown"
        )
        make_mapping(session, ingredient, potato)
        make_mapping(session, ingredient, milk, priority=2, is_default=False)
        session.commit()
        potato_id = potato.id
        milk_id = milk.id
        unmapped_id = unmapped.id

    details = {
        "1001": MercadonaProductDetail(
            id="1001",
            display_name="Patata",
            nutrition_information=MercadonaNutritionInformation(
                allergens=" <strong>x99</strong>.", ingredients="Patata"
            ),
        ),
        "1002": MercadonaProductDetail(
            id="1002",
            display_name="Leche",
            nutrition_information=MercadonaNutritionInformation(
                allergens="Contiene <strong>leche</strong>.", ingredients="Leche"
            ),
        ),
    }
    client = FakeDetailClient(details, failures=set())
    service = AllergenSyncService(catalog_session_factory, client_factory=lambda: client)

    result = await service.run()

    assert result.products_seen == 2
    assert result.updated == 2
    assert result.failed == []
    assert client.closed is True
    with catalog_session_factory() as session:
        assert session.get(Product, potato_id).allergen_status == "known"  # type: ignore[union-attr]
        assert session.get(Product, milk_id).allergen_status == "known"  # type: ignore[union-attr]
        assert session.get(Product, unmapped_id).allergen_status == "unknown"  # type: ignore[union-attr]
        rows = session.scalars(
            select(ProductAllergen).where(ProductAllergen.product_id == milk_id)
        ).all()
        assert {row.allergen_code for row in rows} == {"milk"}


async def test_allergen_sync_keeps_status_when_detail_fails(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = make_ingredient(session, "rice", group="carb", serving_group="carb")
        product = make_product(session, "2001", allergen_status="unknown")
        make_mapping(session, ingredient, product)
        session.commit()
        product_id = product.id

    client = FakeDetailClient({}, failures={"2001"})
    result = await AllergenSyncService(catalog_session_factory, client_factory=lambda: client).run()

    assert result.updated == 0
    assert len(result.failed) == 1
    with catalog_session_factory() as session:
        from app.models.catalog import Product

        assert session.get(Product, product_id).allergen_status == "unknown"  # type: ignore[union-attr]


def test_unknown_product_is_excluded_when_allergens_are_declared(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = make_ingredient(session, "tomato", allergens=["milk"])
        cheap_unknown = make_product(
            session, "3001", allergen_status="unknown", package_price_cents=10
        )
        safe = make_product(session, "3002", allergen_status="known", package_price_cents=200)
        make_mapping(session, ingredient, cheap_unknown)
        make_mapping(session, ingredient, safe, priority=2, is_default=False)
        session.commit()

        without_allergens = ingredient_eligibility(ingredient, frozenset())
        with_milk = ingredient_eligibility(ingredient, frozenset({"milk"}))

    assert {mapping.product.external_id for mapping in without_allergens.eligible_products} == {
        "3001",
        "3002",
    }
    assert {mapping.product.external_id for mapping in with_milk.eligible_products} == set()
    assert with_milk.reason == "ingredient_allergen"


def test_fallback_product_with_allergen_is_not_used(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        ingredient = make_ingredient(session, "bread-ingredient", allergens=["gluten"])
        unknown = make_product(session, "3101", allergen_status="unknown")
        with_milk = make_product(session, "3102", allergen_status="known")
        safe = make_product(session, "3103", allergen_status="known")
        session.add(
            ProductAllergen(
                product_id=with_milk.id,
                allergen_code="milk",
                source="test",
                confidence="high",
            )
        )
        make_mapping(session, ingredient, unknown)
        make_mapping(session, ingredient, with_milk, priority=2, is_default=False)
        make_mapping(session, ingredient, safe, priority=3, is_default=False)
        session.commit()

        declared = ingredient_eligibility(ingredient, frozenset({"milk"}))

    assert [mapping.product.external_id for mapping in declared.eligible_products] == ["3103"]


def test_dish_evaluation_reports_exclusions_and_blocked_ingredients(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    with catalog_session_factory() as session:
        rice = make_ingredient(session, "rice", group="carb", serving_group="carb")
        rice_product = make_product(session, "4001", allergen_status="known")
        make_mapping(session, rice, rice_product)
        dish = make_dish(
            session,
            "rice-dish",
            meal_types=["lunch", "dinner"],
            tags=["rice"],
            ingredients=[(rice, 60_000)],
        )
        make_profile(session, allergen_codes=["gluten"])
        session.commit()

        result = evaluate_dish(
            dish,
            PreferenceSnapshot(
                allergen_codes=frozenset({"gluten"}),
                excluded_dish_ids=frozenset({dish.id}),
                excluded_tags=frozenset({"rice"}),
            ),
        )

    assert result.eligible is False
    assert {"dish_excluded", "tag_excluded"}.issubset(result.reasons)
