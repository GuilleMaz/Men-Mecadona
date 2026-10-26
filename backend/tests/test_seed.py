"""Seed: validación, cobertura, carga idempotente, dry-run y borrado suave (F2.2-F2.7)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.models.profile import Exclusion, PantryItem, Profile
from app.schemas.seed import SeedDish, SeedDishIngredient, SeedIngredient, SeedProduct
from app.services.seed import (
    SeedDocuments,
    SeedIssue,
    SeedService,
    load_seed_documents,
    to_quantity_milli,
    validate_catalog_mappings,
    validate_seed,
)
from tests.domain_fixtures import make_product, make_profile


def _seed_ingredient(
    slug: str,
    *,
    products: list[SeedProduct] | None = None,
    allergens: list[str] | None = None,
) -> SeedIngredient:
    return SeedIngredient(
        slug=slug,
        name=slug.replace("-", " ").title(),
        category="vegetables",
        group="vegetable",
        base_unit="g",
        serving_group="vegetable",
        serving_size_milli=150_000,
        allergens=allergens or [],
        products=products or [SeedProduct(external_id=f"ext-{slug}", priority=1, is_default=True)],
    )


def _seed_dish(
    slug: str,
    ingredients: list[SeedDishIngredient],
    *,
    has_vegetables: bool = True,
    light: bool = False,
    carbs: str | None = "rice",
    tags: list[str] | None = None,
) -> SeedDish:
    return SeedDish(
        slug=slug,
        name=slug.replace("-", " ").title(),
        base_servings=2,
        meal_types=["lunch"],
        protein_sources=[],
        has_vegetables=has_vegetables,
        light=light,
        carbs=carbs,
        tags=tags or [],
        ingredients=ingredients,
    )


def _codes(issues: list[SeedIssue]) -> set[str]:
    return {issue.code for issue in issues if issue.level == "error"}


def test_quantity_conversion_rounds_half_up() -> None:
    assert to_quantity_milli(Decimal("1")) == 1000
    assert to_quantity_milli(Decimal("0.1")) == 100
    assert to_quantity_milli(Decimal("1.2345")) == 1235


def test_seed_documents_pass_structure_and_coverage() -> None:
    documents = load_seed_documents()

    assert len(documents.ingredients) == 110
    assert len(documents.dishes) == 60
    assert len(documents.version) == 16
    assert not validate_seed(documents.ingredients, documents.dishes)


def test_validation_detects_shared_product_bad_flags_and_units() -> None:
    first = _seed_ingredient("rice")
    second = _seed_ingredient(
        "tomato",
        products=[SeedProduct(external_id="ext-rice", priority=1, is_default=True)],
    )
    third = _seed_ingredient("onion")
    fourth = _seed_ingredient("salt")
    dish = _seed_dish(
        "rice-dish",
        [
            SeedDishIngredient(ingredient="rice", quantity=Decimal("60"), unit="ml"),
            SeedDishIngredient(ingredient="tomato", quantity=Decimal("150"), unit="g"),
            SeedDishIngredient(ingredient="onion", quantity=Decimal("150"), unit="g"),
            SeedDishIngredient(ingredient="salt", quantity=Decimal("2"), unit="g"),
        ],
        has_vegetables=False,
    )

    issues = validate_seed([first, second, third, fourth], [dish])
    codes = _codes(issues)

    assert "SHARED_PRODUCT" in codes
    assert "UNIT_MISMATCH" in codes
    assert "HAS_VEGETABLES_MISMATCH" in codes
    assert "DUPLICATE_DISH" not in codes


def test_validation_detects_unknown_ingredient() -> None:
    first = _seed_ingredient("rice")
    dish = _seed_dish(
        "rice-dish",
        [
            SeedDishIngredient(ingredient="rice", quantity=Decimal("60"), unit="g"),
            SeedDishIngredient(ingredient="missing", quantity=Decimal("10"), unit="g"),
            SeedDishIngredient(ingredient="missing-two", quantity=Decimal("10"), unit="g"),
            SeedDishIngredient(ingredient="missing-three", quantity=Decimal("10"), unit="g"),
        ],
    )

    issues = validate_seed([first], [dish])

    assert "UNKNOWN_INGREDIENT" in _codes(issues)


def test_catalog_validation_reports_missing_products(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    documents = load_seed_documents()
    with catalog_session_factory() as session:
        make_product(session, "69089", package_unit="g")
        session.commit()
        issues = validate_catalog_mappings(session, documents)

    errors = [issue for issue in issues if issue.level == "error"]
    assert any(issue.code == "MISSING_PRODUCT" for issue in errors)
    assert not any(issue.code == "MISSING_PRODUCT" and "69089" in issue.message for issue in errors)


def _populate_catalog(session: Session, documents: SeedDocuments) -> None:
    for ingredient in documents.ingredients:
        for mapping in ingredient.products:
            make_product(
                session,
                mapping.external_id,
                name=ingredient.name,
                package_quantity_milli=1_000_000,
                package_unit=ingredient.base_unit,
                package_price_cents=100,
                allergen_status="known",
            )


def test_seed_loader_is_idempotent_and_preserves_user_data(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    documents = load_seed_documents()
    with catalog_session_factory() as session:
        _populate_catalog(session, documents)
        session.commit()

    service = SeedService(catalog_session_factory)
    first = service.load()
    assert first.ingredients == 110
    assert first.dishes == 60
    assert first.products == len(
        [product for ingredient in documents.ingredients for product in ingredient.products]
    )
    assert first.missing_products == []
    assert first.skipped_products == []

    with catalog_session_factory() as session:
        mapping_ids = {mapping.id for mapping in session.scalars(select(IngredientProduct)).all()}
        dish_link_ids = {link.id for link in session.scalars(select(DishIngredient)).all()}
        onion = session.scalar(select(Ingredient).where(Ingredient.slug == "onion"))
        assert onion is not None
        make_profile(session, allergen_codes=["gluten"])
        session.add(PantryItem(profile_id=1, ingredient_id=onion.id, quantity_milli=250_000))
        rice_dish = session.scalar(select(Dish).where(Dish.slug == "chicken-rice-vegetables"))
        assert rice_dish is not None
        session.add(Exclusion(profile_id=1, dish_id=rice_dish.id))
        session.add(
            Ingredient(
                slug="ghost-ingredient",
                name="Fantasma",
                category="x",
                group="other",
                base_unit="g",
                serving_group="none",
                serving_size_milli=1000,
            )
        )
        session.add(
            Dish(
                slug="ghost-dish",
                name="Fantasma",
                base_servings=2,
                meal_types_json=["lunch"],
                protein_sources_json=[],
                has_vegetables=False,
                light=False,
                carbs=None,
                tags_json=[],
                active=True,
                seed_version="old",
            )
        )
        session.commit()

    second = service.load()
    assert second.products == first.products
    assert second.deactivated_ingredients == 1
    assert second.deactivated_dishes == 1

    with catalog_session_factory() as session:
        assert {
            mapping.id for mapping in session.scalars(select(IngredientProduct)).all()
        } == mapping_ids
        assert {link.id for link in session.scalars(select(DishIngredient)).all()} == dish_link_ids
        assert session.scalar(select(func.count()).select_from(Ingredient)) == 111
        ghost = session.scalar(select(Ingredient).where(Ingredient.slug == "ghost-ingredient"))
        assert ghost is not None and ghost.active is False
        assert session.get(Profile, 1) is not None
        assert session.scalar(select(func.count()).select_from(PantryItem)) == 1
        assert session.scalar(select(func.count()).select_from(Exclusion)) == 1


def test_seed_dry_run_does_not_persist(
    catalog_session_factory: sessionmaker[Session],
) -> None:
    service = SeedService(catalog_session_factory)

    result = service.load(dry_run=True)

    assert result.dry_run is True
    assert result.ingredients == 110
    with catalog_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Ingredient)) == 0
        assert session.scalar(select(func.count()).select_from(Dish)) == 0
