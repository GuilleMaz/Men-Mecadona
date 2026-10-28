"""Catálogos sintéticos deterministas para los tests del optimizador (F4.2-F4.4).

Todos los datos son locales: no se llama a Mercadona ni se usa el catálogo real.
Los platos incluyen siempre verdura, proteína e hidrato para que los mínimos
diarios se puedan cumplir con una sola comida y una sola cena.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.dishes import Dish
from app.models.ingredients import Ingredient
from app.services.eligibility import DishEligibility, PreferenceSnapshot, evaluate_dishes
from tests.domain_fixtures import make_dish, make_ingredient, make_mapping, make_product

_VEGETABLES: tuple[tuple[str, str, int], ...] = (
    ("carrot", "Zanahoria", 120),
    ("zucchini", "Calabacín", 140),
    ("spinach", "Espinaca", 180),
    ("tomato", "Tomate", 130),
)

_PROTEINS: tuple[tuple[str, str, int, int], ...] = (
    # slug, source, serving_size_milli, price_cents
    ("chicken", "chicken", 100_000, 350),
    ("fish", "fish", 100_000, 500),
    ("legumes", "legumes", 80_000, 120),
    ("beef", "beef", 100_000, 600),
    ("eggs", "eggs", 100_000, 200),
)

_CARBS: tuple[tuple[str, str, int], ...] = (
    ("rice", "rice", 130),
    ("pasta", "pasta", 140),
    ("potato", "potato", 120),
    ("bread", "bread", 150),
)

_LUNCH_SOURCES: tuple[str, ...] = (
    "chicken",
    "beef",
    "fish",
    "legumes",
    "eggs",
    "chicken",
    "fish",
    "legumes",
    "beef",
    "eggs",
    "chicken",
    "fish",
    "legumes",
    "beef",
    "eggs",
    "chicken",
)

_DINNER_SOURCES: tuple[str, ...] = (
    "fish",
    "legumes",
    "chicken",
    "beef",
    "eggs",
    "fish",
    "legumes",
    "chicken",
    "beef",
    "eggs",
    "fish",
    "legumes",
    "chicken",
    "eggs",
    "fish",
    "beef",
)


@dataclass(frozen=True, slots=True)
class OptimizerCatalog:
    """Platos, ingredientes y elegibilidad ya evaluada."""

    dishes: tuple[Dish, ...]
    ingredients: tuple[Ingredient, ...]
    eligibility: tuple[DishEligibility, ...]
    ingredients_by_slug: dict[str, Ingredient]
    unknown_product_id: int | None = None

    def dishes_with_slot(self, slot: str) -> tuple[Dish, ...]:
        return tuple(dish for dish in self.dishes if slot in dish.meal_types_json)


def _make_ingredient(
    session: Session,
    slug: str,
    *,
    name: str,
    category: str,
    group: str,
    serving_group: str,
    serving_size_milli: int,
    price_cents: int,
    protein_source: str | None = None,
    extra_unknown_product: bool = False,
) -> tuple[Ingredient, int | None]:
    ingredient = make_ingredient(
        session,
        slug,
        name=name,
        category=category,
        group=group,
        serving_group=serving_group,
        serving_size_milli=serving_size_milli,
        protein_source=protein_source,
    )
    product = make_product(
        session,
        f"p-{slug}",
        name=f"{name} (formato)",
        package_quantity_milli=1_000_000,
        package_unit=ingredient.base_unit,
        package_price_cents=price_cents,
        allergen_status="known",
    )
    make_mapping(session, ingredient, product, priority=1, is_default=True)
    if not extra_unknown_product:
        return ingredient, None

    unknown = make_product(
        session,
        f"p-{slug}-unknown",
        name=f"{name} (etiqueta desconocida)",
        package_quantity_milli=1_000_000,
        package_unit=ingredient.base_unit,
        package_price_cents=10,
        allergen_status="unknown",
    )
    make_mapping(session, ingredient, unknown, priority=2, is_default=False)
    return ingredient, unknown.id


def build_balanced_catalog(
    session: Session,
    *,
    days: int,
    preferences: PreferenceSnapshot | None = None,
    unknown_chicken: bool = False,
) -> OptimizerCatalog:
    """Catálogo con suficientes platos y variedad para ``days`` días."""
    ingredients: dict[str, Ingredient] = {}
    unknown_product_id: int | None = None

    for slug, name, price in _VEGETABLES:
        ingredient, _ = _make_ingredient(
            session,
            slug,
            name=name,
            category="vegetables",
            group="vegetable",
            serving_group="vegetable",
            serving_size_milli=150_000,
            price_cents=price,
        )
        ingredients[slug] = ingredient

    for slug, source, serving_size, price in _PROTEINS:
        ingredient, unknown = _make_ingredient(
            session,
            slug,
            name=slug.capitalize(),
            category="protein",
            group="protein",
            serving_group="protein",
            serving_size_milli=serving_size,
            price_cents=price,
            protein_source=source,
            extra_unknown_product=unknown_chicken and slug == "chicken",
        )
        if unknown is not None:
            unknown_product_id = unknown
        ingredients[slug] = ingredient

    for slug, _, price in _CARBS:
        ingredient, _ = _make_ingredient(
            session,
            slug,
            name=slug.capitalize(),
            category="carbs",
            group="carb",
            serving_group="carb",
            serving_size_milli=60_000,
            price_cents=price,
        )
        ingredients[slug] = ingredient

    lunch_count = max(days + 2, 4)
    dinner_count = max(days + 2, 4)
    dishes: list[Dish] = []
    for index, source in enumerate(_LUNCH_SOURCES[:lunch_count]):
        dishes.append(
            _make_meal(
                session,
                index,
                slot="lunch",
                source=source,
                ingredients=ingredients,
                light=False,
            )
        )
    for index, source in enumerate(_DINNER_SOURCES[:dinner_count]):
        dishes.append(
            _make_meal(
                session,
                index,
                slot="dinner",
                source=source,
                ingredients=ingredients,
                light=source != "beef",
            )
        )

    snapshot = preferences or PreferenceSnapshot()
    return OptimizerCatalog(
        dishes=tuple(dishes),
        ingredients=tuple(ingredients.values()),
        eligibility=tuple(evaluate_dishes(session, snapshot)),
        ingredients_by_slug=dict(ingredients),
        unknown_product_id=unknown_product_id,
    )


def _make_meal(
    session: Session,
    index: int,
    *,
    slot: str,
    source: str,
    ingredients: dict[str, Ingredient],
    light: bool,
) -> Dish:
    vegetable = ingredients[_VEGETABLES[index % len(_VEGETABLES)][0]]
    protein = ingredients[source]
    carb = ingredients[_CARBS[(index * 3 + (0 if slot == "lunch" else 1)) % len(_CARBS)][0]]
    base_servings = (1, 2, 4, 2)[index % 4]
    tags: list[str] = []
    if source == "fish":
        tags.append("fish")
    if source == "legumes":
        tags.append("legume")
    if source in {"beef", "pork"}:
        tags.append("red_meat")
    return make_dish(
        session,
        f"{slot}-{source}-{index}",
        name=f"{slot.capitalize()} {source} {index + 1}",
        base_servings=base_servings,
        meal_types=[slot],
        protein_sources=[source],
        light=light,
        carbs=carb.slug,
        tags=tags,
        ingredients=[
            (vegetable, 150_000 * base_servings),
            (protein, protein.serving_size_milli * base_servings),
            (carb, 60_000 * base_servings),
        ],
    )
