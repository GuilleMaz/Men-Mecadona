"""Carga idempotente y validación del seed de ingredientes y platos (F2).

El seed es la fuente de verdad de ingredientes, platos y mapeos. El cargador
hace upsert por `slug` y `external_id`, no borra datos de usuario y marca como
inactivos los elementos que desaparecen del YAML. La validación contra el
catálogo es deliberadamente estricta: un mapeo a un producto inexistente, sin
formato o con un producto compartido es un error.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models.catalog import Product
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.schemas.seed import SeedDish, SeedIngredient

RED_MEAT_SOURCES: frozenset[str] = frozenset({"beef", "pork", "lamb"})
ANIMAL_SOURCES: frozenset[str] = frozenset(
    {"chicken", "turkey", "beef", "pork", "lamb", "fish", "seafood"}
)
DERIVED_TAGS: frozenset[str] = frozenset(
    {"fish", "seafood", "legume", "red_meat", "vegetarian", "vegan"}
)
MIN_LUNCH_DISHES = 14
MIN_DINNER_DISHES = 14
MIN_TOTAL_DISHES = 28
MIN_PROTEIN_SOURCES = 3
MIN_PROTEIN_DISHES = 4
MIN_FISH_DISHES = 2
MIN_LEGUME_DISHES = 2
MIN_RED_MEAT_DISHES = 2
MIN_LIGHT_DINNERS = 4
MIN_COMPLEMENTS = 3
MAIN_MIN_PROTEIN_RATIONS = Decimal("0.5")
MAIN_MIN_VEGETABLE_CARB_RATIONS = Decimal("0.5")

IssueLevel = Literal["error", "warning"]


class SeedValidationError(ValueError):
    """El seed no cumple el contrato y no debe cargarse."""


@dataclass(frozen=True, slots=True)
class SeedIssue:
    """Incidencia de validación con código estable."""

    level: IssueLevel
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SeedDocuments:
    """YAML cargado, validado y con su versión reproducible."""

    ingredients: list[SeedIngredient]
    dishes: list[SeedDish]
    version: str


@dataclass(frozen=True, slots=True)
class DerivedDish:
    """Flags calculados desde la composición de un plato."""

    has_vegetables: bool
    light: bool
    carbs: str | None
    protein_sources: list[str]
    tags: frozenset[str]
    servings: dict[str, Decimal]
    role: str = "main"
    primary_protein: str | None = None


@dataclass(slots=True)
class SeedLoadResult:
    """Resumen de una carga o dry-run."""

    version: str
    dry_run: bool
    ingredients: int = 0
    products: int = 0
    dishes: int = 0
    missing_products: list[str] = field(default_factory=list)
    skipped_products: list[str] = field(default_factory=list)
    deactivated_ingredients: int = 0
    deactivated_dishes: int = 0
    issues: list[SeedIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)


def default_data_dir() -> Path:
    """Directorio de los YAML dentro de `backend/app/data`."""
    return Path(__file__).resolve().parents[1] / "data"


def to_quantity_milli(quantity: Decimal) -> int:
    """Convierte una cantidad humana a milésimas, redondeando half-up."""
    milli = (quantity * 1000).to_integral_value(rounding=ROUND_HALF_UP)
    value = int(milli)
    if value <= 0:
        raise SeedValidationError(f"La cantidad {quantity} no es positiva en milésimas.")
    return value


def _pydantic_error(path: Path, index: int, exc: ValidationError) -> SeedValidationError:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return SeedValidationError(f"{path.name}, elemento {index}: {details}")


def load_seed_documents(data_dir: Path | None = None) -> SeedDocuments:
    """Lee los dos YAML, valida su estructura estática y calcula su versión."""
    directory = data_dir or default_data_dir()
    ingredients_path = directory / "ingredients.yaml"
    dishes_path = directory / "dishes.yaml"
    if not ingredients_path.exists() or not dishes_path.exists():
        raise SeedValidationError(
            f"Faltan los YAML del seed en {directory} (ingredients.yaml y dishes.yaml)."
        )

    raw_ingredients = yaml.safe_load(ingredients_path.read_text(encoding="utf-8"))
    raw_dishes = yaml.safe_load(dishes_path.read_text(encoding="utf-8"))
    if not isinstance(raw_ingredients, list) or not isinstance(raw_dishes, list):
        raise SeedValidationError("Los YAML del seed deben ser listas de elementos.")

    ingredients: list[SeedIngredient] = []
    for index, item in enumerate(raw_ingredients):
        try:
            ingredients.append(SeedIngredient.model_validate(item))
        except ValidationError as exc:
            raise _pydantic_error(ingredients_path, index, exc) from exc

    dishes: list[SeedDish] = []
    for index, item in enumerate(raw_dishes):
        try:
            dishes.append(SeedDish.model_validate(item))
        except ValidationError as exc:
            raise _pydantic_error(dishes_path, index, exc) from exc

    issues = validate_seed(ingredients, dishes)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        message = "\n".join(f"[{issue.code}] {issue.message}" for issue in errors[:20])
        raise SeedValidationError(f"El seed no es válido:\n{message}")

    digest = hashlib.sha256(
        ingredients_path.read_bytes() + b"\n" + dishes_path.read_bytes()
    ).hexdigest()[:16]
    return SeedDocuments(ingredients=ingredients, dishes=dishes, version=digest)


def derive_dish(dish: SeedDish, ingredients_by_slug: dict[str, SeedIngredient]) -> DerivedDish:
    """Calcula flags y etiquetas derivadas de la composición del plato."""
    sources: set[str] = set()
    has_vegetables = False
    servings: dict[str, Decimal] = {
        "vegetable": Decimal(0),
        "protein": Decimal(0),
        "carb": Decimal(0),
    }
    carb_scores: list[tuple[Decimal, str]] = []
    protein_by_source: dict[str, Decimal] = {}
    has_animal = False
    has_dairy = False
    has_egg = False
    has_honey = False
    for item in dish.ingredients:
        ingredient = ingredients_by_slug[item.ingredient]
        quantity_milli = Decimal(to_quantity_milli(item.quantity))
        if ingredient.group == "vegetable":
            has_vegetables = True
        if ingredient.serving_group in servings:
            servings[ingredient.serving_group] += quantity_milli / Decimal(
                ingredient.serving_size_milli
            )
        if ingredient.group == "carb":
            carb_scores.append(
                (
                    quantity_milli / Decimal(ingredient.serving_size_milli),
                    ingredient.slug,
                )
            )
        if ingredient.protein_source:
            sources.add(ingredient.protein_source)
            if ingredient.serving_group == "protein":
                protein_by_source[ingredient.protein_source] = protein_by_source.get(
                    ingredient.protein_source, Decimal(0)
                ) + quantity_milli / Decimal(ingredient.serving_size_milli)
            if ingredient.protein_source in ANIMAL_SOURCES:
                has_animal = True
        if ingredient.group == "dairy":
            has_dairy = True
        if "eggs" in ingredient.allergens:
            has_egg = True
        if ingredient.slug == "honey":
            has_honey = True

    carbs: str | None = None
    if carb_scores:
        _, primary = max(carb_scores)
        carb_tags = [
            tag for tag in ingredients_by_slug[primary].tags if tag.startswith("carb_type:")
        ]
        if carb_tags:
            carbs = carb_tags[0].split(":", 1)[1]

    red_meat = any(source in RED_MEAT_SOURCES for source in sources)
    light = not red_meat and servings["vegetable"] >= Decimal(1) and servings["carb"] <= Decimal(1)
    tags: set[str] = set()
    if "fish" in sources:
        tags.add("fish")
    if "seafood" in sources:
        tags.add("seafood")
    if "legumes" in sources:
        tags.add("legume")
    if red_meat:
        tags.add("red_meat")
    vegetarian = not has_animal
    if vegetarian:
        tags.add("vegetarian")
        if not has_dairy and not has_egg and not has_honey:
            tags.add("vegan")

    base_servings = Decimal(dish.base_servings)
    protein_per_person = servings["protein"] / base_servings
    vegetable_carb_per_person = (servings["vegetable"] + servings["carb"]) / base_servings
    role = (
        "main"
        if protein_per_person >= MAIN_MIN_PROTEIN_RATIONS
        and vegetable_carb_per_person >= MAIN_MIN_VEGETABLE_CARB_RATIONS
        else "complement"
    )
    primary_protein = (
        max(sorted(protein_by_source), key=lambda source: protein_by_source[source])
        if protein_by_source
        else None
    )

    return DerivedDish(
        has_vegetables=has_vegetables,
        light=light,
        carbs=carbs,
        protein_sources=sorted(sources),
        tags=frozenset(tags),
        servings=servings,
        role=role,
        primary_protein=primary_protein,
    )


def validate_seed(ingredients: list[SeedIngredient], dishes: list[SeedDish]) -> list[SeedIssue]:
    """Valida referencias, unidades, flags derivados y cobertura."""
    issues: list[SeedIssue] = []
    ingredients_by_slug: dict[str, SeedIngredient] = {}
    for ingredient in ingredients:
        if ingredient.slug in ingredients_by_slug:
            issues.append(
                SeedIssue(
                    "error", "DUPLICATE_INGREDIENT", f"Ingrediente duplicado: {ingredient.slug}"
                )
            )
        ingredients_by_slug[ingredient.slug] = ingredient

    product_owners: dict[str, str] = {}
    for ingredient in ingredients:
        for product in ingredient.products:
            owner = product_owners.get(product.external_id)
            if owner is not None:
                issues.append(
                    SeedIssue(
                        "error",
                        "SHARED_PRODUCT",
                        (
                            f"El producto {product.external_id} aparece en {owner} "
                            f"y {ingredient.slug}."
                        ),
                        {"product_external_id": product.external_id},
                    )
                )
            product_owners[product.external_id] = ingredient.slug

    dish_slugs: set[str] = set()
    derived_by_dish: dict[str, DerivedDish] = {}
    for dish in dishes:
        if dish.slug in dish_slugs:
            issues.append(SeedIssue("error", "DUPLICATE_DISH", f"Plato duplicado: {dish.slug}"))
        dish_slugs.add(dish.slug)

        for item in dish.ingredients:
            resolved = ingredients_by_slug.get(item.ingredient)
            if resolved is None:
                issues.append(
                    SeedIssue(
                        "error",
                        "UNKNOWN_INGREDIENT",
                        f"{dish.slug} referencia un ingrediente inexistente: {item.ingredient}.",
                    )
                )
                continue
            if item.unit != resolved.base_unit:
                issues.append(
                    SeedIssue(
                        "error",
                        "UNIT_MISMATCH",
                        (
                            f"{dish.slug}: {item.ingredient} está en {item.unit}, "
                            f"pero su unidad base es {resolved.base_unit}."
                        ),
                    )
                )
        if not all(item.ingredient in ingredients_by_slug for item in dish.ingredients):
            continue

        derived = derive_dish(dish, ingredients_by_slug)
        derived_by_dish[dish.slug] = derived
        if derived.has_vegetables != dish.has_vegetables:
            issues.append(
                SeedIssue(
                    "error",
                    "HAS_VEGETABLES_MISMATCH",
                    f"{dish.slug}: has_vegetables debería ser {derived.has_vegetables}.",
                )
            )
        if derived.light != dish.light:
            issues.append(
                SeedIssue(
                    "error",
                    "LIGHT_MISMATCH",
                    f"{dish.slug}: light debería ser {derived.light}.",
                )
            )
        if derived.carbs != dish.carbs:
            issues.append(
                SeedIssue(
                    "error",
                    "CARBS_MISMATCH",
                    f"{dish.slug}: carbs debería ser {derived.carbs!r}.",
                )
            )
        if derived.protein_sources != sorted(dish.protein_sources):
            issues.append(
                SeedIssue(
                    "error",
                    "PROTEIN_SOURCES_MISMATCH",
                    (f"{dish.slug}: protein_sources debería ser {derived.protein_sources}."),
                )
            )
        missing_tags = derived.tags - set(dish.tags)
        if missing_tags:
            issues.append(
                SeedIssue(
                    "error",
                    "MISSING_DERIVED_TAG",
                    f"{dish.slug}: faltan etiquetas derivadas {sorted(missing_tags)}.",
                )
            )

    issues.extend(coverage_issues(dishes, ingredients, derived_by_dish))
    return issues


def coverage_issues(
    dishes: list[SeedDish],
    ingredients: list[SeedIngredient],
    derived_by_dish: dict[str, DerivedDish],
) -> list[SeedIssue]:
    """Comprueba los umbrales de cobertura de PLAN §13.2 para principales y acompañamientos."""
    issues: list[SeedIssue] = []
    derived_dishes = [
        (dish, derived_by_dish[dish.slug]) for dish in dishes if dish.slug in derived_by_dish
    ]
    mains = [(dish, derived) for dish, derived in derived_dishes if derived.role == "main"]
    complements = [
        (dish, derived) for dish, derived in derived_dishes if derived.role == "complement"
    ]

    lunch = sum(1 for dish, _ in mains if "lunch" in dish.meal_types)
    dinner = sum(1 for dish, _ in mains if "dinner" in dish.meal_types)
    if lunch < MIN_LUNCH_DISHES:
        issues.append(
            SeedIssue(
                "error",
                "NOT_ENOUGH_LUNCH",
                f"Solo hay {lunch} platos principales de comida; mínimo {MIN_LUNCH_DISHES}.",
            )
        )
    if dinner < MIN_DINNER_DISHES:
        issues.append(
            SeedIssue(
                "error",
                "NOT_ENOUGH_DINNER",
                f"Solo hay {dinner} platos principales de cena; mínimo {MIN_DINNER_DISHES}.",
            )
        )
    if len(mains) < MIN_TOTAL_DISHES:
        issues.append(
            SeedIssue(
                "error",
                "NOT_ENOUGH_DISHES",
                f"Solo hay {len(mains)} platos principales; mínimo {MIN_TOTAL_DISHES}.",
            )
        )

    if len(complements) < MIN_COMPLEMENTS:
        issues.append(
            SeedIssue(
                "error",
                "NOT_ENOUGH_COMPLEMENTS",
                f"Solo hay {len(complements)} acompañamientos; mínimo {MIN_COMPLEMENTS}.",
            )
        )
    for slot in ("lunch", "dinner"):
        count = sum(1 for dish, _ in complements if slot in dish.meal_types)
        if count < 1:
            issues.append(
                SeedIssue(
                    "error",
                    "MISSING_COMPLEMENT",
                    f"No hay ningún acompañamiento compatible con {slot}.",
                )
            )

    for dish, derived in mains:
        if derived.primary_protein is None:
            issues.append(
                SeedIssue(
                    "error",
                    "MAIN_WITHOUT_PROTEIN_SOURCE",
                    f"{dish.slug}: un plato principal debe declarar una proteína principal.",
                )
            )

    sources: dict[str, int] = {}
    for _, derived in mains:
        for source in derived.protein_sources:
            sources[source] = sources.get(source, 0) + 1
    strong_sources = [source for source, count in sources.items() if count >= MIN_PROTEIN_DISHES]
    if len(strong_sources) < MIN_PROTEIN_SOURCES:
        issues.append(
            SeedIssue(
                "error",
                "NOT_ENOUGH_PROTEIN_SOURCES",
                (
                    f"Solo {len(strong_sources)} fuentes de proteína tienen "
                    f"{MIN_PROTEIN_DISHES}+ platos principales."
                ),
            )
        )

    def count_tag(tag: str, *, dinner_only: bool = False) -> int:
        total = 0
        for dish, derived in mains:
            if dinner_only and "dinner" not in dish.meal_types:
                continue
            if tag in derived.tags:
                total += 1
        return total

    checks = [
        ("NOT_ENOUGH_FISH", "fish", MIN_FISH_DISHES, count_tag("fish")),
        ("NOT_ENOUGH_LEGUME", "legume", MIN_LEGUME_DISHES, count_tag("legume")),
        ("NOT_ENOUGH_RED_MEAT", "red_meat", MIN_RED_MEAT_DISHES, count_tag("red_meat")),
        (
            "NOT_ENOUGH_LIGHT_DINNERS",
            "light",
            MIN_LIGHT_DINNERS,
            sum(1 for dish, derived in mains if "dinner" in dish.meal_types and derived.light),
        ),
    ]
    for code, label, minimum, actual in checks:
        if actual < minimum:
            issues.append(SeedIssue("error", code, f"{label}: {actual} platos; mínimo {minimum}."))

    if not any(ingredient.serving_group == "vegetable" for ingredient in ingredients):
        issues.append(
            SeedIssue("error", "NO_VEGETABLE_SERVINGS", "No hay ingredientes de verdura.")
        )
    if not any(ingredient.serving_group == "carb" for ingredient in ingredients):
        issues.append(SeedIssue("error", "NO_CARB_SERVINGS", "No hay ingredientes de hidrato."))
    return issues


def validate_catalog_mappings(session: Session, documents: SeedDocuments) -> list[SeedIssue]:
    """Valida el mapeo contra el catálogo sincronizado y el UNIQUE(product_id)."""
    issues: list[SeedIssue] = []
    external_ids = [
        product.external_id
        for ingredient in documents.ingredients
        for product in ingredient.products
    ]
    products = {
        product.external_id: product
        for product in session.scalars(
            select(Product).where(Product.external_id.in_(external_ids))
        ).all()
    }
    owners: dict[int, str] = {}
    for ingredient in documents.ingredients:
        usable = 0
        for mapping in ingredient.products:
            product = products.get(mapping.external_id)
            if product is None:
                issues.append(
                    SeedIssue(
                        "error",
                        "MISSING_PRODUCT",
                        (
                            f"{ingredient.slug}: el producto {mapping.external_id} "
                            "no está en el catálogo."
                        ),
                    )
                )
                continue
            owner = owners.get(product.id)
            if owner is not None:
                issues.append(
                    SeedIssue(
                        "error",
                        "SHARED_CATALOG_PRODUCT",
                        f"El producto {mapping.external_id} ya pertenece a {owner}.",
                    )
                )
            owners[product.id] = ingredient.slug
            if product.package_quantity_milli is None or product.package_quantity_milli <= 0:
                issues.append(
                    SeedIssue(
                        "error",
                        "PRODUCT_WITHOUT_QUANTITY",
                        f"{ingredient.slug}: {mapping.external_id} no tiene cantidad de paquete.",
                    )
                )
                continue
            if product.package_price_cents is None or product.package_price_cents <= 0:
                issues.append(
                    SeedIssue(
                        "error",
                        "PRODUCT_WITHOUT_PRICE",
                        f"{ingredient.slug}: {mapping.external_id} no tiene precio.",
                    )
                )
                continue
            if product.package_unit != ingredient.base_unit:
                issues.append(
                    SeedIssue(
                        "error",
                        "PRODUCT_UNIT_MISMATCH",
                        (
                            f"{ingredient.slug}: {mapping.external_id} está en "
                            f"{product.package_unit}, pero la unidad base es "
                            f"{ingredient.base_unit}."
                        ),
                    )
                )
                continue
            if product.approx_size or (product.selling_method or 0) != 0:
                issues.append(
                    SeedIssue(
                        "error",
                        "VARIABLE_WEIGHT_PRODUCT",
                        (
                            f"{ingredient.slug}: {mapping.external_id} es de peso "
                            "variable o mostrador."
                        ),
                    )
                )
                continue
            if not product.published:
                issues.append(
                    SeedIssue(
                        "warning",
                        "UNPUBLISHED_PRODUCT",
                        f"{ingredient.slug}: {mapping.external_id} no está disponible ahora.",
                    )
                )
            usable += 1
        if usable == 0:
            issues.append(
                SeedIssue(
                    "error",
                    "NO_USABLE_PRODUCT",
                    f"{ingredient.slug}: no tiene ningún producto utilizable.",
                )
            )
    return issues


class SeedService:
    """Carga idempotente del seed sobre una base ya migrada."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        data_dir: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir

    def load(self, *, dry_run: bool = False) -> SeedLoadResult:
        """Carga ingredientes, mapeos y platos; no borra datos de usuario."""
        documents = load_seed_documents(self._data_dir)
        result = SeedLoadResult(version=documents.version, dry_run=dry_run)
        with self._session_factory() as session:
            self._load_documents(session, documents, result)
            if dry_run:
                session.rollback()
            else:
                session.commit()
        return result

    def _load_documents(
        self, session: Session, documents: SeedDocuments, result: SeedLoadResult
    ) -> None:
        catalog_count = session.scalar(select(func.count()).select_from(Product)) or 0
        products = {
            product.external_id: product
            for product in session.scalars(
                select(Product).where(
                    Product.external_id.in_(
                        [
                            mapping.external_id
                            for ingredient in documents.ingredients
                            for mapping in ingredient.products
                        ]
                    )
                )
            ).all()
        }
        ingredients = {
            ingredient.slug: ingredient for ingredient in session.scalars(select(Ingredient)).all()
        }
        dishes = {dish.slug: dish for dish in session.scalars(select(Dish)).all()}
        ingredients_by_slug = {ingredient.slug: ingredient for ingredient in documents.ingredients}

        for seed_ingredient in documents.ingredients:
            ingredient = ingredients.get(seed_ingredient.slug)
            if ingredient is None:
                ingredient = Ingredient(slug=seed_ingredient.slug)
                session.add(ingredient)
                ingredients[seed_ingredient.slug] = ingredient
            ingredient.name = seed_ingredient.name
            ingredient.category = seed_ingredient.category
            ingredient.group = seed_ingredient.group
            ingredient.base_unit = seed_ingredient.base_unit
            ingredient.grams_per_unit = seed_ingredient.grams_per_unit
            ingredient.protein_source = seed_ingredient.protein_source
            ingredient.serving_group = seed_ingredient.serving_group
            ingredient.serving_size_milli = seed_ingredient.serving_size_milli
            ingredient.allergens_json = list(seed_ingredient.allergens)
            ingredient.tags_json = list(seed_ingredient.tags)
            ingredient.active = True
            result.ingredients += 1

        session.flush()

        if catalog_count > 0:
            for seed_ingredient in documents.ingredients:
                ingredient = ingredients[seed_ingredient.slug]
                existing = {row.product.external_id: row for row in ingredient.products}
                desired: list[tuple[str, int, bool, int]] = []
                for seed_product in seed_ingredient.products:
                    product = products.get(seed_product.external_id)
                    if product is None:
                        result.missing_products.append(seed_product.external_id)
                        continue
                    if not _product_is_mappable(product):
                        result.skipped_products.append(seed_product.external_id)
                        continue
                    desired.append(
                        (
                            seed_product.external_id,
                            product.id,
                            seed_product.is_default,
                            seed_product.priority,
                        )
                    )
                desired_ids = {item[0] for item in desired}
                stale = [
                    row for external_id, row in existing.items() if external_id not in desired_ids
                ]
                for row in stale:
                    ingredient.products.remove(row)
                kept = [row for external_id, row in existing.items() if external_id in desired_ids]
                # Las prioridades y el índice parcial de «default» pueden
                # colisionar si el YAML reordena formatos: se liberan antes
                # con valores temporales positivos.
                for row in kept:
                    row.priority = 1_000_000 + row.priority
                    row.is_default = False
                session.flush()
                for external_id, product_id, is_default, priority in desired:
                    existing_row = existing.get(external_id)
                    if existing_row is None:
                        existing_row = IngredientProduct(product_id=product_id)
                        ingredient.products.append(existing_row)
                    existing_row.priority = priority
                    existing_row.is_default = is_default
                result.products += len(desired)
                session.flush()

        for seed_dish in documents.dishes:
            dish = dishes.get(seed_dish.slug)
            if dish is None:
                dish = Dish(slug=seed_dish.slug)
                session.add(dish)
                dishes[seed_dish.slug] = dish
            derived = derive_dish(
                seed_dish,
                ingredients_by_slug,
            )
            dish.name = seed_dish.name
            dish.description = seed_dish.description
            dish.base_servings = seed_dish.base_servings
            dish.role = derived.role
            dish.primary_protein = derived.primary_protein
            dish.meal_types_json = list(seed_dish.meal_types)
            dish.protein_sources_json = list(seed_dish.protein_sources)
            dish.has_vegetables = seed_dish.has_vegetables
            dish.light = seed_dish.light
            dish.carbs = seed_dish.carbs
            dish.tags_json = list(seed_dish.tags)
            dish.active = True
            dish.seed_version = documents.version
            existing_links = {link.ingredient_id: link for link in dish.ingredients}
            desired_links: set[int] = set()
            for item in seed_dish.ingredients:
                ingredient_id = ingredients[item.ingredient].id
                desired_links.add(ingredient_id)
                link = existing_links.get(ingredient_id)
                quantity_milli = to_quantity_milli(item.quantity)
                if link is None:
                    dish.ingredients.append(
                        DishIngredient(
                            ingredient_id=ingredient_id,
                            quantity_milli=quantity_milli,
                        )
                    )
                else:
                    link.quantity_milli = quantity_milli
            for ingredient_id, link in existing_links.items():
                if ingredient_id not in desired_links:
                    dish.ingredients.remove(link)
            result.dishes += 1

        seeded_ingredients = {seed.slug for seed in documents.ingredients}
        seeded_dishes = {seed.slug for seed in documents.dishes}
        ingredient_update = session.execute(
            update(Ingredient)
            .where(Ingredient.slug.not_in(seeded_ingredients))
            .where(Ingredient.active.is_(True))
            .values(active=False)
        )
        result.deactivated_ingredients = getattr(ingredient_update, "rowcount", 0) or 0
        dish_update = session.execute(
            update(Dish)
            .where(Dish.slug.not_in(seeded_dishes))
            .where(Dish.active.is_(True))
            .values(active=False)
        )
        result.deactivated_dishes = getattr(dish_update, "rowcount", 0) or 0

        if result.missing_products:
            result.issues.append(
                SeedIssue(
                    "warning",
                    "MISSING_PRODUCTS",
                    f"{len(result.missing_products)} productos del seed no están en el catálogo.",
                )
            )
        if result.skipped_products:
            result.issues.append(
                SeedIssue(
                    "warning",
                    "SKIPPED_PRODUCTS",
                    (
                        f"{len(result.skipped_products)} productos no son mapeables "
                        "(formato o peso variable)."
                    ),
                )
            )


def _product_is_mappable(product: Product) -> bool:
    """Formato fijo, precio y cantidad positivos, fuera de mostrador."""
    return (
        product.package_quantity_milli is not None
        and product.package_quantity_milli > 0
        and product.package_price_cents is not None
        and product.package_price_cents > 0
        and product.package_unit in {"g", "ml", "unit"}
        and not product.approx_size
        and (product.selling_method or 0) == 0
    )
