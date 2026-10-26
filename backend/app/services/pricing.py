"""Motor de costes puro del presupuesto (F3).

El coste se calcula con dos métricas separadas:

- **Consumo**: valor de la cantidad usada, incluida la despensa.
- **Ticket**: paquetes cerrados que hay que comprar.

La identidad obligatoria es ``ticket + pantry_consumption = consumption + leftover``.
Para garantizarla con enteros, cada ingrediente redondea su consumo una sola vez al
final y el valor de las sobras se calcula como el residuo exacto del ticket.

``plan_purchase`` es la función canónica de compra: minimiza el coste total y,
a igual coste, prefiere menos paquetes y un ``product_id`` estable. F3 y F4
comparten esta función para que el preview y la lista de la compra den
exactamente el mismo ticket.

Todas las cantidades están en milésimas de la unidad base del ingrediente (mg, µl
o mili-unidades) y todos los importes en céntimos enteros. No se usa ``float``
para dinero.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from itertools import product as cartesian_product
from math import gcd
from typing import Any

from app.models.dishes import Dish
from app.models.ingredients import Ingredient

#: Límite de personas del MVP (`PLAN.md` §2.1).
MAX_PEOPLE = 10

#: Por encima de este número de combinaciones se usa programación dinámica.
_MAX_ENUMERATION = 50_000

#: Tope de estados de la programación dinámica de respaldo.
_MAX_DP_TARGET = 2_000_000

_CENT = Decimal("1")


class PricingError(ValueError):
    """Error de dominio del motor de costes con código estable."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class ProductFormat:
    """Formato comprable de un producto, normalizado a la unidad base."""

    product_id: int
    external_id: str
    name: str
    package_quantity_milli: int
    package_unit: str
    package_price_cents: int
    reference_price_cents: int | None
    reference_unit: str | None
    is_default: bool
    priority: int

    @property
    def unit_cost(self) -> Decimal:
        """Coste en céntimos por milésima de unidad base."""
        return Decimal(self.package_price_cents) / Decimal(self.package_quantity_milli)


@dataclass(frozen=True, slots=True)
class PurchaseLine:
    """Un formato comprado dentro de un plan."""

    product: ProductFormat
    packages: int
    quantity_milli: int
    subtotal_cents: int
    used_milli: int = 0
    leftover_milli: int = 0


@dataclass(frozen=True, slots=True)
class PurchasePlan:
    """Plan canónico de compra de un ingrediente."""

    ingredient_id: int
    net_need_milli: int
    lines: tuple[PurchaseLine, ...]
    purchased_milli: int
    ticket_cents: int


@dataclass(frozen=True, slots=True)
class IngredientCost:
    """Coste, consumo y sobras de un ingrediente."""

    ingredient: Ingredient
    need_milli: int
    pantry_milli: int
    pantry_used_milli: int
    net_need_milli: int
    purchased_milli: int
    leftover_milli: int
    ticket_cents: int
    consumption_cents: int
    pantry_consumption_cents: int
    leftover_value_cents: int
    lines: tuple[PurchaseLine, ...]


@dataclass(frozen=True, slots=True)
class DishCost:
    """Coste de una aparición concreta de un plato en el menú."""

    index: int
    dish: Dish
    servings: int
    consumption_cents: int
    per_serving_cents: int


@dataclass(frozen=True, slots=True)
class BasketCost:
    """Resultado completo del cálculo de coste de un conjunto de platos."""

    people: int
    ingredients: tuple[IngredientCost, ...]
    dishes: tuple[DishCost, ...]
    ticket_cents: int
    consumption_cents: int
    pantry_consumption_cents: int
    leftover_value_cents: int

    @property
    def dish_count(self) -> int:
        return len(self.dishes)


def _round_half_up(value: Decimal) -> int:
    """Redondea a céntimos enteros una sola vez, al final."""
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _ceil_div(dividend: int, divisor: int) -> int:
    return -(-dividend // divisor)


def scale_quantity(quantity_milli: int, people: int, base_servings: int) -> int:
    """Escala la cantidad de un plato a las personas reales.

    ``coef = round(quantity_milli × people / base_servings)``. El redondeo se
    aplica por plato antes de multiplicar por sus apariciones en el menú. Una
    cantidad positiva puede redondear a cero si la ración es muy pequeña.
    """
    if quantity_milli < 0:
        raise PricingError("INVALID_INPUT", "La cantidad del ingrediente no puede ser negativa.")
    if people < 1 or people > MAX_PEOPLE:
        raise PricingError(
            "INVALID_INPUT",
            f"Las personas deben estar entre 1 y {MAX_PEOPLE}.",
        )
    if base_servings < 1:
        raise PricingError("INVALID_INPUT", "Las raciones base del plato deben ser positivas.")
    exact = Decimal(quantity_milli) * Decimal(people) / Decimal(base_servings)
    return _round_half_up(exact)


def scale_dish(dish: Dish, people: int) -> dict[int, int]:
    """Necesidad por ingrediente de una aparición del plato."""
    needs: dict[int, int] = {}
    for link in dish.ingredients:
        quantity = scale_quantity(link.quantity_milli, people, dish.base_servings)
        if quantity > 0:
            needs[link.ingredient_id] = needs.get(link.ingredient_id, 0) + quantity
    return needs


def purchasable_formats(
    ingredient: Ingredient,
    allowed_product_ids: Collection[int] | None = None,
) -> tuple[ProductFormat, ...]:
    """Formatos que pueden comprarse para el ingrediente, ordenados por coste.

    Se exige que el producto esté publicado, tenga precio y cantidad de paquete,
    sea de formato fijo y use la misma unidad base que el ingrediente (F3.1). La
    elegibilidad por alérgenos no se aplica aquí: el preview es de coste. F4
    puede pasar ``allowed_product_ids`` con los productos de ``P_i`` para no
    comprar nunca un producto excluido por alérgenos o disponibilidad.
    """
    formats: list[ProductFormat] = []
    for mapping in ingredient.products:
        product = mapping.product
        if allowed_product_ids is not None and product.id not in allowed_product_ids:
            continue
        if not product.published:
            continue
        if (
            product.package_quantity_milli is None
            or product.package_quantity_milli <= 0
            or product.package_price_cents is None
            or product.package_price_cents <= 0
        ):
            continue
        if product.package_unit != ingredient.base_unit:
            continue
        if product.approx_size or (product.selling_method or 0) != 0:
            continue
        formats.append(
            ProductFormat(
                product_id=product.id,
                external_id=product.external_id,
                name=product.name,
                package_quantity_milli=product.package_quantity_milli,
                package_unit=product.package_unit,
                package_price_cents=product.package_price_cents,
                reference_price_cents=product.reference_price_cents,
                reference_unit=product.reference_unit,
                is_default=mapping.is_default,
                priority=mapping.priority,
            )
        )
    return tuple(sorted(formats, key=_format_order))


def _format_order(fmt: ProductFormat) -> tuple[Decimal, int, int]:
    """Coste unitario ascendente; a igual coste, formato grande y producto estable."""
    return (fmt.unit_cost, -fmt.package_quantity_milli, fmt.product_id)


def _require_formats(
    ingredient: Ingredient,
    formats: Sequence[ProductFormat] | None = None,
) -> tuple[ProductFormat, ...]:
    resolved = tuple(formats) if formats is not None else purchasable_formats(ingredient)
    if not resolved:
        raise PricingError(
            "PRODUCT_UNAVAILABLE",
            f"No hay un producto comprable para «{ingredient.name}».",
            details={"ingredient_id": ingredient.id, "ingredient_name": ingredient.name},
        )
    return resolved


def _score(
    formats: Sequence[ProductFormat], counts: Sequence[int]
) -> tuple[int, int, tuple[tuple[int, int], ...]]:
    """Orden de preferencia: coste, paquetes y producto estable."""
    cost = sum(count * fmt.package_price_cents for count, fmt in zip(counts, formats, strict=True))
    packages = sum(counts)
    stable = tuple(
        sorted(
            (fmt.product_id, count) for count, fmt in zip(counts, formats, strict=True) if count > 0
        )
    )
    return (cost, packages, stable)


def _enumerate_counts(
    formats: Sequence[ProductFormat], target: int, bounds: Sequence[int]
) -> tuple[int, ...]:
    """Enumera los formatos no óptimos y completa con el de mejor coste unitario."""
    best_format = formats[0]
    others = formats[1:]
    best_counts: tuple[int, ...] | None = None
    best_score: tuple[int, int, tuple[tuple[int, int], ...]] | None = None
    for combination in cartesian_product(*(range(bound) for bound in bounds)):
        covered = sum(
            count * fmt.package_quantity_milli
            for count, fmt in zip(combination, others, strict=True)
        )
        remaining = target - covered
        best_quantity = (
            _ceil_div(remaining, best_format.package_quantity_milli) if remaining > 0 else 0
        )
        counts = (best_quantity, *combination)
        score = _score(formats, counts)
        if best_score is None or score < best_score:
            best_score = score
            best_counts = counts
    if best_counts is None:  # pragma: no cover - la enumeración nunca está vacía
        raise PricingError("PRICING_INCONSISTENT", "No se pudo construir el plan de compra.")
    return best_counts


def _dynamic_program_counts(formats: Sequence[ProductFormat], target: int) -> tuple[int, ...]:
    """Respaldo exacto para formatos con cocientes muy grandes.

    Trabaja sobre el máximo común divisor de los tamaños para reducir el número
    de estados. Solo se usa en catálogos patológicos; los formatos reales
    resuelven por enumeración.
    """
    factor = 0
    for fmt in formats:
        factor = gcd(factor, fmt.package_quantity_milli)
    scaled_target = _ceil_div(target, factor)
    if scaled_target > _MAX_DP_TARGET:  # pragma: no cover - requiere cantidades absurdas
        raise PricingError(
            "PRICING_TOO_COMPLEX",
            "La compra de este ingrediente es demasiado grande para calcularse.",
        )

    sizes = [fmt.package_quantity_milli // factor for fmt in formats]
    costs = [0] * (scaled_target + 1)
    packages = [0] * (scaled_target + 1)
    choice = [-1] * (scaled_target + 1)
    for remaining in range(1, scaled_target + 1):
        best_cost: int | None = None
        best_packages = 0
        best_index = -1
        for index, size in enumerate(sizes):
            previous = max(0, remaining - size)
            candidate_cost = costs[previous] + formats[index].package_price_cents
            candidate_packages = packages[previous] + 1
            if best_cost is None or (candidate_cost, candidate_packages) < (
                best_cost,
                best_packages,
            ):
                best_cost = candidate_cost
                best_packages = candidate_packages
                best_index = index
        if best_cost is None:  # pragma: no cover - siempre hay al menos un formato
            raise PricingError("PRICING_INCONSISTENT", "No se pudo construir el plan de compra.")
        costs[remaining] = best_cost
        packages[remaining] = best_packages
        choice[remaining] = best_index

    counts = [0] * len(formats)
    remaining = scaled_target
    while remaining > 0:
        index = choice[remaining]
        counts[index] += 1
        remaining = max(0, remaining - sizes[index])
    return tuple(counts)


def _plan_counts(formats: Sequence[ProductFormat], target: int) -> tuple[int, ...]:
    """Cuenta de paquetes por formato que cubre ``target`` con coste mínimo."""
    if len(formats) == 1:
        return (_ceil_div(target, formats[0].package_quantity_milli),)

    best = formats[0]
    bounds: list[int] = []
    combinations = 1
    for fmt in formats[1:]:
        bound = best.package_quantity_milli // gcd(
            fmt.package_quantity_milli, best.package_quantity_milli
        )
        bounds.append(bound)
        combinations *= bound

    if combinations <= _MAX_ENUMERATION:
        return _enumerate_counts(formats, target, bounds)
    return _dynamic_program_counts(formats, target)


def plan_purchase(
    ingredient: Ingredient,
    net_need_milli: int,
    formats: Sequence[ProductFormat] | None = None,
) -> PurchasePlan:
    """Plan canónico de compra para una necesidad neta.

    Minimiza ``Σ q[p] × precio[p]`` sujeto a
    ``Σ q[p] × cantidad_paquete[p] ≥ net_need_milli``. Permite mezclar formatos.
    A igual coste, prefiere menos paquetes y ``product_id`` estable. Si se pasan
    ``formats``, el plan se limita a ese conjunto (los productos elegibles de F4).
    """
    if net_need_milli < 0:
        raise PricingError("INVALID_INPUT", "La necesidad neta no puede ser negativa.")
    if net_need_milli == 0:
        return PurchasePlan(
            ingredient_id=ingredient.id,
            net_need_milli=0,
            lines=(),
            purchased_milli=0,
            ticket_cents=0,
        )

    resolved_formats = _require_formats(ingredient, formats)
    counts = _plan_counts(resolved_formats, net_need_milli)
    lines = tuple(
        PurchaseLine(
            product=fmt,
            packages=count,
            quantity_milli=count * fmt.package_quantity_milli,
            subtotal_cents=count * fmt.package_price_cents,
            leftover_milli=count * fmt.package_quantity_milli,
        )
        for fmt, count in zip(resolved_formats, counts, strict=True)
        if count > 0
    )
    purchased = sum(line.quantity_milli for line in lines)
    ticket = sum(line.subtotal_cents for line in lines)
    if purchased < net_need_milli:  # pragma: no cover - invariante del plan
        raise PricingError("PRICING_INCONSISTENT", "El plan de compra no cubre la necesidad.")
    return PurchasePlan(
        ingredient_id=ingredient.id,
        net_need_milli=net_need_milli,
        lines=lines,
        purchased_milli=purchased,
        ticket_cents=ticket,
    )


def price_ingredient(
    ingredient: Ingredient,
    need_milli: int,
    pantry_milli: int = 0,
    formats: Sequence[ProductFormat] | None = None,
) -> IngredientCost:
    """Calcula ticket, consumo, despensa y sobras de un ingrediente."""
    if need_milli < 0 or pantry_milli < 0:
        raise PricingError("INVALID_INPUT", "Las cantidades no pueden ser negativas.")
    if need_milli == 0:
        return IngredientCost(
            ingredient=ingredient,
            need_milli=0,
            pantry_milli=pantry_milli,
            pantry_used_milli=0,
            net_need_milli=0,
            purchased_milli=0,
            leftover_milli=0,
            ticket_cents=0,
            consumption_cents=0,
            pantry_consumption_cents=0,
            leftover_value_cents=0,
            lines=(),
        )

    pantry_used = min(pantry_milli, need_milli)
    net_need = need_milli - pantry_used
    plan = plan_purchase(ingredient, net_need, formats)

    # La despensa se valora al coste unitario del formato elegible más barato;
    # si no hay compra, al producto por defecto del ingrediente.
    resolved_formats = _require_formats(ingredient, formats)
    if plan.lines:
        valuation = resolved_formats[0]
    else:
        valuation = next((fmt for fmt in resolved_formats if fmt.is_default), resolved_formats[0])

    remaining = net_need
    purchased_value = Decimal(0)
    priced_lines: list[PurchaseLine] = []
    for line in plan.lines:
        used = min(remaining, line.quantity_milli)
        purchased_value += Decimal(used) * line.product.unit_cost
        remaining -= used
        priced_lines.append(
            replace(
                line,
                used_milli=used,
                leftover_milli=line.quantity_milli - used,
            )
        )
    if remaining != 0:  # pragma: no cover - invariante del plan
        raise PricingError("PRICING_INCONSISTENT", "El plan de compra no cubre el consumo.")

    pantry_consumption = _round_half_up(Decimal(pantry_used) * valuation.unit_cost)
    purchased_consumption = _round_half_up(purchased_value)
    consumption = pantry_consumption + purchased_consumption
    leftover_value = plan.ticket_cents - purchased_consumption
    if leftover_value < 0:  # pragma: no cover - el consumo nunca supera el ticket
        raise PricingError("PRICING_INCONSISTENT", "El valor de las sobras no puede ser negativo.")

    return IngredientCost(
        ingredient=ingredient,
        need_milli=need_milli,
        pantry_milli=pantry_milli,
        pantry_used_milli=pantry_used,
        net_need_milli=net_need,
        purchased_milli=plan.purchased_milli,
        leftover_milli=plan.purchased_milli - net_need,
        ticket_cents=plan.ticket_cents,
        consumption_cents=consumption,
        pantry_consumption_cents=pantry_consumption,
        leftover_value_cents=leftover_value,
        lines=tuple(priced_lines),
    )


def allocate_cents(total: int, weights: Sequence[int]) -> tuple[int, ...]:
    """Reparte céntimos de forma exacta con el método del mayor resto.

    Se comparte con el servicio de menús para repartir el consumo de cada
    ingrediente entre las entradas sin perder ni duplicar céntimos.
    """
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return tuple(0 for _ in weights)
    exact = [Decimal(total) * Decimal(weight) / Decimal(weight_sum) for weight in weights]
    allocated = [int(value) for value in exact]
    remainder = total - sum(allocated)
    order = sorted(
        range(len(weights)),
        key=lambda index: (-(exact[index] - Decimal(allocated[index])), index),
    )
    for index in order[:remainder]:
        allocated[index] += 1
    return tuple(allocated)


def price_basket(
    dishes: Sequence[Dish],
    people: int,
    pantry: Mapping[int, int] | None = None,
    formats_by_ingredient: Mapping[int, Sequence[ProductFormat]] | None = None,
) -> BasketCost:
    """Calcula el coste agregado de un conjunto de apariciones de platos.

    Cada elemento de ``dishes`` es un hueco del menú; el mismo plato puede
    repetirse. El coste de cada ingrediente se reparte entre las apariciones de
    forma proporcional a su necesidad, con reparto exacto de céntimos. F4 puede
    limitar los formatos comprables por ingrediente con
    ``formats_by_ingredient`` para respetar la elegibilidad.
    """
    if people < 1 or people > MAX_PEOPLE:
        raise PricingError(
            "INVALID_INPUT",
            f"Las personas deben estar entre 1 y {MAX_PEOPLE}.",
        )
    if not dishes:
        raise PricingError("INVALID_INPUT", "El preview necesita al menos un plato.")

    pantry_map = {
        ingredient_id: max(0, quantity) for ingredient_id, quantity in (pantry or {}).items()
    }
    entry_needs: list[dict[int, int]] = []
    ingredients: dict[int, Ingredient] = {}
    totals: dict[int, int] = {}
    for dish in dishes:
        needs = scale_dish(dish, people)
        entry_needs.append(needs)
        for link in dish.ingredients:
            ingredients[link.ingredient_id] = link.ingredient
        for ingredient_id, quantity in needs.items():
            totals[ingredient_id] = totals.get(ingredient_id, 0) + quantity

    ingredient_costs = tuple(
        price_ingredient(
            ingredients[ingredient_id],
            totals[ingredient_id],
            pantry_map.get(ingredient_id, 0),
            formats_by_ingredient.get(ingredient_id) if formats_by_ingredient else None,
        )
        for ingredient_id in sorted(totals)
    )

    entry_cents = [0] * len(dishes)
    for cost in ingredient_costs:
        weights = [needs.get(cost.ingredient.id, 0) for needs in entry_needs]
        if cost.consumption_cents == 0 or sum(weights) == 0:
            continue
        allocated = allocate_cents(cost.consumption_cents, weights)
        for index, cents in enumerate(allocated):
            entry_cents[index] += cents

    dish_costs = tuple(
        DishCost(
            index=index,
            dish=dish,
            servings=people,
            consumption_cents=entry_cents[index],
            per_serving_cents=_round_half_up(Decimal(entry_cents[index]) / Decimal(people)),
        )
        for index, dish in enumerate(dishes)
    )

    return BasketCost(
        people=people,
        ingredients=ingredient_costs,
        dishes=dish_costs,
        ticket_cents=sum(cost.ticket_cents for cost in ingredient_costs),
        consumption_cents=sum(cost.consumption_cents for cost in ingredient_costs),
        pantry_consumption_cents=sum(cost.pantry_consumption_cents for cost in ingredient_costs),
        leftover_value_cents=sum(cost.leftover_value_cents for cost in ingredient_costs),
    )
