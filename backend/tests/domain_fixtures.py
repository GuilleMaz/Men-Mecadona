"""Constructores sintéticos para los tests de ingredientes, platos y preferencias."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.catalog import Category, Product
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.models.profile import Profile
from app.models.types import utcnow


def ensure_category(session: Session, category_id: int = 1, name: str = "Despensa") -> Category:
    category = session.get(Category, category_id)
    if category is None:
        category = Category(id=category_id, name=name, level=0, is_food=True, sort_order=1)
        session.add(category)
        session.flush()
    return category


def make_product(
    session: Session,
    external_id: str,
    *,
    name: str | None = None,
    package_quantity_milli: int | None = 1_000_000,
    package_unit: str = "g",
    package_price_cents: int = 100,
    allergen_status: str = "known",
    published: bool = True,
    approx_size: bool = False,
    selling_method: int = 0,
    category_id: int = 1,
) -> Product:
    ensure_category(session, category_id)
    now = utcnow()
    product = Product(
        external_id=external_id,
        name=name or f"Producto {external_id}",
        category_id=category_id,
        package_quantity_milli=package_quantity_milli,
        package_unit=package_unit if package_quantity_milli is not None else None,
        package_price_cents=package_price_cents,
        allergen_status=allergen_status,
        published=published,
        approx_size=approx_size,
        selling_method=selling_method,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(product)
    session.flush()
    return product


def make_ingredient(
    session: Session,
    slug: str,
    *,
    name: str | None = None,
    category: str = "vegetables",
    group: str = "vegetable",
    base_unit: str = "g",
    serving_group: str = "vegetable",
    serving_size_milli: int = 150_000,
    protein_source: str | None = None,
    allergens: Iterable[str] = (),
    tags: Iterable[str] = (),
    active: bool = True,
) -> Ingredient:
    ingredient = Ingredient(
        slug=slug,
        name=name or slug.replace("-", " ").capitalize(),
        category=category,
        group=group,
        base_unit=base_unit,
        serving_group=serving_group,
        serving_size_milli=serving_size_milli,
        protein_source=protein_source,
        allergens_json=list(allergens),
        tags_json=list(tags),
        active=active,
    )
    session.add(ingredient)
    session.flush()
    return ingredient


def make_mapping(
    session: Session,
    ingredient: Ingredient,
    product: Product,
    *,
    priority: int = 1,
    is_default: bool = True,
) -> IngredientProduct:
    mapping = IngredientProduct(
        ingredient_id=ingredient.id,
        product_id=product.id,
        priority=priority,
        is_default=is_default,
    )
    session.add(mapping)
    session.flush()
    return mapping


def make_dish(
    session: Session,
    slug: str,
    *,
    name: str | None = None,
    base_servings: int = 2,
    meal_types: Iterable[str] = ("lunch",),
    protein_sources: Iterable[str] = (),
    has_vegetables: bool = True,
    light: bool = False,
    carbs: str | None = "rice",
    tags: Iterable[str] = (),
    ingredients: Iterable[tuple[Ingredient, int]] = (),
    active: bool = True,
) -> Dish:
    dish = Dish(
        slug=slug,
        name=name or slug.replace("-", " ").capitalize(),
        description="Plato sintético",
        base_servings=base_servings,
        meal_types_json=list(meal_types),
        protein_sources_json=list(protein_sources),
        has_vegetables=has_vegetables,
        light=light,
        carbs=carbs,
        tags_json=list(tags),
        active=active,
        seed_version="test",
    )
    session.add(dish)
    session.flush()
    for ingredient, quantity_milli in ingredients:
        session.add(
            DishIngredient(
                dish_id=dish.id,
                ingredient_id=ingredient.id,
                quantity_milli=quantity_milli,
            )
        )
    session.flush()
    return dish


def make_profile(
    session: Session,
    *,
    people: int = 2,
    days: int = 7,
    budget_cents: int = 7000,
    allergen_codes: Iterable[str] = (),
) -> Profile:
    profile = session.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1)
        session.add(profile)
    profile.people = people
    profile.days = days
    profile.budget_cents = budget_cents
    profile.allergen_codes_json = list(allergen_codes)
    session.flush()
    return profile
