"""Optimizador CP-SAT de menús: contrato público de F4.2-F4.4.

Este módulo trabaja con platos ya cargados y evaluados por
``EligibilityService``; no abre sesiones ni persiste nada. La salida contiene las
asignaciones, los paquetes del solver y el estado lexicográfico; la
materialización de la lista de la compra corresponde a ``MenuService`` (F4.5).

Reglas fijas:

- Un plato por hueco, compatible con ``lunch``/``dinner``.
- ``max_repeats`` y bloqueos duros.
- Un plato no puede aparecer dos veces el mismo día.
- Demanda por ingrediente con paquetes elegibles ``P_i`` y despensa.
- Presupuesto duro.
- Mínimos diarios por persona de verdura, proteína e hidrato.
- Etapa 1: minimizar violaciones de variedad; etapa 2: fijar la suma y
  minimizar el ticket.
- ``num_search_workers=1`` y semilla fija.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal, NoReturn

from ortools.sat.python import cp_model

from app.models.dishes import Dish
from app.models.ingredients import Ingredient
from app.services.eligibility import DishEligibility, PreferenceSnapshot
from app.services.pricing import (
    MAX_PEOPLE,
    ProductFormat,
    plan_purchase,
    purchasable_formats,
    scale_quantity,
)

OPTIMIZER_VERSION = "2"
STAGE1_SECONDS = 3.0
STAGE2_SECONDS = 3.0
FALLBACK_SECONDS = 2.0
SOLVER_SEED = 42

OptimizationStatus = Literal["optimal", "feasible", "relaxed", "infeasible", "timeout"]

_SLOTS: tuple[str, ...] = ("lunch", "dinner")
_SERVING_GROUPS: tuple[str, ...] = ("vegetable", "protein", "carb")
_RELAXATION_ORDER: tuple[str, ...] = (
    "protein_sources",
    "fish",
    "legumes",
    "red_meat",
    "light_dinners",
    "carb_sources",
    "legume_dominance",
    "protein_balance",
    "same_day_protein",
)
_RED_MEAT_SOURCES: frozenset[str] = frozenset({"beef", "pork"})
_LEGUME_SOURCES: frozenset[str] = frozenset({"legume", "legumes"})
_DIAGNOSTIC_SECONDS = 0.5
_MIN_SOLVE_SECONDS = 0.01

_SUGGESTIONS: tuple[str, ...] = (
    "Sube el presupuesto total para cubrir el mínimo estimado.",
    "Reduce los días o el número de personas del menú.",
    "Permite repetir platos para abaratar la compra.",
    "Añade despensa para descontar ingredientes que ya tienes.",
)


class OptimizerError(ValueError):
    """Error de dominio del optimizador con código estable."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        reason: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.reason = reason
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class OptimizationLock:
    """Plato fijado en un día y hueco."""

    day_index: int
    slot: str
    dish_id: int


@dataclass(frozen=True, slots=True)
class EligibilityReport:
    """Platos elegibles e ingredientes bloqueados que explican la solución."""

    eligible_dish_ids: tuple[int, ...]
    lunch_dish_ids: tuple[int, ...]
    dinner_dish_ids: tuple[int, ...]
    blocked_ingredient_ids: tuple[int, ...]
    dish_reasons: Mapping[int, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OptimizationRequest:
    """Entrada del optimizador, ya sin acceso a base de datos."""

    people: int
    days: int
    budget_cents: int
    preferences: PreferenceSnapshot
    pantry: Mapping[int, int] = field(default_factory=dict)
    max_repeats: int = 1
    locks: tuple[OptimizationLock, ...] = ()
    stage1_seconds: float = STAGE1_SECONDS
    stage2_seconds: float = STAGE2_SECONDS
    fallback_seconds: float = FALLBACK_SECONDS
    seed: int = SOLVER_SEED


@dataclass(frozen=True, slots=True)
class OptimizationAssignment:
    """Plato elegido para un día y hueco."""

    day_index: int
    slot: str
    dish_id: int
    dish_name: str
    protein_source: str | None = None
    locked: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Resultado completo de las dos etapas del solver."""

    status: OptimizationStatus
    is_preview: bool
    reason: str | None
    assignments: tuple[OptimizationAssignment, ...]
    packages: Mapping[int, int]
    solver_ticket_cents: int
    violations: int
    relaxation_codes: tuple[str, ...]
    timed_out: bool
    eligibility: EligibilityReport
    minimum_ticket_cents: int | None = None
    minimum_is_estimate: bool = False
    shortfall_cents: int = 0
    suggestions: tuple[str, ...] = ()
    elapsed_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class _ProductSpec:
    """Formato comprable ya validado por ``purchasable_formats``."""

    product_id: int
    package_quantity_milli: int
    package_price_cents: int


@dataclass(frozen=True, slots=True)
class _DishSpec:
    """Plato elegible con sus coeficientes y flags de variedad."""

    dish: Dish
    slots: frozenset[str]
    coef_by_ingredient: Mapping[int, int]
    group_rations: Mapping[str, int]
    estimated_cents: int
    protein_sources: frozenset[str]
    primary_protein: str | None
    carbs: str | None
    has_fish: bool
    has_legumes: bool
    has_red_meat: bool
    light: bool


@dataclass(frozen=True, slots=True)
class _PreparedProblem:
    """Entrada ya filtrada que comparten todas las variantes del modelo."""

    dishes: tuple[_DishSpec, ...]
    dishes_by_id: Mapping[int, _DishSpec]
    ingredients: Mapping[int, Ingredient]
    products_by_ingredient: Mapping[int, tuple[_ProductSpec, ...]]
    products: Mapping[int, _ProductSpec]


@dataclass(frozen=True, slots=True)
class _Violation:
    """Variable de violación de una regla de variedad."""

    code: str
    variable: cp_model.IntVar


@dataclass(slots=True)
class _BuiltModel:
    """Variables del modelo CP-SAT de una etapa."""

    model: cp_model.CpModel
    x: dict[tuple[int, str, int], cp_model.IntVar]
    q: dict[int, cp_model.IntVar]
    violations: tuple[_Violation, ...]
    total_violations: cp_model.LinearExpr | int


@dataclass(frozen=True, slots=True)
class _Solution:
    """Incumbente extraído del solver antes de materializar el resultado."""

    x: Mapping[tuple[int, str, int], int]
    packages: Mapping[int, int]
    violation_values: Mapping[str, int]
    violations: int
    ticket_cents: int


@dataclass(frozen=True, slots=True)
class _GreedyHint:
    """Menú determinista usado como pista inicial del solver."""

    x: Mapping[tuple[int, str, int], int]
    packages: Mapping[int, int]


@dataclass(frozen=True, slots=True)
class _SolveOutcome:
    """Solver y estado de una resolución."""

    solver: cp_model.CpSolver
    status: cp_model.CpSolverStatus

    @property
    def has_solution(self) -> bool:
        return self.status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    @property
    def optimal(self) -> bool:
        return self.status == cp_model.OPTIMAL


@dataclass(frozen=True, slots=True)
class _Diagnostic:
    """Variante relajada que explica una inviabilidad."""

    reason: str
    include_locks: bool = True
    include_minimums: bool = True
    max_repeats: int | None = None


def build_eligibility_report(eligibility: Sequence[DishEligibility]) -> EligibilityReport:
    """Resume qué platos pueden usarse y qué ingredientes están bloqueados."""
    eligible: set[int] = set()
    lunch: set[int] = set()
    dinner: set[int] = set()
    blocked: set[int] = set()
    dish_reasons: dict[int, tuple[str, ...]] = {}

    for result in eligibility:
        dish = result.dish
        blocked.update(result.blocked_ingredient_ids)
        if not result.eligible:
            dish_reasons[dish.id] = tuple(result.reasons)
            continue
        eligible.add(dish.id)
        slots = _dish_slots(dish)
        if "lunch" in slots:
            lunch.add(dish.id)
        if "dinner" in slots:
            dinner.add(dish.id)

    return EligibilityReport(
        eligible_dish_ids=tuple(sorted(eligible)),
        lunch_dish_ids=tuple(sorted(lunch)),
        dinner_dish_ids=tuple(sorted(dinner)),
        blocked_ingredient_ids=tuple(sorted(blocked)),
        dish_reasons=dish_reasons,
    )


def _usable_report(report: EligibilityReport, problem: _PreparedProblem) -> EligibilityReport:
    """Ajusta el informe a los platos que realmente tienen productos comprables."""
    usable = {spec.dish.id for spec in problem.dishes}
    lunch = {spec.dish.id for spec in problem.dishes if "lunch" in spec.slots}
    dinner = {spec.dish.id for spec in problem.dishes if "dinner" in spec.slots}
    reasons = dict(report.dish_reasons)
    for dish_id in report.eligible_dish_ids:
        if dish_id not in usable:
            reasons[dish_id] = ("no_purchasable_product",)
    return replace(
        report,
        eligible_dish_ids=tuple(sorted(usable)),
        lunch_dish_ids=tuple(sorted(lunch)),
        dinner_dish_ids=tuple(sorted(dinner)),
        dish_reasons=reasons,
    )


def time_limits_from_total(total_seconds: float) -> tuple[float, float, float]:
    """Reparte el presupuesto de tiempo: etapa 1, etapa 2 y fallback.

    Mantiene la proporción 3/3/2 s del contrato para que
    ``OPTIMIZER_TIME_LIMIT_SECONDS`` tenga efecto real en todos los caminos.
    """
    total = max(1.0, total_seconds)
    return (total * 0.375, total * 0.375, total * 0.25)


def optimize_menu(
    eligibility: Sequence[DishEligibility],
    request: OptimizationRequest,
) -> OptimizationResult:
    """Resuelve el menú en dos etapas lexicográficas.

    ``eligibility`` debe haberse evaluado con las mismas preferencias que
    ``request.preferences``; el optimizador no vuelve a consultar la base de
    datos. Devuelve ``infeasible`` solo cuando el presupuesto es la causa; en ese
    caso incluye un preview con el mínimo y el déficit. Las demás inviabilidades
    lanzan ``OptimizerError`` con ``code="NO_FEASIBLE_MENU"`` y ``reason``.
    """
    started = time.perf_counter()
    _validate_request(request)
    report = build_eligibility_report(eligibility)
    if not report.eligible_dish_ids:
        raise OptimizerError(
            "NO_ELIGIBLE_DISHES",
            "No hay platos elegibles con las preferencias actuales.",
            details={"dish_count": len(eligibility)},
        )

    problem = _prepare_problem(eligibility, request, report)
    report = _usable_report(report, problem)
    _validate_locks(problem, request)

    hint = _greedy_hint(problem, request)
    stage1_model = _build_model(problem, request, objective="violations")
    if hint is not None:
        _apply_greedy_hint(stage1_model, hint)
    stage1 = _solve(stage1_model.model, request.stage1_seconds, request.seed)

    if stage1.status == cp_model.INFEASIBLE:
        return _handle_infeasible(problem, request, report, started)

    if not stage1.has_solution:
        return _fallback_after_timeout(problem, request, report, started, hint)

    solution1 = _extract_solution(stage1.solver, stage1_model, problem)
    stage2_model = _build_model(
        problem,
        request,
        objective="ticket",
        fixed_violations=solution1.violations,
    )
    _apply_hint(stage2_model, solution1)
    stage2 = _solve(stage2_model.model, request.stage2_seconds, request.seed)

    if stage2.has_solution:
        chosen = _extract_solution(stage2.solver, stage2_model, problem)
        optimal = stage1.optimal and stage2.optimal
        timed_out = not optimal
    else:
        chosen = solution1
        optimal = False
        timed_out = True

    status = _status_for(chosen.violations, optimal)
    elapsed = time.perf_counter() - started
    return _result_from_solution(
        problem,
        request,
        report,
        chosen,
        status=status,
        timed_out=timed_out,
        elapsed=elapsed,
    )


def _validate_request(request: OptimizationRequest) -> None:
    if not 1 <= request.people <= MAX_PEOPLE:
        raise OptimizerError(
            "INVALID_INPUT",
            f"Las personas deben estar entre 1 y {MAX_PEOPLE}.",
            details={"people": request.people},
        )
    if request.days < 1 or request.days > 14:
        raise OptimizerError(
            "INVALID_INPUT",
            "Los días del menú deben estar entre 1 y 14.",
            details={"days": request.days},
        )
    if request.budget_cents < 0:
        raise OptimizerError(
            "INVALID_INPUT",
            "El presupuesto no puede ser negativo.",
            details={"budget_cents": request.budget_cents},
        )
    if request.max_repeats < 1:
        raise OptimizerError(
            "INVALID_INPUT",
            "Las repeticiones máximas deben ser al menos 1.",
            details={"max_repeats": request.max_repeats},
        )


def _dish_slots(dish: Dish) -> frozenset[str]:
    """Huecos compatibles; `both` se expande a comida y cena."""
    raw = set(dish.meal_types_json or ())
    slots = raw & set(_SLOTS)
    if "both" in raw:
        slots.update(_SLOTS)
    return frozenset(slots)


def _prepare_problem(
    eligibility: Sequence[DishEligibility],
    request: OptimizationRequest,
    report: EligibilityReport,
) -> _PreparedProblem:
    """Filtra platos y productos comprables exclusivamente desde ``P_i``."""
    eligible_ids = set(report.eligible_dish_ids)
    ingredients: dict[int, Ingredient] = {}
    products_by_ingredient: dict[int, dict[int, _ProductSpec]] = {}
    product_owner: dict[int, int] = {}
    specs: list[_DishSpec] = []

    for result in eligibility:
        if not result.eligible or result.dish.id not in eligible_ids:
            continue
        dish = result.dish
        # F6: el optimizador solo selecciona platos principales completos.
        if dish.role != "main":
            continue
        slots = _dish_slots(dish)
        if not slots:
            continue

        ingredient_results = {item.ingredient.id: item for item in result.ingredients}
        coef_by_ingredient: dict[int, int] = {}
        usable = True
        for link in dish.ingredients:
            ingredient_result = ingredient_results.get(link.ingredient_id)
            if ingredient_result is None:
                usable = False
                break
            ingredient = ingredient_result.ingredient
            allowed_products = {
                mapping.product.id for mapping in ingredient_result.eligible_products
            }
            ingredient_formats = purchasable_formats(ingredient, allowed_products)
            accepted = _accepted_formats(ingredient_formats, ingredient, product_owner)
            if not accepted:
                usable = False
                break
            ingredients[ingredient.id] = ingredient
            bucket = products_by_ingredient.setdefault(ingredient.id, {})
            for product in accepted:
                bucket[product.product_id] = product
                product_owner[product.product_id] = ingredient.id
            coef = scale_quantity(link.quantity_milli, request.people, dish.base_servings)
            if coef > 0:
                coef_by_ingredient[ingredient.id] = coef_by_ingredient.get(ingredient.id, 0) + coef
        if not usable:
            continue

        group_rations: dict[str, int] = {}
        estimated_cents = 0
        for ingredient_id, coef in coef_by_ingredient.items():
            ingredient = ingredients[ingredient_id]
            if ingredient.serving_group in _SERVING_GROUPS:
                ration_milli = (coef * 1_000_000) // ingredient.serving_size_milli
                if ration_milli > 0:
                    group_rations[ingredient.serving_group] = (
                        group_rations.get(ingredient.serving_group, 0) + ration_milli
                    )
            product_specs = products_by_ingredient.get(ingredient_id, {})
            if product_specs:
                estimated_cents += min(
                    (coef * product.package_price_cents) // product.package_quantity_milli
                    for product in product_specs.values()
                )

        protein_sources = frozenset(dish.protein_sources_json or ())
        primary_protein = dish.primary_protein or (
            min(protein_sources) if protein_sources else None
        )
        tags = frozenset(dish.tags_json or ())
        specs.append(
            _DishSpec(
                dish=dish,
                slots=slots,
                coef_by_ingredient=coef_by_ingredient,
                group_rations=group_rations,
                estimated_cents=estimated_cents,
                protein_sources=protein_sources,
                primary_protein=primary_protein,
                carbs=dish.carbs,
                has_fish="fish" in tags or "fish" in protein_sources,
                has_legumes="legume" in tags or "legumes" in protein_sources,
                has_red_meat="red_meat" in tags or bool(_RED_MEAT_SOURCES & protein_sources),
                light=dish.light,
            )
        )

    if not specs:
        raise OptimizerError(
            "NO_ELIGIBLE_DISHES",
            "No hay platos elegibles con productos comprables.",
            details={"eligible_dish_count": len(report.eligible_dish_ids)},
        )

    for slot in _SLOTS:
        if not any(slot in spec.slots for spec in specs):
            raise OptimizerError(
                "NO_FEASIBLE_MENU",
                "No hay platos elegibles compatibles con todos los huecos.",
                reason="no_assignment",
                details={"slot": slot},
            )

    frozen_products = {
        ingredient_id: tuple(
            product for _, product in sorted(bucket.items(), key=lambda item: item[0])
        )
        for ingredient_id, bucket in products_by_ingredient.items()
    }
    all_products = {
        product.product_id: product for products in frozen_products.values() for product in products
    }
    return _PreparedProblem(
        dishes=tuple(specs),
        dishes_by_id={spec.dish.id: spec for spec in specs},
        ingredients={
            ingredient_id: ingredients[ingredient_id] for ingredient_id in frozen_products
        },
        products_by_ingredient=frozen_products,
        products=all_products,
    )


def _accepted_formats(
    formats: Sequence[ProductFormat],
    ingredient: Ingredient,
    product_owner: Mapping[int, int],
) -> tuple[_ProductSpec, ...]:
    """Aplica de nuevo el filtro de compra y evita productos compartidos."""
    accepted: list[_ProductSpec] = []
    for product_format in formats:
        if product_format.package_unit != ingredient.base_unit:
            continue
        if product_format.package_quantity_milli <= 0:
            continue
        if product_format.package_price_cents <= 0:
            continue
        owner = product_owner.get(product_format.product_id)
        if owner is not None and owner != ingredient.id:
            continue
        accepted.append(
            _ProductSpec(
                product_id=product_format.product_id,
                package_quantity_milli=product_format.package_quantity_milli,
                package_price_cents=product_format.package_price_cents,
            )
        )
    return tuple(accepted)


def _validate_locks(problem: _PreparedProblem, request: OptimizationRequest) -> None:
    seen_slots: set[tuple[int, str]] = set()
    seen_day_dish: set[tuple[int, int]] = set()
    for lock in request.locks:
        dish = problem.dishes_by_id.get(lock.dish_id)
        invalid = (
            lock.slot not in _SLOTS
            or lock.day_index < 0
            or lock.day_index >= request.days
            or dish is None
            or lock.slot not in dish.slots
            or (lock.day_index, lock.slot) in seen_slots
            or (lock.day_index, lock.dish_id) in seen_day_dish
        )
        if invalid:
            raise OptimizerError(
                "NO_FEASIBLE_MENU",
                "Un plato bloqueado no puede colocarse en ese día y hueco.",
                reason="locks",
                details={
                    "day_index": lock.day_index,
                    "slot": lock.slot,
                    "dish_id": lock.dish_id,
                },
            )
        seen_slots.add((lock.day_index, lock.slot))
        seen_day_dish.add((lock.day_index, lock.dish_id))


def _build_model(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    *,
    objective: Literal["violations", "ticket"] | None,
    fixed_violations: int | None = None,
    max_repeats: int | None = None,
    include_locks: bool = True,
    include_minimums: bool = True,
    include_budget: bool = True,
) -> _BuiltModel:
    """Construye una variante del modelo CP-SAT."""
    model = cp_model.CpModel()
    effective_repeats = request.max_repeats if max_repeats is None else max_repeats
    repeat_factor = max(0, min(effective_repeats, request.days * 2))

    x: dict[tuple[int, str, int], cp_model.IntVar] = {}
    x_by_dish: dict[int, list[cp_model.IntVar]] = {spec.dish.id: [] for spec in problem.dishes}
    x_by_slot: dict[tuple[int, str], list[cp_model.IntVar]] = {}
    for day in range(request.days):
        for slot in _SLOTS:
            variables: list[cp_model.IntVar] = []
            for spec in problem.dishes:
                if slot not in spec.slots:
                    continue
                variable = model.new_bool_var(f"x_{spec.dish.id}_{day}_{slot}")
                x[(day, slot, spec.dish.id)] = variable
                variables.append(variable)
                x_by_dish[spec.dish.id].append(variable)
            x_by_slot[(day, slot)] = variables

    for variables in x_by_slot.values():
        model.add(sum(variables) == 1)

    for spec in problem.dishes:
        model.add(sum(x_by_dish[spec.dish.id]) <= effective_repeats)
        for day in range(request.days):
            day_variables = [
                x[(day, slot, spec.dish.id)] for slot in _SLOTS if (day, slot, spec.dish.id) in x
            ]
            if day_variables:
                model.add(sum(day_variables) <= 1)

    if include_locks:
        for lock in request.locks:
            model.add(x[(lock.day_index, lock.slot, lock.dish_id)] == 1)

    q: dict[int, cp_model.IntVar] = {}
    for ingredient_id in sorted(problem.products_by_ingredient):
        products = problem.products_by_ingredient[ingredient_id]
        max_need = (
            sum(spec.coef_by_ingredient.get(ingredient_id, 0) for spec in problem.dishes)
            * repeat_factor
        )
        for product in products:
            upper = _ceil_div(max_need, product.package_quantity_milli) if max_need > 0 else 0
            if include_budget:
                if product.package_price_cents > 0:
                    upper = min(upper, request.budget_cents // product.package_price_cents)
                else:
                    upper = 0
            q[product.product_id] = model.new_int_var(0, upper, f"q_{product.product_id}")

    for ingredient_id, products in problem.products_by_ingredient.items():
        demand_terms: list[cp_model.LinearExpr | int] = []
        for spec in problem.dishes:
            coef = spec.coef_by_ingredient.get(ingredient_id, 0)
            if coef <= 0:
                continue
            demand_terms.append(coef * sum(x_by_dish[spec.dish.id]))
        supply = sum(q[product.product_id] * product.package_quantity_milli for product in products)
        pantry = max(0, request.pantry.get(ingredient_id, 0))
        model.add(supply + pantry >= sum(demand_terms))

    ticket_expression = sum(
        q[product.product_id] * product.package_price_cents
        for products in problem.products_by_ingredient.values()
        for product in products
    )
    if include_budget:
        model.add(ticket_expression <= request.budget_cents)

    if include_minimums:
        _add_daily_minimums(model, problem, request, x)

    violations = _add_variety_rules(model, problem, request, x_by_dish, x)
    total_violations = sum(violation.variable for violation in violations)
    if fixed_violations is not None:
        model.add(total_violations == fixed_violations)

    if objective == "violations":
        model.minimize(total_violations)
    elif objective == "ticket":
        model.minimize(ticket_expression)

    return _BuiltModel(
        model=model,
        x=x,
        q=q,
        violations=violations,
        total_violations=total_violations,
    )


def _add_daily_minimums(
    model: cp_model.CpModel,
    problem: _PreparedProblem,
    request: OptimizationRequest,
    x: Mapping[tuple[int, str, int], cp_model.IntVar],
) -> None:
    """Una ración diaria por persona de verdura, proteína e hidrato."""
    for day in range(request.days):
        for group in _SERVING_GROUPS:
            terms: list[cp_model.LinearExpr] = []
            for spec in problem.dishes:
                for slot in _SLOTS:
                    variable = x.get((day, slot, spec.dish.id))
                    if variable is None:
                        continue
                    for ingredient_id, coef in spec.coef_by_ingredient.items():
                        ingredient = problem.ingredients[ingredient_id]
                        if ingredient.serving_group != group:
                            continue
                        ration_milli = (coef * 1_000_000) // ingredient.serving_size_milli
                        if ration_milli > 0:
                            terms.append(ration_milli * variable)
            model.add(sum(terms) >= request.people * 1_000_000)


def _add_variety_rules(
    model: cp_model.CpModel,
    problem: _PreparedProblem,
    request: OptimizationRequest,
    x_by_dish: Mapping[int, Sequence[cp_model.IntVar]],
    x: Mapping[tuple[int, str, int], cp_model.IntVar],
) -> tuple[_Violation, ...]:
    """Añade las violaciones de PLAN §6.6 con peso 1."""
    violations: list[_Violation] = []
    total_slots = request.days * 2

    protein_sources = sorted({source for spec in problem.dishes for source in spec.protein_sources})
    protein_presence: list[cp_model.IntVar] = []
    for source in protein_sources:
        variables = [
            variable
            for spec in problem.dishes
            if source in spec.protein_sources
            for variable in x_by_dish[spec.dish.id]
        ]
        if not variables:
            continue
        presence = model.new_bool_var(f"protein_{_safe_name(source)}")
        for variable in variables:
            model.add(presence >= variable)
        model.add(presence <= sum(variables))
        protein_presence.append(presence)
    violations.append(
        _lower_violation(
            model,
            "protein_sources",
            min(3, request.days),
            sum(protein_presence),
        )
    )

    fish_variables = [
        variable for spec in problem.dishes if spec.has_fish for variable in x_by_dish[spec.dish.id]
    ]
    violations.append(
        _lower_violation(
            model,
            "fish",
            max(1, _ceil_div(request.days * 2, 7)),
            sum(fish_variables),
        )
    )

    legume_variables = [
        variable
        for spec in problem.dishes
        if spec.has_legumes
        for variable in x_by_dish[spec.dish.id]
    ]
    violations.append(
        _lower_violation(
            model,
            "legumes",
            _ceil_div(request.days, 7),
            sum(legume_variables),
        )
    )

    red_meat_variables = [
        variable
        for spec in problem.dishes
        if spec.has_red_meat
        for variable in x_by_dish[spec.dish.id]
    ]
    violations.append(
        _upper_violation(
            model,
            "red_meat",
            _ceil_div(request.days * 3, 7),
            sum(red_meat_variables),
            total_slots,
        )
    )

    light_variables = [
        x[(day, "dinner", spec.dish.id)]
        for day in range(request.days)
        for spec in problem.dishes
        if spec.light and (day, "dinner", spec.dish.id) in x
    ]
    violations.append(
        _lower_violation(
            model,
            "light_dinners",
            _ceil_div(request.days, 2),
            sum(light_variables),
        )
    )

    carb_sources = sorted({spec.carbs for spec in problem.dishes if spec.carbs is not None})
    carb_presence: list[cp_model.IntVar] = []
    for source in carb_sources:
        variables = [
            variable
            for spec in problem.dishes
            if spec.carbs == source
            for variable in x_by_dish[spec.dish.id]
        ]
        if not variables:
            continue
        presence = model.new_bool_var(f"carb_{_safe_name(source)}")
        for variable in variables:
            model.add(presence >= variable)
        model.add(presence <= sum(variables))
        carb_presence.append(presence)
    violations.append(
        _lower_violation(
            model,
            "carb_sources",
            min(2, request.days),
            sum(carb_presence),
        )
    )

    primary_sources = sorted(
        {spec.primary_protein for spec in problem.dishes if spec.primary_protein is not None}
    )
    cap = max(2, _ceil_div(total_slots, min(len(primary_sources), 5))) if primary_sources else 0
    legume_groups: dict[str, list[cp_model.IntVar]] = {}
    other_groups: dict[str, list[cp_model.IntVar]] = {}
    for source in primary_sources:
        variables = [
            variable
            for spec in problem.dishes
            if spec.primary_protein == source
            for variable in x_by_dish[spec.dish.id]
        ]
        if source in _LEGUME_SOURCES:
            legume_groups[source] = variables
        else:
            other_groups[source] = variables
    violations.append(
        _group_cap_violation(
            model,
            "legume_dominance",
            cap,
            legume_groups,
            total_slots,
        )
    )
    violations.append(
        _group_cap_violation(
            model,
            "protein_balance",
            cap,
            other_groups,
            total_slots,
        )
    )

    same_day_terms: list[cp_model.IntVar] = []
    for day in range(request.days):
        for source in primary_sources:
            variables = [
                variable
                for spec in problem.dishes
                if spec.primary_protein == source
                for variable in (x.get((day, slot, spec.dish.id)) for slot in _SLOTS)
                if variable is not None
            ]
            if len(variables) < 2:
                continue
            excess = model.new_int_var(
                0,
                1,
                f"same_day_{day}_{_safe_name(source)}",
            )
            model.add(excess >= sum(variables) - 1)
            same_day_terms.append(excess)
    same_day = model.new_int_var(0, request.days, "violation_same_day_protein")
    model.add(same_day == sum(same_day_terms))
    violations.append(_Violation(code="same_day_protein", variable=same_day))

    ordered = {violation.code: violation for violation in violations}
    return tuple(ordered[code] for code in _RELAXATION_ORDER)


def _lower_violation(
    model: cp_model.CpModel,
    code: str,
    threshold: int,
    expression: cp_model.LinearExpr | int,
) -> _Violation:
    variable = model.new_int_var(0, max(0, threshold), f"violation_{code}")
    model.add(variable >= threshold - expression)
    return _Violation(code=code, variable=variable)


def _upper_violation(
    model: cp_model.CpModel,
    code: str,
    threshold: int,
    expression: cp_model.LinearExpr | int,
    max_count: int,
) -> _Violation:
    variable = model.new_int_var(0, max(0, max_count), f"violation_{code}")
    model.add(variable >= expression - threshold)
    return _Violation(code=code, variable=variable)


def _group_cap_violation(
    model: cp_model.CpModel,
    code: str,
    cap: int,
    groups: Mapping[str, Sequence[cp_model.IntVar]],
    max_count: int,
) -> _Violation:
    """Suma el exceso de varios grupos de platos sobre un tope blando por fuente."""
    excess_terms: list[cp_model.IntVar] = []
    for source, variables in sorted(groups.items()):
        if not variables:
            continue
        excess = model.new_int_var(
            0,
            max_count,
            f"excess_{code}_{_safe_name(source)}",
        )
        model.add(excess >= sum(variables) - cap)
        excess_terms.append(excess)
    variable = model.new_int_var(0, max_count, f"violation_{code}")
    model.add(variable == sum(excess_terms))
    return _Violation(code=code, variable=variable)


def _solve(model: cp_model.CpModel, seconds: float, seed: int) -> _SolveOutcome:
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = max(_MIN_SOLVE_SECONDS, seconds)
    solver.parameters.log_search_progress = False
    status = solver.solve(model)
    return _SolveOutcome(solver=solver, status=status)


def _apply_hint(model: _BuiltModel, solution: _Solution) -> None:
    """Usa el incumbente de la etapa 1 como pista de la etapa 2."""
    for key, variable in model.x.items():
        model.model.add_hint(variable, solution.x.get(key, 0))
    for product_id, variable in model.q.items():
        model.model.add_hint(variable, solution.packages.get(product_id, 0))


def _apply_greedy_hint(model: _BuiltModel, hint: _GreedyHint) -> None:
    """Usa el menú greedy como pista de la etapa 1."""
    for key, variable in model.x.items():
        model.model.add_hint(variable, hint.x.get(key, 0))
    for product_id, variable in model.q.items():
        model.model.add_hint(variable, hint.packages.get(product_id, 0))


def _greedy_hint(problem: _PreparedProblem, request: OptimizationRequest) -> _GreedyHint | None:
    """Construye un menú barato y determinista que cumple mínimos y presupuesto.

    No sustituye al solver: solo le da un incumbente inicial para que los
    presupuestos ajustados no empiecen desde ``q=0``. Para cada día enumera las
    parejas de platos compatibles y se queda con la más barata que cubre los
    mínimos diarios; después valora la compra con ``plan_purchase``. Si no hay
    ninguna combinación válida o no cabe en el presupuesto, devuelve ``None``.
    """
    minimum_rations = request.people * 1_000_000
    selected: dict[tuple[int, str], _DishSpec] = {
        (lock.day_index, lock.slot): problem.dishes_by_id[lock.dish_id] for lock in request.locks
    }
    used_count: dict[int, int] = {}
    for spec in selected.values():
        used_count[spec.dish.id] = used_count.get(spec.dish.id, 0) + 1
        if used_count[spec.dish.id] > request.max_repeats:
            return None

    for day in range(request.days):
        locked_today = {
            slot: spec for (selected_day, slot), spec in selected.items() if selected_day == day
        }
        rations = {group: 0 for group in _SERVING_GROUPS}
        for spec in locked_today.values():
            for group, value in spec.group_rations.items():
                rations[group] += value
        used_today = {spec.dish.id for spec in locked_today.values()}

        unlocked_slots = [slot for slot in _SLOTS if slot not in locked_today]
        candidates_by_slot: dict[str, list[_DishSpec]] = {}
        for slot in unlocked_slots:
            candidates = [
                spec
                for spec in problem.dishes
                if slot in spec.slots
                and spec.dish.id not in used_today
                and used_count.get(spec.dish.id, 0) < request.max_repeats
            ]
            if not candidates:
                return None
            candidates_by_slot[slot] = candidates

        combos: list[tuple[_DishSpec, ...]]
        if not unlocked_slots:
            combos = [()]
        elif len(unlocked_slots) == 1:
            combos = [(spec,) for spec in candidates_by_slot[unlocked_slots[0]]]
        else:
            first, second = unlocked_slots
            combos = [
                (first_spec, second_spec)
                for first_spec in candidates_by_slot[first]
                for second_spec in candidates_by_slot[second]
                if first_spec.dish.id != second_spec.dish.id
            ]

        best_combo: tuple[_DishSpec, ...] | None = None
        best_score: tuple[int, tuple[int, ...]] | None = None
        for combo in combos:
            day_rations = dict(rations)
            for spec in combo:
                for group, value in spec.group_rations.items():
                    day_rations[group] = day_rations.get(group, 0) + value
            if any(day_rations[group] < minimum_rations for group in _SERVING_GROUPS):
                continue
            score = (
                sum(spec.estimated_cents for spec in combo),
                tuple(spec.dish.id for spec in combo),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_combo = combo

        if best_combo is None:
            return None
        for slot, spec in zip(unlocked_slots, best_combo, strict=True):
            selected[(day, slot)] = spec
            used_count[spec.dish.id] = used_count.get(spec.dish.id, 0) + 1

    needs: dict[int, int] = {}
    for spec in selected.values():
        for ingredient_id, coef in spec.coef_by_ingredient.items():
            needs[ingredient_id] = needs.get(ingredient_id, 0) + coef

    packages: dict[int, int] = {}
    ticket_cents = 0
    for ingredient_id, need in needs.items():
        net_need = max(0, need - max(0, request.pantry.get(ingredient_id, 0)))
        if net_need == 0:
            continue
        ingredient = problem.ingredients[ingredient_id]
        allowed = {product.product_id for product in problem.products_by_ingredient[ingredient_id]}
        formats = purchasable_formats(ingredient, allowed)
        if not formats:
            return None
        plan = plan_purchase(ingredient, net_need, formats)
        ticket_cents += plan.ticket_cents
        for line in plan.lines:
            product_id = line.product.product_id
            packages[product_id] = packages.get(product_id, 0) + line.packages

    if ticket_cents > request.budget_cents:
        # La pista de asignaciones sigue siendo útil aunque el plan canónico de
        # este menú greedy no quepa: el solver puede reparar la selección y la
        # compra. No se hintan paquetes que violarían el presupuesto.
        return _GreedyHint(
            x={(day, slot, spec.dish.id): 1 for (day, slot), spec in selected.items()},
            packages={},
        )

    x = {(day, slot, spec.dish.id): 1 for (day, slot), spec in selected.items()}
    return _GreedyHint(x=x, packages=packages)


def _extract_solution(
    solver: cp_model.CpSolver,
    model: _BuiltModel,
    problem: _PreparedProblem,
) -> _Solution:
    x_values = {key: solver.value(variable) for key, variable in model.x.items()}
    q_values = {product_id: solver.value(variable) for product_id, variable in model.q.items()}
    violation_values = {
        violation.code: solver.value(violation.variable) for violation in model.violations
    }
    ticket = sum(
        count * problem.products[product_id].package_price_cents
        for product_id, count in q_values.items()
    )
    return _Solution(
        x=x_values,
        packages=q_values,
        violation_values=violation_values,
        violations=sum(violation_values.values()),
        ticket_cents=ticket,
    )


def _handle_infeasible(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    report: EligibilityReport,
    started: float,
) -> OptimizationResult:
    """Diagnostica la inviabilidad; solo el presupuesto genera preview."""
    short_limit = max(_MIN_SOLVE_SECONDS, min(1.0, request.fallback_seconds))

    if request.locks:
        without_locks = _build_model(
            problem,
            request,
            objective=None,
            include_locks=False,
        )
        outcome = _solve(without_locks.model, short_limit, request.seed)
        if outcome.has_solution:
            _raise_no_feasible_menu("locks", "Los platos bloqueados no caben en el menú.")

    if request.max_repeats == 1:
        relaxed_repeats = _build_model(
            problem,
            request,
            objective=None,
            max_repeats=request.days * 2,
        )
        outcome = _solve(relaxed_repeats.model, short_limit, request.seed)
        if outcome.has_solution:
            _raise_no_feasible_menu(
                "repeats",
                "No hay platos suficientes para cubrir el menú sin repetir.",
            )

    fallback_model = _build_model(
        problem,
        request,
        objective="ticket",
        include_budget=False,
    )
    fallback = _solve(fallback_model.model, request.fallback_seconds, request.seed)
    if fallback.has_solution:
        solution = _extract_solution(fallback.solver, fallback_model, problem)
        elapsed = time.perf_counter() - started
        return _infeasible_result(
            problem,
            request,
            report,
            solution,
            best_possible=fallback.optimal,
            elapsed=elapsed,
        )

    _diagnose_without_budget(problem, request)
    _raise_no_feasible_menu(
        "no_assignment",
        "No hay ninguna combinación de platos que cumpla las restricciones.",
    )


def _diagnose_without_budget(
    problem: _PreparedProblem,
    request: OptimizationRequest,
) -> None:
    """Solves cortos sin presupuesto para explicar la inviabilidad."""
    diagnostics: list[_Diagnostic] = []
    if request.locks:
        diagnostics.append(_Diagnostic("locks", include_locks=False))
    diagnostics.append(_Diagnostic("minimums", include_minimums=False))
    if request.max_repeats < request.days * 2:
        diagnostics.append(_Diagnostic("repeats", max_repeats=request.days * 2))

    for diagnostic in diagnostics:
        diagnostic_model = _build_model(
            problem,
            request,
            objective=None,
            include_budget=False,
            include_locks=diagnostic.include_locks,
            include_minimums=diagnostic.include_minimums,
            max_repeats=diagnostic.max_repeats,
        )
        outcome = _solve(diagnostic_model.model, _DIAGNOSTIC_SECONDS, request.seed)
        if outcome.has_solution:
            _raise_no_feasible_menu(diagnostic.reason, _DIAGNOSTIC_MESSAGES[diagnostic.reason])


_DIAGNOSTIC_MESSAGES: Mapping[str, str] = {
    "locks": "Los platos bloqueados no caben en el menú.",
    "minimums": "Los mínimos diarios de verdura, proteína o hidrato no se pueden cumplir.",
    "repeats": "No hay platos suficientes para cubrir el menú sin repetir.",
    "no_assignment": "No hay ninguna combinación de platos que cumpla las restricciones.",
}


def _raise_no_feasible_menu(reason: str, message: str) -> NoReturn:
    raise OptimizerError(
        "NO_FEASIBLE_MENU",
        message,
        reason=reason,
        details={"reason": reason},
    )


def _fallback_after_timeout(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    report: EligibilityReport,
    started: float,
    hint: _GreedyHint | None,
) -> OptimizationResult:
    """Intenta devolver un menú válido cuando la etapa 1 agota el tiempo.

    El modelo sin presupuesto minimiza el ticket del solver. Si su plan canónico
    cabe en el presupuesto, el menú es válido y se devuelve como ``feasible`` o
    ``relaxed``; si no cabe, no se puede afirmar que el presupuesto sea
    inviable, así que se mantiene ``timeout``.
    """
    fallback_model = _build_model(
        problem,
        request,
        objective="ticket",
        include_budget=False,
    )
    if hint is not None:
        _apply_greedy_hint(fallback_model, hint)
    fallback = _solve(fallback_model.model, request.fallback_seconds, request.seed)
    if not fallback.has_solution:
        return _timeout_result(report, started)

    solution = _extract_solution(fallback.solver, fallback_model, problem)
    canonical_packages, canonical_ticket = _canonical_plan(problem, request, solution)
    if canonical_ticket > request.budget_cents:
        return _timeout_result(report, started)

    result = _result_from_solution(
        problem,
        request,
        report,
        solution,
        status=_status_for(solution.violations, optimal=False),
        timed_out=True,
        elapsed=time.perf_counter() - started,
    )
    return replace(
        result,
        packages=canonical_packages,
        solver_ticket_cents=canonical_ticket,
    )


def _timeout_result(report: EligibilityReport, started: float) -> OptimizationResult:
    return OptimizationResult(
        status="timeout",
        is_preview=False,
        reason=None,
        assignments=(),
        packages={},
        solver_ticket_cents=0,
        violations=0,
        relaxation_codes=(),
        timed_out=True,
        eligibility=report,
        elapsed_seconds=time.perf_counter() - started,
    )


def _status_for(violations: int, optimal: bool) -> OptimizationStatus:
    if violations > 0:
        return "relaxed"
    return "optimal" if optimal else "feasible"


def _result_from_solution(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    report: EligibilityReport,
    solution: _Solution,
    *,
    status: OptimizationStatus,
    timed_out: bool,
    elapsed: float,
    minimum_ticket_cents: int | None = None,
    minimum_is_estimate: bool = False,
    shortfall_cents: int = 0,
    suggestions: tuple[str, ...] = (),
) -> OptimizationResult:
    locked_keys = {(lock.day_index, lock.slot, lock.dish_id) for lock in request.locks}
    selected = sorted(
        (key for key, value in solution.x.items() if value == 1),
        key=lambda key: (key[0], _SLOTS.index(key[1]), key[2]),
    )
    assignments: list[OptimizationAssignment] = []
    for day, slot, dish_id in selected:
        spec = problem.dishes_by_id[dish_id]
        protein_source = spec.primary_protein or (
            min(spec.protein_sources) if spec.protein_sources else None
        )
        assignments.append(
            OptimizationAssignment(
                day_index=day,
                slot=slot,
                dish_id=dish_id,
                dish_name=spec.dish.name,
                protein_source=protein_source,
                locked=(day, slot, dish_id) in locked_keys,
            )
        )

    return OptimizationResult(
        status=status,
        is_preview=status == "infeasible",
        reason="budget" if status == "infeasible" else None,
        assignments=tuple(assignments),
        packages={
            product_id: count for product_id, count in solution.packages.items() if count > 0
        },
        solver_ticket_cents=solution.ticket_cents,
        violations=solution.violations,
        relaxation_codes=tuple(
            code for code in _RELAXATION_ORDER if solution.violation_values.get(code, 0) > 0
        ),
        timed_out=timed_out,
        eligibility=report,
        minimum_ticket_cents=minimum_ticket_cents,
        minimum_is_estimate=minimum_is_estimate,
        shortfall_cents=shortfall_cents,
        suggestions=suggestions,
        elapsed_seconds=elapsed,
    )


def _infeasible_result(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    report: EligibilityReport,
    solution: _Solution,
    *,
    best_possible: bool,
    elapsed: float,
) -> OptimizationResult:
    canonical_packages, canonical_ticket = _canonical_plan(problem, request, solution)
    result = _result_from_solution(
        problem,
        request,
        report,
        solution,
        status="infeasible",
        timed_out=False,
        elapsed=elapsed,
        minimum_ticket_cents=canonical_ticket,
        minimum_is_estimate=not best_possible,
        shortfall_cents=max(0, canonical_ticket - request.budget_cents),
        suggestions=_SUGGESTIONS,
    )
    return replace(
        result,
        packages=canonical_packages,
        solver_ticket_cents=canonical_ticket,
    )


def _canonical_plan(
    problem: _PreparedProblem,
    request: OptimizationRequest,
    solution: _Solution,
) -> tuple[Mapping[int, int], int]:
    """Ticket canónico del menú preview, usando `plan_purchase` sobre la demanda.

    El fallback sin presupuesto puede devolver `q` no óptimas (o un incumbente
    parcial). El mínimo que se muestra al usuario debe ser el coste real del
    menú preview con el plan canónico, no el ticket de esas `q`.
    """
    needs: dict[int, int] = {}
    for (_, _, dish_id), selected in solution.x.items():
        if not selected:
            continue
        spec = problem.dishes_by_id[dish_id]
        for ingredient_id, coef in spec.coef_by_ingredient.items():
            needs[ingredient_id] = needs.get(ingredient_id, 0) + coef

    packages: dict[int, int] = {}
    ticket_cents = 0
    for ingredient_id, need in needs.items():
        net_need = max(0, need - max(0, request.pantry.get(ingredient_id, 0)))
        if net_need == 0:
            continue
        ingredient = problem.ingredients[ingredient_id]
        allowed = {product.product_id for product in problem.products_by_ingredient[ingredient_id]}
        formats = purchasable_formats(ingredient, allowed)
        plan = plan_purchase(ingredient, net_need, formats)
        ticket_cents += plan.ticket_cents
        for line in plan.lines:
            product_id = line.product.product_id
            packages[product_id] = packages.get(product_id, 0) + line.packages
    return packages, ticket_cents


def _ceil_div(dividend: int, divisor: int) -> int:
    return -(-dividend // divisor)


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)
