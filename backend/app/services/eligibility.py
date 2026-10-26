"""Elegibilidad de ingredientes y platos (F2.4 y base de F4.2).

La política de alérgenos es fail-closed y se aplica en dos niveles:

- El ingrediente aporta sus alérgenos intrínsecos.
- El producto solo es elegible si es `known` y no contiene un alérgeno declarado.

Si el usuario no declara alérgenos, los productos `partial`/`unknown` sí pueden
usarse. Si declara alguno, se excluyen. Un ingrediente sin productos elegibles
bloquea todos los platos que lo contienen.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Product
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.models.profile import Exclusion, Profile


@dataclass(frozen=True, slots=True)
class IngredientEligibility:
    """Productos elegibles de un ingrediente para los alérgenos declarados."""

    ingredient: Ingredient
    eligible_products: tuple[IngredientProduct, ...]
    allergens: frozenset[str]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DishEligibility:
    """Resultado de aplicar preferencias y alérgenos a un plato."""

    dish: Dish
    eligible: bool
    reasons: tuple[str, ...] = ()
    blocked_ingredient_ids: tuple[int, ...] = ()
    allergens: frozenset[str] = frozenset()
    ingredients: tuple[IngredientEligibility, ...] = ()


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    """Preferencias normalizadas que participan en la elegibilidad."""

    allergen_codes: frozenset[str] = frozenset()
    excluded_ingredient_ids: frozenset[int] = frozenset()
    excluded_dish_ids: frozenset[int] = frozenset()
    excluded_tags: frozenset[str] = frozenset()


def preferences_from_profile(session: Session, profile: Profile) -> PreferenceSnapshot:
    """Carga las exclusiones del perfil en una instantánea inmutable."""
    exclusions = session.scalars(select(Exclusion).where(Exclusion.profile_id == profile.id)).all()
    return PreferenceSnapshot(
        allergen_codes=frozenset(profile.allergen_codes_json or []),
        excluded_ingredient_ids=frozenset(
            exclusion.ingredient_id
            for exclusion in exclusions
            if exclusion.ingredient_id is not None
        ),
        excluded_dish_ids=frozenset(
            exclusion.dish_id for exclusion in exclusions if exclusion.dish_id is not None
        ),
        excluded_tags=frozenset(
            exclusion.tag for exclusion in exclusions if exclusion.tag is not None
        ),
    )


def _product_allergens(product: Product) -> set[str]:
    return {allergen.allergen_code for allergen in product.allergens}


def ingredient_eligibility(
    ingredient: Ingredient, declared_allergens: frozenset[str]
) -> IngredientEligibility:
    """Aplica la política fail-closed a los productos del ingrediente."""
    intrinsic = frozenset(ingredient.allergens_json or [])
    if declared_allergens and intrinsic & declared_allergens:
        return IngredientEligibility(
            ingredient=ingredient,
            eligible_products=(),
            allergens=intrinsic,
            reason="ingredient_allergen",
        )

    eligible: list[IngredientProduct] = []
    allergen_codes: set[str] = set(intrinsic)
    for mapping in ingredient.products:
        product = mapping.product
        product_codes = _product_allergens(product)
        allergen_codes.update(product_codes)
        if not product.published:
            continue
        if (
            product.package_quantity_milli is None
            or product.package_quantity_milli <= 0
            or product.package_price_cents is None
            or product.package_price_cents <= 0
            or product.approx_size
            or (product.selling_method or 0) != 0
        ):
            continue
        if declared_allergens:
            if product.allergen_status != "known":
                continue
            if product_codes & declared_allergens:
                continue
        eligible.append(mapping)

    reason = None
    if not eligible:
        reason = "no_eligible_product"
    return IngredientEligibility(
        ingredient=ingredient,
        eligible_products=tuple(eligible),
        allergens=frozenset(allergen_codes),
        reason=reason,
    )


def evaluate_dish(dish: Dish, preferences: PreferenceSnapshot) -> DishEligibility:
    """Aplica exclusiones, alérgenos y disponibilidad a un plato cargado."""
    reasons: list[str] = []
    if dish.id in preferences.excluded_dish_ids:
        reasons.append("dish_excluded")
    if set(dish.tags_json or []) & preferences.excluded_tags:
        reasons.append("tag_excluded")

    blocked: list[int] = []
    allergens: set[str] = set()
    ingredient_results: list[IngredientEligibility] = []
    for link in dish.ingredients:
        ingredient = link.ingredient
        if ingredient.id in preferences.excluded_ingredient_ids:
            reasons.append("ingredient_excluded")
            blocked.append(ingredient.id)
            continue
        result = ingredient_eligibility(ingredient, preferences.allergen_codes)
        ingredient_results.append(result)
        allergens.update(result.allergens)
        if result.reason is not None:
            reasons.append(result.reason)
            blocked.append(ingredient.id)

    return DishEligibility(
        dish=dish,
        eligible=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        blocked_ingredient_ids=tuple(dict.fromkeys(blocked)),
        allergens=frozenset(allergens),
        ingredients=tuple(ingredient_results),
    )


def load_dishes(session: Session, *, dish_id: int | None = None) -> list[Dish]:
    """Carga platos activos con ingredientes, productos y alérgenos."""
    statement = (
        select(Dish)
        .where(Dish.active.is_(True))
        .options(
            selectinload(Dish.ingredients)
            .selectinload(DishIngredient.ingredient)
            .selectinload(Ingredient.products)
            .selectinload(IngredientProduct.product)
            .selectinload(Product.allergens)
        )
    )
    if dish_id is not None:
        statement = statement.where(Dish.id == dish_id)
    return list(session.scalars(statement.order_by(Dish.name, Dish.id)).all())


def evaluate_dishes(
    session: Session, preferences: PreferenceSnapshot, *, dish_id: int | None = None
) -> list[DishEligibility]:
    """Evalúa todos los platos activos (o solo uno) con las preferencias dadas."""
    return [evaluate_dish(dish, preferences) for dish in load_dishes(session, dish_id=dish_id)]
