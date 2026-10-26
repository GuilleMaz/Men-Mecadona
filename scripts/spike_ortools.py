"""Spike de OR-Tools CP-SAT (F0.6).

Construye un modelo toy con la forma del optimizador real:

- 14 dias x 2 huecos = 28 huecos.
- 60 platos (comida, cena o ambos) con 1-4 raciones base.
- 120 ingredientes con 1-2 formatos de paquete.
- Demanda dependiente de los platos elegidos, despensa y presupuesto duro.
- Minimos diarios de verdura, proteina e hidrato.
- Variedad lexicografica en dos etapas.

El objetivo del spike es medir si CP-SAT resuelve esta instancia en menos de 10 s
con `num_search_workers=1` y semilla fija. No es el optimizador definitivo de F4.

Uso desde la raiz del repositorio:

    backend\\.venv\\Scripts\\python.exe scripts\\spike_ortools.py

o:

    cd backend
    uv run python ..\\scripts\\spike_ortools.py
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from fractions import Fraction

import ortools
from ortools.sat.python import cp_model

DAYS = 14
SLOTS = ("lunch", "dinner")
PEOPLE = 4
MAX_REPEATS = 1

STAGE1_SECONDS = 3.0
STAGE2_SECONDS = 3.0
TOTAL_LIMIT_SECONDS = 10.0
SOLVER_SEED = 42
DEFAULT_REPETITIONS = 3

VEGETABLE_SERVING_MILLI = 150_000
PROTEIN_SERVING_MILLI = 100_000
LEGUME_SERVING_MILLI = 80_000
DAIRY_SERVING_MILLI = 200_000
EGG_SERVING_MILLI = 2_000
CARB_SERVING_MILLI = 60_000

PROTEIN_SOURCES = (
    "chicken",
    "turkey",
    "beef",
    "pork",
    "fish",
    "eggs",
    "legumes",
    "dairy",
    "tofu",
)
CARB_SOURCES = ("rice", "pasta", "potato", "bread")


@dataclass(frozen=True)
class Product:
    """Formato de compra de un ingrediente."""

    id: str
    package_quantity_milli: int
    package_price_cents: int


@dataclass(frozen=True)
class Ingredient:
    """Ingrediente canonico del modelo toy."""

    id: int
    name: str
    serving_group: str
    serving_size_milli: int
    pantry_milli: int
    protein_source: str | None
    carb_source: str | None
    products: tuple[Product, ...]


@dataclass(frozen=True)
class Dish:
    """Plato con composicion por racion base."""

    id: int
    name: str
    meal_types: frozenset[str]
    base_servings: int
    ingredients: tuple[tuple[int, int], ...]
    protein_sources: frozenset[str]
    carb_sources: frozenset[str]
    has_fish: bool
    has_legumes: bool
    has_red_meat: bool
    is_light: bool


@dataclass(frozen=True)
class VarietyThresholds:
    """Umbrales de variedad de PLAN.md §6.6 para 14 dias."""

    protein_sources: int
    fish_dishes: int
    legume_dishes: int
    red_meat_dishes: int
    light_dinners: int
    carb_sources: int

    @classmethod
    def for_days(cls, days: int) -> VarietyThresholds:
        return cls(
            protein_sources=min(3, days),
            fish_dishes=math.ceil(days / 7),
            legume_dishes=math.ceil(days / 7),
            red_meat_dishes=math.ceil(days * 3 / 7),
            light_dinners=math.ceil(days / 2),
            carb_sources=min(2, days),
        )


@dataclass(frozen=True)
class Instance:
    """Instancia completa del spike."""

    people: int
    days: int
    dishes: tuple[Dish, ...]
    ingredients: tuple[Ingredient, ...]
    reference_lunch: tuple[Dish, ...]
    reference_dinner: tuple[Dish, ...]
    budget_cents: int
    reference_ticket_cents: int
    locks: tuple[tuple[int, int, str], ...]
    thresholds: VarietyThresholds

    @property
    def slots(self) -> list[tuple[int, str]]:
        return [(day, slot) for day in range(self.days) for slot in SLOTS]

    @property
    def product_count(self) -> int:
        return sum(len(ingredient.products) for ingredient in self.ingredients)


@dataclass
class StageResult:
    """Resultado de una etapa del solver."""

    status: int
    status_name: str
    objective: int
    seconds: float
    optimal: bool
    num_search_workers: int
    assignments: dict[tuple[int, int, str], int]
    packages: dict[str, int]


@dataclass
class ModelVars:
    """Variables y expresiones del modelo para extraer y validar la solucion."""

    x: dict[tuple[int, int, str], cp_model.IntVar]
    q: dict[str, cp_model.IntVar]
    violations: list[cp_model.IntVar]
    total_violations: cp_model.LinearExpr


def _products(
    counter: list[int],
    small_quantity: int,
    small_price: int,
    large_quantity: int,
    large_price: int,
) -> tuple[Product, ...]:
    """Crea dos formatos de compra con identificadores unicos."""
    counter[0] += 1
    small = Product(
        id=f"P{counter[0]:04d}",
        package_quantity_milli=small_quantity,
        package_price_cents=small_price,
    )
    counter[0] += 1
    large = Product(
        id=f"P{counter[0]:04d}",
        package_quantity_milli=large_quantity,
        package_price_cents=large_price,
    )
    return (small, large)


def _make_ingredients() -> tuple[Ingredient, ...]:
    """Genera 120 ingredientes: 40 verduras, 30 proteinas, 25 hidratos y 25 extras."""
    counter = [0]
    ingredients: list[Ingredient] = []
    next_id = 0

    for index in range(40):
        small_price = 120 + (index % 5) * 20
        ingredients.append(
            Ingredient(
                id=next_id,
                name=f"Verdura {index + 1:02d}",
                serving_group="vegetable",
                serving_size_milli=VEGETABLE_SERVING_MILLI,
                pantry_milli=0,
                protein_source=None,
                carb_source=None,
                products=_products(
                    counter,
                    400_000,
                    small_price,
                    1_000_000,
                    round(small_price * 2.2),
                ),
            )
        )
        next_id += 1

    # 30 proteinas: 4 pollo/pavo/ternera y 3 del resto de fuentes.
    protein_count_by_source = {
        "chicken": 4,
        "turkey": 4,
        "beef": 4,
        "pork": 3,
        "fish": 3,
        "eggs": 3,
        "legumes": 3,
        "dairy": 3,
        "tofu": 3,
    }
    protein_sources = [
        source for source in PROTEIN_SOURCES for _ in range(protein_count_by_source[source])
    ]
    for index, source in enumerate(protein_sources):
        if source == "eggs":
            serving_size = EGG_SERVING_MILLI
            products = _products(counter, 6_000, 150, 12_000, 280)
        elif source == "legumes":
            serving_size = LEGUME_SERVING_MILLI
            products = _products(counter, 400_000, 120, 1_000_000, 260)
        elif source == "dairy":
            serving_size = DAIRY_SERVING_MILLI
            products = _products(counter, 1_000_000, 100, 2_000_000, 180)
        else:
            serving_size = PROTEIN_SERVING_MILLI
            base_price = {
                "chicken": 350,
                "turkey": 420,
                "beef": 600,
                "pork": 450,
                "fish": 500,
                "tofu": 300,
            }[source]
            products = _products(
                counter,
                400_000 + (index % 3) * 100_000,
                base_price,
                1_000_000,
                round(base_price * 2.2),
            )
        ingredients.append(
            Ingredient(
                id=next_id,
                name=f"{source.capitalize()} {index + 1:02d}",
                serving_group="protein",
                serving_size_milli=serving_size,
                pantry_milli=0,
                protein_source=source,
                carb_source=None,
                products=products,
            )
        )
        next_id += 1

    pantry_by_source = {"rice": 500_000, "pasta": 250_000, "potato": 1_000_000}
    for index in range(25):
        source = CARB_SOURCES[index % len(CARB_SOURCES)]
        if source == "potato":
            products = _products(counter, 2_000_000, 250, 5_000_000, 550)
        elif source == "bread":
            products = _products(counter, 500_000, 180, 1_000_000, 320)
        else:
            products = _products(counter, 1_000_000, 150, 5_000_000, 600)
        ingredients.append(
            Ingredient(
                id=next_id,
                name=f"{source.capitalize()} {index + 1:02d}",
                serving_group="carb",
                serving_size_milli=CARB_SERVING_MILLI,
                pantry_milli=pantry_by_source.get(source, 0) if index < 8 else 0,
                protein_source=None,
                carb_source=source,
                products=products,
            )
        )
        next_id += 1

    for index in range(25):
        ingredients.append(
            Ingredient(
                id=next_id,
                name=f"Extra {index + 1:02d}",
                serving_group="none",
                serving_size_milli=1_000,
                pantry_milli=500_000 if index == 0 else 0,
                protein_source=None,
                carb_source=None,
                products=_products(counter, 250_000, 200, 1_000_000, 600),
            )
        )
        next_id += 1

    if len(ingredients) != 120:
        raise RuntimeError(f"Se esperaban 120 ingredientes y se generaron {len(ingredients)}")
    return tuple(ingredients)


def _by_source(
    ingredients: tuple[Ingredient, ...],
    group: str,
    attribute: str,
) -> dict[str, list[Ingredient]]:
    grouped: dict[str, list[Ingredient]] = {}
    for ingredient in ingredients:
        if ingredient.serving_group != group:
            continue
        source = getattr(ingredient, attribute)
        if source is None:
            continue
        grouped.setdefault(source, []).append(ingredient)
    return grouped


def _pick(grouped: dict[str, list[Ingredient]], source: str, index: int) -> Ingredient:
    """Devuelve el ingrediente `index` de una fuente, ciclando si hace falta."""
    candidates = grouped[source]
    return candidates[index % len(candidates)]


def _protein_quantity(source: str, meal_type: str) -> int:
    if source == "eggs":
        return 2_000
    if source == "legumes":
        return {"lunch": 100_000, "dinner": 90_000, "both": 80_000}[meal_type]
    if source == "dairy":
        return {"lunch": 250_000, "dinner": 200_000, "both": 200_000}[meal_type]
    return {"lunch": 150_000, "dinner": 130_000, "both": 120_000}[meal_type]


def _carb_quantity(meal_type: str, index: int) -> int:
    if meal_type == "dinner":
        return 0 if index % 3 == 0 else 40_000
    if meal_type == "lunch":
        return 80_000 + (index % 3) * 10_000
    return 60_000


def _make_dish(
    dish_id: int,
    protein: Ingredient,
    carb: Ingredient,
    vegetable_a: Ingredient,
    vegetable_b: Ingredient,
    extra: Ingredient,
    meal_types: frozenset[str],
    meal_type: str,
    base_servings: int,
    quantity_index: int,
) -> Dish:
    """Construye un plato y deriva sus flags de composicion."""
    protein_qty = _protein_quantity(protein.protein_source or "", meal_type)
    carb_qty = _carb_quantity(meal_type, quantity_index)
    components = [
        (vegetable_a.id, 180_000 * base_servings),
        (vegetable_b.id, 100_000 * base_servings),
        (protein.id, protein_qty * base_servings),
        (extra.id, 10_000 * base_servings),
    ]
    if carb_qty > 0:
        components.append((carb.id, carb_qty * base_servings))

    source = protein.protein_source or ""
    has_red_meat = source in {"beef", "pork"}
    vegetable_total_milli = 180_000 + 100_000
    is_light = (
        not has_red_meat
        and vegetable_total_milli >= VEGETABLE_SERVING_MILLI
        and carb_qty <= CARB_SERVING_MILLI
    )
    return Dish(
        id=dish_id,
        name=f"{dish_id + 1:02d}. {protein.name} con {vegetable_a.name}",
        meal_types=meal_types,
        base_servings=base_servings,
        ingredients=tuple(components),
        protein_sources=frozenset({source}),
        carb_sources=frozenset({carb.carb_source}) if carb.carb_source else frozenset(),
        has_fish=source == "fish",
        has_legumes=source == "legumes",
        has_red_meat=has_red_meat,
        is_light=is_light,
    )


def _make_dishes(ingredients: tuple[Ingredient, ...]) -> tuple[Dish, ...]:
    """Genera 20 comidas, 20 cenas y 20 platos para ambos huecos."""
    proteins = _by_source(ingredients, "protein", "protein_source")
    carbs = _by_source(ingredients, "carb", "carb_source")
    vegetables = [item for item in ingredients if item.serving_group == "vegetable"]
    extras = [item for item in ingredients if item.serving_group == "none"]

    lunch_specs = [
        ("beef", 0),
        ("pork", 0),
        ("beef", 1),
        ("pork", 1),
        ("beef", 2),
        ("fish", 0),
        ("fish", 1),
        ("fish", 2),
        ("legumes", 0),
        ("legumes", 1),
        ("legumes", 2),
        ("chicken", 0),
        ("turkey", 0),
        ("eggs", 0),
        ("pork", 2),
        ("chicken", 1),
        ("turkey", 1),
        ("eggs", 1),
        ("dairy", 0),
        ("tofu", 0),
    ]
    dinner_specs = [
        ("fish", 0),
        ("fish", 1),
        ("fish", 2),
        ("legumes", 0),
        ("legumes", 1),
        ("legumes", 2),
        ("chicken", 2),
        ("chicken", 3),
        ("turkey", 2),
        ("turkey", 3),
        ("eggs", 2),
        ("dairy", 1),
        ("dairy", 2),
        ("tofu", 1),
        ("tofu", 2),
        ("chicken", 0),
        ("turkey", 0),
        ("eggs", 0),
        ("fish", 0),
        ("legumes", 0),
    ]
    both_specs = [
        ("beef", 3),
        ("pork", 0),
        ("fish", 0),
        ("chicken", 0),
        ("turkey", 1),
        ("eggs", 1),
        ("legumes", 1),
        ("dairy", 0),
        ("tofu", 0),
        ("chicken", 1),
        ("beef", 0),
        ("fish", 1),
        ("legumes", 2),
        ("turkey", 2),
        ("eggs", 0),
        ("dairy", 1),
        ("tofu", 1),
        ("chicken", 2),
        ("fish", 2),
        ("pork", 1),
    ]

    carb_sources = list(CARB_SOURCES)
    dishes: list[Dish] = []
    specs = (
        (lunch_specs, frozenset({"lunch"}), "lunch"),
        (dinner_specs, frozenset({"dinner"}), "dinner"),
        (both_specs, frozenset({"lunch", "dinner"}), "both"),
    )
    for spec_group, meal_types, meal_type in specs:
        for index, (source, source_index) in enumerate(spec_group):
            dish_id = len(dishes)
            protein = _pick(proteins, source, source_index)
            carb_source = carb_sources[dish_id % len(carb_sources)]
            carb = _pick(carbs, carb_source, dish_id)
            vegetable_a = vegetables[(dish_id * 2) % len(vegetables)]
            vegetable_b = vegetables[(dish_id * 2 + 1) % len(vegetables)]
            extra = extras[dish_id % len(extras)]
            base_servings = 1 + (dish_id % 4)
            dishes.append(
                _make_dish(
                    dish_id,
                    protein,
                    carb,
                    vegetable_a,
                    vegetable_b,
                    extra,
                    meal_types,
                    meal_type,
                    base_servings,
                    index,
                )
            )
    return tuple(dishes)


def _coef(quantity_milli: int, people: int, base_servings: int) -> int:
    """Redondeo entero por plato, como en PLAN.md §11.1."""
    return (quantity_milli * people + base_servings // 2) // base_servings


def _plan_purchase(ingredient: Ingredient, need_milli: int) -> tuple[int, dict[str, int]]:
    """Plan de compra de referencia: coste minimo y, a igualdad, menos paquetes."""
    net_need = max(0, need_milli - ingredient.pantry_milli)
    best: tuple[int, int, dict[str, int]] | None = None
    products = ingredient.products

    if len(products) == 1:
        packages = math.ceil(net_need / products[0].package_quantity_milli) if net_need else 0
        return packages * products[0].package_price_cents, {products[0].id: packages}

    first, second = products
    max_first = math.ceil(net_need / first.package_quantity_milli) if net_need else 0
    for first_qty in range(max_first + 1):
        remaining = max(0, net_need - first_qty * first.package_quantity_milli)
        second_qty = math.ceil(remaining / second.package_quantity_milli) if remaining else 0
        cost = first_qty * first.package_price_cents + second_qty * second.package_price_cents
        packages = first_qty + second_qty
        candidate = (cost, packages, {first.id: first_qty, second.id: second_qty})
        if best is None or candidate[:2] < best[:2]:
            best = candidate

    if best is None:  # pragma: no cover - siempre hay al menos una combinacion
        raise RuntimeError(f"Sin plan de compra para {ingredient.name}")
    return best[0], best[2]


def _make_instance() -> Instance:
    """Crea la instancia determinista del spike."""
    ingredients = _make_ingredients()
    dishes = _make_dishes(ingredients)
    ingredient_by_id = {ingredient.id: ingredient for ingredient in ingredients}

    lunch_only = [dish for dish in dishes if dish.meal_types == frozenset({"lunch"})]
    dinner_only = [dish for dish in dishes if dish.meal_types == frozenset({"dinner"})]
    reference_lunch = tuple(lunch_only[:DAYS])
    reference_dinner = tuple(dinner_only[:DAYS])

    needs: dict[int, int] = {ingredient.id: 0 for ingredient in ingredients}
    for dish in (*reference_lunch, *reference_dinner):
        for ingredient_id, quantity_milli in dish.ingredients:
            needs[ingredient_id] += _coef(quantity_milli, PEOPLE, dish.base_servings)

    reference_ticket = 0
    for ingredient_id, need_milli in needs.items():
        cost, _ = _plan_purchase(ingredient_by_id[ingredient_id], need_milli)
        reference_ticket += cost

    budget_cents = reference_ticket + max(100, math.ceil(reference_ticket * 0.05))
    locks = (
        (reference_lunch[0].id, 0, "lunch"),
        (reference_dinner[0].id, 0, "dinner"),
    )
    return Instance(
        people=PEOPLE,
        days=DAYS,
        dishes=dishes,
        ingredients=ingredients,
        reference_lunch=reference_lunch,
        reference_dinner=reference_dinner,
        budget_cents=budget_cents,
        reference_ticket_cents=reference_ticket,
        locks=locks,
        thresholds=VarietyThresholds.for_days(DAYS),
    )


def _build_model(
    instance: Instance,
    *,
    fixed_violations: int | None,
    objective: str,
) -> tuple[cp_model.CpModel, ModelVars]:
    """Construye una etapa del modelo CP-SAT."""
    model = cp_model.CpModel()
    ingredient_by_id = {ingredient.id: ingredient for ingredient in instance.ingredients}
    slots = instance.slots

    x: dict[tuple[int, int, str], cp_model.IntVar] = {}
    x_by_slot: dict[tuple[int, str], list[cp_model.IntVar]] = {slot: [] for slot in slots}
    x_by_dish: dict[int, list[cp_model.IntVar]] = {dish.id: [] for dish in instance.dishes}
    for dish in instance.dishes:
        for day, slot in slots:
            if slot not in dish.meal_types:
                continue
            variable = model.NewBoolVar(f"x_{dish.id}_{day}_{slot}")
            x[(dish.id, day, slot)] = variable
            x_by_slot[(day, slot)].append(variable)
            x_by_dish[dish.id].append(variable)

    for slot, variables in x_by_slot.items():
        model.Add(sum(variables) == 1)
        if not variables:  # pragma: no cover - la instancia lo evita
            raise RuntimeError(f"Sin platos compatibles para el hueco {slot}")

    for dish in instance.dishes:
        model.Add(sum(x_by_dish[dish.id]) <= MAX_REPEATS)
    for dish_id, day, slot in instance.locks:
        model.Add(x[(dish_id, day, slot)] == 1)

    coef_by_dish: dict[int, dict[int, int]] = {}
    for dish in instance.dishes:
        coef_by_dish[dish.id] = {
            ingredient_id: _coef(quantity_milli, instance.people, dish.base_servings)
            for ingredient_id, quantity_milli in dish.ingredients
        }

    q: dict[str, cp_model.IntVar] = {}
    for ingredient in instance.ingredients:
        max_need = sum(coef_by_dish[dish.id].get(ingredient.id, 0) for dish in instance.dishes)
        for product in ingredient.products:
            net = max(0, max_need - ingredient.pantry_milli)
            upper = math.ceil(net / product.package_quantity_milli) if net else 0
            q[product.id] = model.NewIntVar(0, upper, f"q_{product.id}")

    for ingredient in instance.ingredients:
        demand_terms = [
            coef_by_dish[dish.id][ingredient.id] * sum(x_by_dish[dish.id])
            for dish in instance.dishes
            if ingredient.id in coef_by_dish[dish.id]
        ]
        supply = sum(
            q[product.id] * product.package_quantity_milli for product in ingredient.products
        )
        model.Add(supply + ingredient.pantry_milli >= sum(demand_terms))

    # Minimos diarios por grupo, en mili-raciones (1 racion = 1_000_000).
    for day in range(instance.days):
        for group in ("vegetable", "protein", "carb"):
            terms: list[cp_model.LinearExpr] = []
            for dish in instance.dishes:
                if group not in _dish_groups(dish, ingredient_by_id):
                    continue
                for slot in SLOTS:
                    variable = x.get((dish.id, day, slot))
                    if variable is None:
                        continue
                    for ingredient_id, _ in dish.ingredients:
                        ingredient = ingredient_by_id[ingredient_id]
                        if ingredient.serving_group != group:
                            continue
                        coef = coef_by_dish[dish.id][ingredient_id]
                        ration_milli = (
                            coef * 1_000_000 + ingredient.serving_size_milli // 2
                        ) // ingredient.serving_size_milli
                        terms.append(ration_milli * variable)
            model.Add(sum(terms) >= instance.people * 1_000_000)

    model.Add(
        sum(
            q[product.id] * product.package_price_cents
            for ingredient in instance.ingredients
            for product in ingredient.products
        )
        <= instance.budget_cents
    )

    violations: list[cp_model.IntVar] = []
    thresholds = instance.thresholds

    def add_lower_bound(name: str, threshold: int, expression: cp_model.LinearExpr) -> None:
        violation = model.NewIntVar(0, threshold, name)
        model.Add(violation >= threshold - expression)
        violations.append(violation)

    def add_upper_bound(name: str, threshold: int, expression: cp_model.LinearExpr) -> None:
        violation = model.NewIntVar(0, len(slots), name)
        model.Add(violation >= expression - threshold)
        violations.append(violation)

    protein_sources = sorted(
        {source for dish in instance.dishes for source in dish.protein_sources}
    )
    protein_presence: list[cp_model.IntVar] = []
    for source in protein_sources:
        variables = [
            variable
            for dish in instance.dishes
            if source in dish.protein_sources
            for variable in x_by_dish[dish.id]
        ]
        if not variables:  # pragma: no cover - la instancia lo evita
            continue
        presence = model.NewBoolVar(f"protein_{source}")
        for variable in variables:
            model.Add(presence >= variable)
        model.Add(presence <= sum(variables))
        protein_presence.append(presence)
    add_lower_bound(
        "violation_protein_sources",
        thresholds.protein_sources,
        sum(protein_presence),
    )

    carb_sources = sorted({source for dish in instance.dishes for source in dish.carb_sources})
    carb_presence: list[cp_model.IntVar] = []
    for source in carb_sources:
        variables = [
            variable
            for dish in instance.dishes
            if source in dish.carb_sources
            for variable in x_by_dish[dish.id]
        ]
        if not variables:  # pragma: no cover - la instancia lo evita
            continue
        presence = model.NewBoolVar(f"carb_{source}")
        for variable in variables:
            model.Add(presence >= variable)
        model.Add(presence <= sum(variables))
        carb_presence.append(presence)
    add_lower_bound(
        "violation_carb_sources",
        thresholds.carb_sources,
        sum(carb_presence),
    )

    fish_count = sum(
        variable for dish in instance.dishes if dish.has_fish for variable in x_by_dish[dish.id]
    )
    add_lower_bound("violation_fish", thresholds.fish_dishes, fish_count)

    legume_count = sum(
        variable for dish in instance.dishes if dish.has_legumes for variable in x_by_dish[dish.id]
    )
    add_lower_bound("violation_legumes", thresholds.legume_dishes, legume_count)

    red_meat_count = sum(
        variable for dish in instance.dishes if dish.has_red_meat for variable in x_by_dish[dish.id]
    )
    add_upper_bound("violation_red_meat", thresholds.red_meat_dishes, red_meat_count)

    light_dinner_count = sum(
        x[(dish.id, day, "dinner")]
        for dish in instance.dishes
        if dish.is_light and "dinner" in dish.meal_types
        for day in range(instance.days)
    )
    add_lower_bound("violation_light_dinners", thresholds.light_dinners, light_dinner_count)

    total_violations = sum(violations)
    if fixed_violations is not None:
        model.Add(total_violations == fixed_violations)

    if objective == "violations":
        model.Minimize(total_violations)
    elif objective == "ticket":
        model.Minimize(
            sum(
                q[product.id] * product.package_price_cents
                for ingredient in instance.ingredients
                for product in ingredient.products
            )
        )
    else:  # pragma: no cover - proteccion ante errores de programacion
        raise ValueError(f"Objetivo desconocido: {objective}")

    if len(instance.dishes) != 60 or len(instance.ingredients) != 120:
        raise RuntimeError("La instancia del spike no tiene 60 platos y 120 ingredientes")

    return model, ModelVars(x=x, q=q, violations=violations, total_violations=total_violations)


def _dish_groups(dish: Dish, ingredient_by_id: dict[int, Ingredient]) -> set[str]:
    return {
        ingredient_by_id[ingredient_id].serving_group
        for ingredient_id, _ in dish.ingredients
        if ingredient_by_id[ingredient_id].serving_group != "none"
    }


def _apply_stage1_hint(
    model: cp_model.CpModel,
    variables: ModelVars,
    stage1: StageResult,
) -> None:
    """Usa el incumbente de la etapa 1 como pista de la etapa 2."""
    for key, variable in variables.x.items():
        model.AddHint(variable, stage1.assignments.get(key, 0))
    for product_id, variable in variables.q.items():
        model.AddHint(variable, stage1.packages.get(product_id, 0))


def _solve(model: cp_model.CpModel, seconds: float) -> tuple[cp_model.CpSolver, int, str]:
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = SOLVER_SEED
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.log_search_progress = False
    if solver.parameters.num_search_workers != 1:  # pragma: no cover - proteccion
        raise RuntimeError("num_search_workers no se ha fijado a 1")
    status = solver.Solve(model)
    return solver, status, solver.StatusName(status)


def _extract(
    solver: cp_model.CpSolver,
    status: int,
    status_name: str,
    variables: ModelVars,
    seconds: float,
) -> StageResult:
    assignments = {key: solver.Value(variable) for key, variable in variables.x.items()}
    packages = {product_id: solver.Value(variable) for product_id, variable in variables.q.items()}
    value = (
        int(round(solver.ObjectiveValue()))
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else -1
    )
    return StageResult(
        status=status,
        status_name=status_name,
        objective=value,
        seconds=seconds,
        optimal=status == cp_model.OPTIMAL,
        num_search_workers=solver.parameters.num_search_workers,
        assignments=assignments,
        packages=packages,
    )


def _validate(
    instance: Instance,
    stage1: StageResult,
    stage2: StageResult,
) -> list[str]:
    """Comprueba la solucion devuelta contra todas las reglas del modelo."""
    errors: list[str] = []
    dish_by_id = {dish.id: dish for dish in instance.dishes}
    ingredient_by_id = {ingredient.id: ingredient for ingredient in instance.ingredients}
    product_by_id = {
        product.id: product
        for ingredient in instance.ingredients
        for product in ingredient.products
    }
    selected = [
        (dish_by_id[dish_id], day, slot)
        for (dish_id, day, slot), value in stage2.assignments.items()
        if value
    ]

    if len(selected) != len(instance.slots):
        errors.append(f"Huecos cubiertos: {len(selected)} de {len(instance.slots)}")
    if len({(day, slot) for _, day, slot in selected}) != len(instance.slots):
        errors.append("Hay huecos repetidos o sin cubrir")
    if len({dish.id for dish, _, _ in selected}) != len(selected):
        errors.append("Hay platos repetidos con max_repeats=1")
    for dish_id, day, slot in instance.locks:
        if stage2.assignments.get((dish_id, day, slot)) != 1:
            errors.append(f"Bloqueo incumplido: {dish_id} en {day}/{slot}")

    ticket = sum(
        count * product_by_id[product_id].package_price_cents
        for product_id, count in stage2.packages.items()
    )
    if ticket > instance.budget_cents:
        errors.append(f"Ticket {ticket} > presupuesto {instance.budget_cents}")

    needs: dict[int, int] = {ingredient.id: 0 for ingredient in instance.ingredients}
    for dish, _, _ in selected:
        for ingredient_id, quantity_milli in dish.ingredients:
            needs[ingredient_id] += _coef(quantity_milli, instance.people, dish.base_servings)
    for ingredient in instance.ingredients:
        purchased = sum(
            stage2.packages.get(product.id, 0) * product.package_quantity_milli
            for product in ingredient.products
        )
        if purchased + ingredient.pantry_milli < needs[ingredient.id]:
            errors.append(f"Demanda insuficiente para {ingredient.name}")

    for day in range(instance.days):
        day_dishes = [dish for dish, dish_day, _ in selected if dish_day == day]
        for group in ("vegetable", "protein", "carb"):
            rations = Fraction(0)
            for dish in day_dishes:
                for ingredient_id, _ in dish.ingredients:
                    ingredient = ingredient_by_id[ingredient_id]
                    if ingredient.serving_group != group:
                        continue
                    coef = _coef(
                        dict(dish.ingredients)[ingredient_id],
                        instance.people,
                        dish.base_servings,
                    )
                    rations += Fraction(coef, ingredient.serving_size_milli)
            if rations < instance.people:
                errors.append(f"Minimo diario de {group} incumplido el dia {day + 1}")

    protein_sources = {source for dish, _, _ in selected for source in dish.protein_sources}
    carb_sources = {source for dish, _, _ in selected for source in dish.carb_sources}
    fish_count = sum(1 for dish, _, _ in selected if dish.has_fish)
    legume_count = sum(1 for dish, _, _ in selected if dish.has_legumes)
    red_meat_count = sum(1 for dish, _, _ in selected if dish.has_red_meat)
    light_dinners = sum(1 for dish, _, slot in selected if slot == "dinner" and dish.is_light)
    thresholds = instance.thresholds
    if len(protein_sources) < thresholds.protein_sources:
        errors.append("Variedad de proteinas incumplida")
    if len(carb_sources) < thresholds.carb_sources:
        errors.append("Variedad de hidratos incumplida")
    if fish_count < thresholds.fish_dishes:
        errors.append("Pescado insuficiente")
    if legume_count < thresholds.legume_dishes:
        errors.append("Legumbres insuficientes")
    if red_meat_count > thresholds.red_meat_dishes:
        errors.append("Demasiada carne roja")
    if light_dinners < thresholds.light_dinners:
        errors.append("Cenas ligeras insuficientes")

    if stage1.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        errors.append(f"Etapa 1 sin solucion: {stage1.status_name}")
    if stage2.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        errors.append(f"Etapa 2 sin solucion: {stage2.status_name}")
    if stage1.objective != 0:
        errors.append(f"Violaciones de variedad: {stage1.objective}")
    if stage2.objective > instance.budget_cents:
        errors.append("La etapa 2 supera el presupuesto")
    return errors


def _run_once(
    instance: Instance,
    repetition: int,
) -> tuple[StageResult, StageResult, float, list[str]]:
    """Ejecuta las dos etapas y valida la solucion."""
    print()
    print(f"--- Repeticion {repetition} ---")

    started = time.perf_counter()
    model1, variables1 = _build_model(instance, fixed_violations=None, objective="violations")
    solver1, status1, name1 = _solve(model1, STAGE1_SECONDS)
    stage1 = _extract(solver1, status1, name1, variables1, solver1.WallTime())
    print(
        f"Etapa 1 (violaciones): {stage1.status_name} "
        f"objetivo={stage1.objective} tiempo={stage1.seconds:.2f} s"
    )
    if stage1.status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return stage1, stage1, time.perf_counter() - started, ["Etapa 1 sin solucion"]

    model2, variables2 = _build_model(
        instance, fixed_violations=stage1.objective, objective="ticket"
    )
    _apply_stage1_hint(model2, variables2, stage1)
    solver2, status2, name2 = _solve(model2, STAGE2_SECONDS)
    stage2 = _extract(solver2, status2, name2, variables2, solver2.WallTime())
    print(
        f"Etapa 2 (ticket): {stage2.status_name} "
        f"ticket={stage2.objective / 100:.2f} EUR tiempo={stage2.seconds:.2f} s"
    )

    elapsed = time.perf_counter() - started
    print(f"Total de la repeticion (construccion + solver): {elapsed:.2f} s")

    errors = _validate(instance, stage1, stage2)
    if errors:
        print("Validacion: FALLO")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Validacion: OK (28 huecos, demanda, minimos, variedad, presupuesto y bloqueos)")
    return stage1, stage2, elapsed, errors


def _check(label: str, passed: bool) -> bool:
    print(f"  [{'OK' if passed else 'FALLO'}] {label}")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Spike de OR-Tools CP-SAT (F0.6)")
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
        help="Numero de ejecuciones para medir estabilidad (por defecto 3)",
    )
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions debe ser >= 1")

    instance = _make_instance()
    print("=== Spike de OR-Tools CP-SAT (F0.6) ===")
    print(f"OR-Tools: {ortools.__version__}")
    print(f"Modelo: {instance.days} dias x {len(SLOTS)} huecos = {len(instance.slots)} huecos")
    print(
        f"Platos: {len(instance.dishes)} | Ingredientes: {len(instance.ingredients)} | "
        f"Productos: {instance.product_count}"
    )
    print(
        f"Personas: {instance.people} | Max. repeticiones por plato: {MAX_REPEATS} | "
        f"Solver: num_search_workers=1, seed={SOLVER_SEED}"
    )
    print(
        f"Presupuesto: {instance.budget_cents / 100:.2f} EUR | "
        f"Referencia: {instance.reference_ticket_cents / 100:.2f} EUR"
    )
    print(
        "Umbrales de variedad: "
        f"proteinas={instance.thresholds.protein_sources}, "
        f"pescado={instance.thresholds.fish_dishes}, "
        f"legumbres={instance.thresholds.legume_dishes}, "
        f"carne_roja={instance.thresholds.red_meat_dishes}, "
        f"cenas_ligeras={instance.thresholds.light_dinners}, "
        f"hidratos={instance.thresholds.carb_sources}"
    )

    stage1_results: list[StageResult] = []
    stage2_results: list[StageResult] = []
    elapsed_results: list[float] = []
    all_errors: list[str] = []
    for repetition in range(1, args.repetitions + 1):
        stage1, stage2, elapsed, errors = _run_once(instance, repetition)
        stage1_results.append(stage1)
        stage2_results.append(stage2)
        elapsed_results.append(elapsed)
        all_errors.extend(errors)

    max_elapsed = max(elapsed_results)
    all_stage1_optimal = all(stage.optimal for stage in stage1_results)
    all_stage2_optimal = all(stage.optimal for stage in stage2_results)
    tickets = [stage.objective for stage in stage2_results]
    print()
    print("--- Resumen ---")
    print(f"Repeticiones: {len(elapsed_results)}")
    print(f"Tiempo maximo por ejecucion: {max_elapsed:.2f} s")
    print(f"Tickets: {', '.join(f'{ticket / 100:.2f} EUR' for ticket in tickets)}")
    print(f"Etapa 1 optima probada: {'si' if all_stage1_optimal else 'no'}")
    print(f"Etapa 2 optima probada: {'si' if all_stage2_optimal else 'no'}")

    workers = {stage.num_search_workers for stage in (*stage1_results, *stage2_results)}
    checks = [
        (
            "Modelo con 28 huecos, 60 platos y 120 ingredientes",
            len(instance.slots) == 28
            and len(instance.dishes) == 60
            and len(instance.ingredients) == 120,
        ),
        ("Modelo con paquetes", instance.product_count > 0),
        ("num_search_workers=1", workers == {1}),
        ("Solucion valida en todas las repeticiones", not all_errors),
        (
            f"Toy resuelto en < {TOTAL_LIMIT_SECONDS:.0f} s",
            max_elapsed < TOTAL_LIMIT_SECONDS,
        ),
    ]
    print()
    print("--- Umbrales (F0.6) ---")
    passed = all(_check(label, condition) for label, condition in checks)
    print()
    print(f"Resultado: {'APTO' if passed else 'NO APTO'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
