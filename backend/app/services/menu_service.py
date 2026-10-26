"""Persistencia, recálculo y mutaciones de menús (F4.5).

``MenuService`` es la única puerta de escritura de ``menus``, ``menu_entries``,
``menu_entry_ingredients`` y ``shopping_items``. Materializa siempre la lista de
la compra con ``pricing.plan_purchase`` sobre la necesidad agregada, nunca con
otro criterio, y verifica en la misma transacción:

- ``ticket_canónico <= ticket_solver <= budget_cents``.
- ``Σ menu_entry_ingredients.consumption_cents = menu_entries.entry_consumption_cents``.
- ``Σ menu_entries.entry_consumption_cents = menus.consumption_cents``.
- ``Σ shopping_items.subtotal_cents = menus.ticket_cents``.
- ``ticket + pantry_consumption = consumption + leftover``.

Las mutaciones que superan el presupuesto se revierten con
``BUDGET_EXCEEDED``. ``regenerate`` conserva los bloqueos y el estado ``checked``
por ``product_id``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE, get_settings
from app.models.catalog import Product, SyncRun
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.models.menu import MENU_SLOTS, Menu, MenuEntry, MenuEntryIngredient, ShoppingItem
from app.models.profile import Exclusion, Profile
from app.schemas.menu import MenuSettings, PantrySnapshot
from app.services.eligibility import (
    DishEligibility,
    PreferenceSnapshot,
    evaluate_dish,
    evaluate_dishes,
    ingredient_eligibility,
)
from app.services.optimizer import (
    OptimizationAssignment,
    OptimizationLock,
    OptimizationRequest,
    OptimizationResult,
    OptimizerError,
    optimize_menu,
    time_limits_from_total,
)
from app.services.pricing import (
    PricingError,
    ProductFormat,
    PurchaseLine,
    allocate_cents,
    price_ingredient,
    purchasable_formats,
    scale_dish,
    scale_quantity,
)

ExclusionScope = Literal["menu", "profile"]

#: Estados que pueden persistirse (`PLAN.md` §10.3).
_PERSISTED_STATUSES: frozenset[str] = frozenset({"optimal", "feasible", "relaxed"})
_VALID_SCOPES: frozenset[str] = frozenset({"menu", "profile"})

#: Firma de una línea de compra para detectar cambios de precio o formato.
_ShoppingSignature = frozenset[tuple[int, int, int, int, int]]


class MenuServiceError(ValueError):
    """Error de dominio del servicio de menús con código estable."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        reason: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.reason = reason
        self.details = details or {}


class _OverBudgetRevalidation(Exception):
    """Señal interna para no persistir una revalidación que supera el presupuesto."""

    def __init__(self, ticket_cents: int) -> None:
        super().__init__("La revalidación supera el presupuesto.")
        self.ticket_cents = ticket_cents


class MenuService:
    """Servicio transaccional de menús."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def generate(
        self,
        *,
        profile_id: int,
        people: int,
        days: int,
        budget_cents: int,
        settings: MenuSettings,
        optimization: OptimizationResult,
        sync_run_id: int | None = None,
        prices_captured_at: datetime | None = None,
    ) -> Menu:
        """Persiste un menú ya optimizado y materializa su lista de la compra."""
        try:
            if not 1 <= people <= 10:
                raise MenuServiceError(
                    "VALIDATION_ERROR",
                    "Las personas deben estar entre 1 y 10.",
                    details={"people": people},
                )
            if not 1 <= days <= 14:
                raise MenuServiceError(
                    "VALIDATION_ERROR",
                    "Los días deben estar entre 1 y 14.",
                    details={"days": days},
                )
            if budget_cents <= 0:
                raise MenuServiceError(
                    "VALIDATION_ERROR",
                    "El presupuesto debe ser positivo.",
                    details={"budget_cents": budget_cents},
                )
            if profile_id < 1 or self.session.get(Profile, profile_id) is None:
                raise self._not_found(
                    "El perfil del menú no existe.",
                    profile_id=profile_id,
                )
            self._validate_persistible_result(optimization, days, code="INVALID_OPTIMIZATION")
            assignments = optimization.assignments
            self._validate_assignment_coverage(
                assignments,
                days,
                code="INVALID_OPTIMIZATION",
                status_code=422,
            )

            preferences = self._preferences(settings)
            eligibility_by_dish = {
                item.dish.id: item for item in evaluate_dishes(self.session, preferences)
            }
            for assignment in assignments:
                eligibility = eligibility_by_dish.get(assignment.dish_id)
                if eligibility is None or not eligibility.eligible:
                    raise self._inconsistent_menu(
                        "Una entrada del menú no tiene productos elegibles.",
                        dish_id=assignment.dish_id,
                        reasons=list(eligibility.reasons) if eligibility is not None else [],
                    )
            self._validate_assignment_rules(
                assignments,
                eligibility_by_dish,
                settings,
                code="INVALID_OPTIMIZATION",
                status_code=422,
            )
            resolved_sync_run_id = self._resolve_sync_run(sync_run_id)

            menu = Menu(
                profile_id=profile_id,
                people=people,
                days=days,
                budget_cents=budget_cents,
                status=optimization.status,
                price_status="current",
                timed_out=optimization.timed_out,
                violations=optimization.violations,
                relaxation_codes_json=list(optimization.relaxation_codes),
                postal_code=POSTAL_CODE,
                warehouse=EXPECTED_WAREHOUSE,
                optimizer_version=settings.optimizer_version,
                settings_json=settings.model_dump(mode="json"),
                sync_run_id=resolved_sync_run_id,
                prices_captured_at=prices_captured_at,
            )
            self.session.add(menu)
            self.session.flush()

            for assignment in assignments:
                dish = eligibility_by_dish[assignment.dish_id].dish
                menu.entries.append(
                    self._entry_from_dish(
                        dish,
                        assignment.day_index,
                        assignment.slot,
                        locked=assignment.locked,
                        dish_name=assignment.dish_name or dish.name,
                        protein_source=assignment.protein_source,
                    )
                )
            self.session.flush()

            self._rebuild_children(
                menu,
                settings=settings,
                eligibility_by_dish=eligibility_by_dish,
            )

            if not (menu.ticket_cents <= optimization.solver_ticket_cents <= menu.budget_cents):
                raise self._inconsistent_menu(
                    "El ticket del solver no es coherente con el plan canónico.",
                    ticket_canonical_cents=menu.ticket_cents,
                    solver_ticket_cents=optimization.solver_ticket_cents,
                    budget_cents=menu.budget_cents,
                )

            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def recalculate(
        self,
        menu_id: int,
        *,
        enforce_budget: bool = True,
        mark_stale: bool = False,
    ) -> Menu:
        """Recalcula ticket, costes por entrada y lista con los precios actuales.

        Con ``enforce_budget=True`` (mutaciones) un ticket superior al
        presupuesto revierte con ``BUDGET_EXCEEDED``. Con ``enforce_budget=False``
        (revalidación) el menú guardado conserva su snapshot válido y solo se
        registra el ticket recalculado en ``revalidated_ticket_cents`` con
        ``price_status="stale"``; nunca se persiste un ticket por encima del
        presupuesto.
        """
        try:
            menu = self._require_menu(menu_id)
            if not enforce_budget:
                return self._revalidate_prices(menu)
            previous_signature = self._rebuild_children(menu)
            self._enforce_budget(menu, enforce_budget=True)
            if mark_stale:
                menu.revalidated_ticket_cents = menu.ticket_cents
                current_signature = self._shopping_signature(list(menu.shopping_items))
                menu.price_status = (
                    "stale" if current_signature != previous_signature else "current"
                )
            else:
                menu.price_status = "current"
                menu.revalidated_ticket_cents = None
            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def _revalidate_prices(self, menu: Menu) -> Menu:
        """Recalcula precios sin romper el invariante de presupuesto."""
        menu_id = menu.id
        try:
            with self.session.begin_nested():
                previous_signature = self._rebuild_children(menu, budget_mode="signal")
                current_signature = self._shopping_signature(list(menu.shopping_items))
                menu.revalidated_ticket_cents = menu.ticket_cents
                menu.price_status = (
                    "stale" if current_signature != previous_signature else "current"
                )
                self.verify_identities(menu.id)
        except _OverBudgetRevalidation as exc:
            # El savepoint ha revertido la lista y los costes; se conserva el
            # snapshot válido y se expone el ticket recalculado para el aviso.
            self.session.expire_all()
            menu = self._require_menu(menu_id)
            menu.revalidated_ticket_cents = exc.ticket_cents
            menu.price_status = "stale"
            self.session.commit()
            return self._require_menu(menu_id)
        self.session.commit()
        return self._require_menu(menu_id)

    def swap_entry(self, menu_id: int, entry_id: int, dish_id: int) -> Menu:
        """Cambia el plato de una entrada y recalcula; rechaza si supera presupuesto."""
        try:
            menu = self._require_menu(menu_id)
            entry = self._require_entry(menu, entry_id)
            dish = self._load_dishes({dish_id}).get(dish_id)
            if dish is None or not dish.active:
                raise self._not_found(
                    "El plato solicitado no existe o está inactivo.",
                    dish_id=dish_id,
                )
            if not self._compatible_with_slot(dish, entry.slot):
                raise MenuServiceError(
                    "VALIDATION_ERROR",
                    "El plato no es compatible con el hueco del menú.",
                    details={
                        "dish_id": dish.id,
                        "slot": entry.slot,
                        "meal_types": list(dish.meal_types_json or []),
                    },
                )
            settings = self._settings(menu)
            preferences = self._preferences(settings)
            eligibility = evaluate_dish(dish, preferences)
            if not eligibility.eligible:
                raise MenuServiceError(
                    "NO_FEASIBLE_MENU",
                    "El plato no es elegible con las preferencias del menú.",
                    reason="no_assignment",
                    details={
                        "dish_id": dish.id,
                        "reasons": list(eligibility.reasons),
                    },
                )
            repeated = self.session.scalar(
                select(MenuEntry.id).where(
                    MenuEntry.menu_id == menu.id,
                    MenuEntry.day_index == entry.day_index,
                    MenuEntry.id != entry.id,
                    MenuEntry.dish_id == dish.id,
                )
            )
            if repeated is not None:
                raise MenuServiceError(
                    "NO_FEASIBLE_MENU",
                    "El plato ya está en el otro hueco del mismo día.",
                    reason="repeats",
                    details={"dish_id": dish.id, "day_index": entry.day_index},
                )
            occurrences = self.session.scalar(
                select(func.count())
                .select_from(MenuEntry)
                .where(
                    MenuEntry.menu_id == menu.id,
                    MenuEntry.id != entry.id,
                    MenuEntry.dish_id == dish.id,
                )
            )
            if int(occurrences or 0) >= settings.max_repeats:
                raise MenuServiceError(
                    "NO_FEASIBLE_MENU",
                    "El plato alcanzó el máximo de repeticiones del menú.",
                    reason="repeats",
                    details={
                        "dish_id": dish.id,
                        "max_repeats": settings.max_repeats,
                        "occurrences": int(occurrences or 0),
                    },
                )

            entry.dish_id = dish.id
            entry.dish = dish
            entry.dish_name = dish.name
            entry.entry_protein_source = self._protein_source(dish)
            # La composición de la entrada cambia: se recalcula desde el plato.
            entry.ingredients.clear()

            self._rebuild_children(menu, settings=settings)
            self._enforce_budget(menu, enforce_budget=True)
            self._mark_manual_change(menu)

            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def exclude_entry(self, menu_id: int, entry_id: int, scope: ExclusionScope) -> Menu:
        """Excluye el plato del menú o del perfil y busca un reemplazo elegible."""
        try:
            if scope not in _VALID_SCOPES:
                raise MenuServiceError(
                    "VALIDATION_ERROR",
                    "El ámbito de exclusión no es válido.",
                    details={"scope": scope, "allowed": sorted(_VALID_SCOPES)},
                )
            menu = self._require_menu(menu_id)
            entry = self._require_entry(menu, entry_id)
            excluded_dish_id = entry.dish_id
            settings = self._settings(menu)

            if excluded_dish_id not in settings.excluded_dish_ids:
                settings.excluded_dish_ids.append(excluded_dish_id)
            menu.settings_json = settings.model_dump(mode="json")

            if scope == "profile":
                already_excluded = self.session.scalar(
                    select(Exclusion.id).where(
                        Exclusion.profile_id == menu.profile_id,
                        Exclusion.dish_id == excluded_dish_id,
                    )
                )
                if already_excluded is None:
                    self.session.add(
                        Exclusion(profile_id=menu.profile_id, dish_id=excluded_dish_id)
                    )

            preferences = self._preferences(settings)
            eligible = [
                item for item in evaluate_dishes(self.session, preferences) if item.eligible
            ]
            available = [item.dish for item in eligible]
            all_ingredients: dict[int, Ingredient] = {}
            for dish in available:
                for link in dish.ingredients:
                    all_ingredients[link.ingredient_id] = link.ingredient
            formats_by_ingredient = self._formats_by_ingredient(
                all_ingredients,
                preferences,
            )
            available.sort(
                key=lambda dish: (
                    self._estimated_dish_cents(dish, menu.people, formats_by_ingredient),
                    dish.name,
                    dish.id,
                )
            )
            # El plato excluido puede aparecer más de una vez si se permitieron
            # repeticiones; se sustituyen todas las apariciones del mismo día.
            targets = [item for item in menu.entries if item.dish_id == excluded_dish_id]
            for target in targets:
                used_today = {
                    other.dish_id
                    for other in menu.entries
                    if other.id != target.id and other.day_index == target.day_index
                }
                replacement = next(
                    (
                        dish
                        for dish in available
                        if dish.id not in used_today
                        and self._compatible_with_slot(dish, target.slot)
                        and self._occurrences(
                            menu,
                            dish.id,
                            exclude_entry_id=target.id,
                        )
                        < settings.max_repeats
                    ),
                    None,
                )
                if replacement is None:
                    raise MenuServiceError(
                        "NO_FEASIBLE_MENU",
                        "No hay un plato elegible para reemplazar la entrada.",
                        reason="no_assignment",
                        details={
                            "day_index": target.day_index,
                            "slot": target.slot,
                            "excluded_dish_id": excluded_dish_id,
                        },
                    )
                target.dish_id = replacement.id
                target.dish = replacement
                target.dish_name = replacement.name
                target.entry_protein_source = self._protein_source(replacement)
                target.ingredients.clear()

            self._rebuild_children(menu, settings=settings)
            self._enforce_budget(menu, enforce_budget=True)
            self._mark_manual_change(menu)

            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def regenerate(self, menu_id: int, request: OptimizationRequest | None = None) -> Menu:
        """Regenera el menú respetando los bloqueos y el snapshot de preferencias."""
        try:
            menu = self._require_menu(menu_id)
            settings = self._settings(menu)
            resolved_request = request or self._build_optimization_request(menu, settings)

            eligibility = evaluate_dishes(self.session, resolved_request.preferences)
            try:
                result = optimize_menu(eligibility, resolved_request)
            except OptimizerError as exc:
                raise MenuServiceError(
                    exc.code,
                    exc.message,
                    status_code=422,
                    reason=exc.reason,
                    details=exc.details,
                ) from exc

            if result.status == "timeout":
                raise MenuServiceError(
                    "SOLVER_TIMEOUT",
                    "El optimizador agotó el tiempo sin un menú válido.",
                    status_code=200,
                    reason="timeout",
                    details={"elapsed_seconds": result.elapsed_seconds},
                )
            if result.status == "infeasible":
                raise MenuServiceError(
                    "BUDGET_EXCEEDED",
                    "El presupuesto no permite ningún menú válido.",
                    reason="budget",
                    details={
                        "minimum_ticket_cents": result.minimum_ticket_cents,
                        "minimum_is_estimate": result.minimum_is_estimate,
                        "shortfall_cents": result.shortfall_cents,
                        "suggestions": list(result.suggestions),
                    },
                )
            self._validate_persistible_result(
                result,
                menu.days,
                code="INCONSISTENT_MENU",
                status_code=500,
            )
            self._validate_assignment_coverage(
                result.assignments,
                menu.days,
                code="INCONSISTENT_MENU",
                status_code=500,
            )

            dishes_by_id = {item.dish.id: item.dish for item in eligibility if item.eligible}
            eligibility_by_dish = {item.dish.id: item for item in eligibility if item.eligible}
            locked_by_slot = {(entry.day_index, entry.slot): entry.locked for entry in menu.entries}
            for assignment in result.assignments:
                if assignment.dish_id not in dishes_by_id:
                    raise self._inconsistent_menu(
                        "El optimizador devolvió un plato no elegible.",
                        dish_id=assignment.dish_id,
                    )
            self._validate_assignment_rules(
                result.assignments,
                eligibility_by_dish,
                settings,
                code="INCONSISTENT_MENU",
                status_code=500,
            )

            menu.entries.clear()
            self.session.flush()
            for assignment in result.assignments:
                dish = dishes_by_id[assignment.dish_id]
                menu.entries.append(
                    self._entry_from_dish(
                        dish,
                        assignment.day_index,
                        assignment.slot,
                        locked=locked_by_slot.get(
                            (assignment.day_index, assignment.slot),
                            assignment.locked,
                        ),
                        dish_name=assignment.dish_name or dish.name,
                        protein_source=assignment.protein_source,
                    )
                )
            self.session.flush()

            menu.status = result.status
            menu.timed_out = result.timed_out
            menu.violations = result.violations
            menu.relaxation_codes_json = list(result.relaxation_codes)
            self._rebuild_children(menu, settings=settings)
            self._enforce_budget(menu, enforce_budget=True)
            menu.price_status = "current"
            menu.revalidated_ticket_cents = None

            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def revalidate(self, menu_id: int) -> Menu:
        """Recalcula con los precios actuales y marca ``stale`` si el ticket cambia."""
        return self.recalculate(menu_id, enforce_budget=False, mark_stale=True)

    def set_pantry_sufficient(self, menu_id: int, ingredient_id: int) -> Menu:
        """Aplica «ya lo tengo» al snapshot del menú y recalcula."""
        try:
            menu = self._require_menu(menu_id)
            settings = self._settings(menu)
            dishes = self._load_dishes({entry.dish_id for entry in menu.entries})
            persisted_needs = {
                entry.id: {
                    row.ingredient_id: row.used_milli
                    for row in entry.ingredients
                    if row.used_milli > 0
                }
                for entry in menu.entries
            }
            _, totals, ingredients = self._entry_requirements(
                menu,
                dishes,
                persisted_needs,
            )
            if ingredient_id not in ingredients:
                raise self._not_found(
                    "El ingrediente no forma parte del menú.",
                    ingredient_id=ingredient_id,
                    menu_id=menu.id,
                )
            need_milli = totals.get(ingredient_id, 0)
            pantry = [item for item in settings.pantry if item.ingredient_id != ingredient_id]
            pantry.append(PantrySnapshot(ingredient_id=ingredient_id, quantity_milli=need_milli))
            settings.pantry = pantry
            menu.settings_json = settings.model_dump(mode="json")

            self._rebuild_children(menu, settings=settings)
            self._enforce_budget(menu, enforce_budget=True)
            self._mark_manual_change(menu)

            self.verify_identities(menu.id)
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def set_shopping_item_checked(self, menu_id: int, item_id: int, checked: bool) -> Menu:
        """Marca una línea de compra sin recalcular el ticket."""
        try:
            menu = self._require_menu(menu_id)
            item = self.session.get(ShoppingItem, item_id)
            if item is None or item.menu_id != menu.id:
                raise self._not_found(
                    "La línea de compra no existe en este menú.",
                    item_id=item_id,
                    menu_id=menu.id,
                )
            item.checked = checked
            self.session.commit()
            return self._require_menu(menu.id)
        except Exception:
            self.session.rollback()
            raise

    def verify_identities(self, menu_id: int) -> None:
        """Comprueba las identidades contables y lanza ``INCONSISTENT_MENU`` si fallan."""
        try:
            menu = self._require_menu(menu_id)
            entries = list(
                self.session.scalars(
                    select(MenuEntry)
                    .where(MenuEntry.menu_id == menu.id)
                    .order_by(MenuEntry.day_index, MenuEntry.slot)
                ).all()
            )
            failures: list[str] = []
            for entry in entries:
                entry_ingredients_total = int(
                    self.session.scalar(
                        select(
                            func.coalesce(
                                func.sum(MenuEntryIngredient.consumption_cents),
                                0,
                            )
                        ).where(MenuEntryIngredient.entry_id == entry.id)
                    )
                    or 0
                )
                if entry_ingredients_total != entry.entry_consumption_cents:
                    failures.append(
                        f"menu_entry_ingredients != entry_consumption_cents (entry_id={entry.id})"
                    )

            entries_total = sum(entry.entry_consumption_cents for entry in entries)
            if entries_total != menu.consumption_cents:
                failures.append("menu_entries != menus.consumption_cents")

            shopping_total = int(
                self.session.scalar(
                    select(func.coalesce(func.sum(ShoppingItem.subtotal_cents), 0)).where(
                        ShoppingItem.menu_id == menu.id
                    )
                )
                or 0
            )
            if shopping_total != menu.ticket_cents:
                failures.append("shopping_items != menus.ticket_cents")

            shopping_items = list(
                self.session.scalars(
                    select(ShoppingItem)
                    .where(ShoppingItem.menu_id == menu.id)
                    .order_by(ShoppingItem.id)
                ).all()
            )
            for item in shopping_items:
                if item.subtotal_cents != item.packages * item.package_price_cents:
                    failures.append(f"subtotal incoherente (shopping_item_id={item.id})")

            if (
                menu.ticket_cents + menu.pantry_consumption_cents
                != menu.consumption_cents + menu.leftover_value_cents
            ):
                failures.append("ticket + pantry_consumption != consumption + leftover")

            if menu.ticket_cents > menu.budget_cents:
                failures.append("ticket_cents > budget_cents")

            if failures:
                raise self._inconsistent_menu(
                    "Las identidades contables del menú no cuadran.",
                    menu_id=menu.id,
                    failures=failures,
                    ticket_cents=menu.ticket_cents,
                    shopping_total_cents=shopping_total,
                    consumption_cents=menu.consumption_cents,
                    entries_total_cents=entries_total,
                    pantry_consumption_cents=menu.pantry_consumption_cents,
                    leftover_value_cents=menu.leftover_value_cents,
                )
        except Exception:
            self.session.rollback()
            raise

    # ------------------------------------------------------------------
    # Materialización del menú
    # ------------------------------------------------------------------

    def _rebuild_children(
        self,
        menu: Menu,
        *,
        settings: MenuSettings | None = None,
        eligibility_by_dish: Mapping[int, DishEligibility] | None = None,
        budget_mode: Literal["enforce", "signal"] = "enforce",
    ) -> _ShoppingSignature:
        """Reemplaza entradas hijas y lista desde el plan canónico de compra.

        Devuelve la firma de la lista anterior para que ``revalidate`` pueda
        decidir si los precios cambiaron.
        """
        resolved_settings = settings or self._settings(menu)
        preferences = self._preferences(resolved_settings)
        entries = list(menu.entries)
        if len(entries) != menu.days * 2:
            raise self._inconsistent_menu(
                "El menú no tiene exactamente dos entradas por día.",
                expected=menu.days * 2,
                actual=len(entries),
            )

        dishes = self._load_dishes({entry.dish_id for entry in entries})
        missing = sorted({entry.dish_id for entry in entries} - set(dishes))
        if missing:
            raise self._inconsistent_menu(
                "Alguna entrada apunta a un plato inexistente.",
                dish_ids=missing,
            )

        resolved_eligibility = dict(eligibility_by_dish or {})
        for dish_id, dish in dishes.items():
            if dish_id not in resolved_eligibility:
                resolved_eligibility[dish_id] = evaluate_dish(dish, preferences)
            eligibility = resolved_eligibility[dish_id]
            if not eligibility.eligible:
                if "no_eligible_product" in eligibility.reasons:
                    raise MenuServiceError(
                        "PRODUCT_UNAVAILABLE",
                        "Un plato del menú ya no tiene productos elegibles disponibles.",
                        status_code=409,
                        details={
                            "dish_id": dish_id,
                            "reasons": list(eligibility.reasons),
                            "blocked_ingredient_ids": list(eligibility.blocked_ingredient_ids),
                        },
                    )
                raise self._inconsistent_menu(
                    "Una entrada del menú ha dejado de ser elegible.",
                    dish_id=dish_id,
                    reasons=list(eligibility.reasons),
                )

        previous_signature = self._shopping_signature(list(menu.shopping_items))
        checked_by_product = {item.product_id: item.checked for item in list(menu.shopping_items)}
        persisted_needs = {
            entry.id: {
                row.ingredient_id: row.used_milli for row in entry.ingredients if row.used_milli > 0
            }
            for entry in entries
        }

        entry_needs, totals, ingredients = self._entry_requirements(
            menu,
            dishes,
            persisted_needs,
        )
        formats_by_ingredient = self._formats_by_ingredient(ingredients, preferences)
        pantry_by_ingredient = {
            item.ingredient_id: item.quantity_milli for item in resolved_settings.pantry
        }

        resolved_formats_by_ingredient: dict[int, tuple[ProductFormat, ...]] = {}
        costs = []
        for ingredient_id in sorted(totals):
            ingredient = ingredients[ingredient_id]
            formats = formats_by_ingredient[ingredient_id]
            resolved_formats_by_ingredient[ingredient_id] = formats
            try:
                costs.append(
                    price_ingredient(
                        ingredient,
                        totals[ingredient_id],
                        pantry_by_ingredient.get(ingredient_id, 0),
                        formats,
                    )
                )
            except PricingError as exc:
                raise self._inconsistent_menu(
                    "No se pudo valorar un ingrediente del menú.",
                    ingredient_id=ingredient_id,
                    ingredient_name=ingredient.name,
                    pricing_code=exc.code,
                    pricing_details=exc.details,
                ) from exc

        # Las colecciones se vacían antes de insertar para no chocar con las
        # restricciones únicas (entry_id, ingredient_id) y (menu_id, product_id).
        for entry in entries:
            entry.ingredients.clear()
        menu.shopping_items.clear()
        self.session.flush()

        consumption_by_entry: dict[int, int] = {entry.id: 0 for entry in entries}
        for cost in costs:
            entry_ids = [
                entry.id for entry in entries if cost.ingredient.id in entry_needs[entry.id]
            ]
            weights = [entry_needs[entry_id][cost.ingredient.id] for entry_id in entry_ids]
            allocated = allocate_cents(cost.consumption_cents, weights)
            product_id = self._representative_product_id(
                resolved_formats_by_ingredient[cost.ingredient.id],
                cost.lines,
            )
            entries_by_id = {entry.id: entry for entry in entries}
            for entry_id, cents in zip(entry_ids, allocated, strict=True):
                entries_by_id[entry_id].ingredients.append(
                    MenuEntryIngredient(
                        ingredient_id=cost.ingredient.id,
                        product_id=product_id,
                        used_milli=entry_needs[entry_id][cost.ingredient.id],
                        consumption_cents=cents,
                    )
                )
                consumption_by_entry[entry_id] += cents

            for line_index, line in enumerate(cost.lines):
                # La despensa se guarda una sola vez por ingrediente (en su
                # primera línea) para que sumar la lista no la duplique.
                menu.shopping_items.append(
                    ShoppingItem(
                        product_id=line.product.product_id,
                        ingredient_id=cost.ingredient.id,
                        packages=line.packages,
                        package_quantity_milli=line.product.package_quantity_milli,
                        package_price_cents=line.product.package_price_cents,
                        subtotal_cents=line.subtotal_cents,
                        pantry_quantity_milli=(cost.pantry_milli if line_index == 0 else 0),
                        checked=checked_by_product.get(line.product.product_id, False),
                    )
                )

        for entry in entries:
            entry.entry_consumption_cents = consumption_by_entry[entry.id]

        menu.ticket_cents = sum(cost.ticket_cents for cost in costs)
        menu.consumption_cents = sum(cost.consumption_cents for cost in costs)
        menu.pantry_consumption_cents = sum(cost.pantry_consumption_cents for cost in costs)
        menu.leftover_value_cents = sum(cost.leftover_value_cents for cost in costs)
        if menu.ticket_cents > menu.budget_cents:
            if budget_mode == "signal":
                raise _OverBudgetRevalidation(menu.ticket_cents)
            raise MenuServiceError(
                "BUDGET_EXCEEDED",
                "El menú supera el presupuesto.",
                reason="budget",
                details={
                    "ticket_cents": menu.ticket_cents,
                    "budget_cents": menu.budget_cents,
                },
            )
        self.session.flush()
        return previous_signature

    def _entry_requirements(
        self,
        menu: Menu,
        dishes: Mapping[int, Dish],
        persisted_needs: Mapping[int, Mapping[int, int]] | None = None,
    ) -> tuple[dict[int, dict[int, int]], dict[int, int], dict[int, Ingredient]]:
        """Necesidad por entrada, agregada por ingrediente y objetos cargados.

        Si la entrada ya tiene `menu_entry_ingredients`, se usan sus
        `used_milli` como snapshot de composición. Así un cambio posterior en el
        seed del plato no altera el coste ni las cantidades de un menú históricamente
        válido; solo se recalculan precios.
        """
        entry_needs: dict[int, dict[int, int]] = {}
        totals: dict[int, int] = {}
        ingredients: dict[int, Ingredient] = {}
        for entry in menu.entries:
            dish = dishes.get(entry.dish_id)
            if dish is None:
                raise self._inconsistent_menu(
                    "Alguna entrada apunta a un plato inexistente.",
                    dish_id=entry.dish_id,
                )
            stored = (persisted_needs or {}).get(entry.id) or {}
            if stored:
                needs = {ingredient_id: quantity for ingredient_id, quantity in stored.items()}
            else:
                needs = scale_dish(dish, menu.people)
                for link in dish.ingredients:
                    ingredients[link.ingredient_id] = link.ingredient
            entry_needs[entry.id] = {
                ingredient_id: quantity for ingredient_id, quantity in needs.items() if quantity > 0
            }
            for ingredient_id, quantity in entry_needs[entry.id].items():
                totals[ingredient_id] = totals.get(ingredient_id, 0) + quantity

        missing_ingredients = set(totals) - set(ingredients)
        if missing_ingredients:
            ingredients.update(self._load_ingredients(missing_ingredients))
        return entry_needs, totals, ingredients

    def _formats_by_ingredient(
        self,
        ingredients: Mapping[int, Ingredient],
        preferences: PreferenceSnapshot,
    ) -> dict[int, tuple[ProductFormat, ...]]:
        """Formatos comprables restringidos a los productos elegibles ``P_i``."""
        formats_by_ingredient: dict[int, tuple[ProductFormat, ...]] = {}
        for ingredient_id in sorted(ingredients):
            ingredient = ingredients[ingredient_id]
            if ingredient_id in preferences.excluded_ingredient_ids:
                raise MenuServiceError(
                    "NO_FEASIBLE_MENU",
                    "Un ingrediente del menú está excluido por las preferencias.",
                    reason="no_assignment",
                    details={
                        "ingredient_id": ingredient_id,
                        "ingredient_name": ingredient.name,
                    },
                )
            eligibility = ingredient_eligibility(ingredient, preferences.allergen_codes)
            allowed = {mapping.product_id for mapping in eligibility.eligible_products}
            formats = purchasable_formats(
                ingredient,
                allowed_product_ids=allowed,
            )
            if not formats:
                raise MenuServiceError(
                    "PRODUCT_UNAVAILABLE",
                    "Un ingrediente del menú no tiene un producto elegible disponible.",
                    status_code=409,
                    details={
                        "ingredient_id": ingredient_id,
                        "ingredient_name": ingredient.name,
                        "allergen_status": [
                            mapping.product.allergen_status for mapping in ingredient.products
                        ],
                    },
                )
            formats_by_ingredient[ingredient_id] = formats
        return formats_by_ingredient

    @staticmethod
    def _representative_product_id(
        formats: Sequence[ProductFormat],
        lines: Sequence[PurchaseLine],
    ) -> int:
        """Producto de la entrada: primer formato comprado o el de respaldo."""
        if lines:
            return lines[0].product.product_id
        default = next((fmt for fmt in formats if fmt.is_default), None)
        if default is not None:
            return default.product_id
        return min(fmt.product_id for fmt in formats)

    # ------------------------------------------------------------------
    # Helpers de carga y validación
    # ------------------------------------------------------------------

    def _require_menu(self, menu_id: int) -> Menu:
        menu = self.session.get(Menu, menu_id)
        if menu is None:
            raise self._not_found("El menú no existe.", menu_id=menu_id)
        return menu

    def _require_entry(self, menu: Menu, entry_id: int) -> MenuEntry:
        entry = self.session.scalar(
            select(MenuEntry).where(
                MenuEntry.id == entry_id,
                MenuEntry.menu_id == menu.id,
            )
        )
        if entry is None:
            raise self._not_found(
                "La entrada no existe en este menú.",
                menu_id=menu.id,
                entry_id=entry_id,
            )
        return entry

    def _settings(self, menu: Menu) -> MenuSettings:
        try:
            return MenuSettings.model_validate(menu.settings_json)
        except ValidationError as exc:
            raise self._inconsistent_menu(
                "El snapshot de preferencias del menú no es válido.",
                menu_id=menu.id,
                errors=exc.errors(include_url=False),
            ) from exc

    def _resolve_sync_run(self, sync_run_id: int | None) -> int:
        """Confirma que los precios proceden de 22002/4389.

        Si se indica una sync concreta, debe existir, haber terminado y usar el
        almacén esperado. Si se omite, se toma la última sync válida; sin ella no
        se genera menú (invariante 10 de `AGENTS.md`).
        """
        valid_statuses = ("success", "partial")
        if sync_run_id is not None:
            run = self.session.get(SyncRun, sync_run_id)
            if (
                run is None
                or run.status not in valid_statuses
                or run.postal_code != POSTAL_CODE
                or run.warehouse != EXPECTED_WAREHOUSE
            ):
                raise MenuServiceError(
                    "WAREHOUSE_UNAVAILABLE",
                    "La sincronización indicada no confirma el almacén 4389 para el CP 22002.",
                    status_code=503,
                    details={"sync_run_id": sync_run_id},
                )
            return run.id

        run = self.session.scalar(
            select(SyncRun)
            .where(
                SyncRun.status.in_(valid_statuses),
                SyncRun.postal_code == POSTAL_CODE,
                SyncRun.warehouse == EXPECTED_WAREHOUSE,
            )
            .order_by(SyncRun.id.desc())
        )
        if run is None:
            raise MenuServiceError(
                "WAREHOUSE_UNAVAILABLE",
                "No hay una sincronización confirmada para el CP 22002 y el almacén 4389.",
                status_code=503,
            )
        return run.id

    @staticmethod
    def _preferences(settings: MenuSettings) -> PreferenceSnapshot:
        return PreferenceSnapshot(
            allergen_codes=frozenset(settings.allergen_codes),
            excluded_ingredient_ids=frozenset(settings.excluded_ingredient_ids),
            excluded_dish_ids=frozenset(settings.excluded_dish_ids),
            excluded_tags=frozenset(settings.excluded_tags),
        )

    def _load_dishes(self, dish_ids: set[int]) -> dict[int, Dish]:
        if not dish_ids:
            return {}
        statement = (
            select(Dish)
            .where(Dish.id.in_(dish_ids))
            .options(
                selectinload(Dish.ingredients)
                .selectinload(DishIngredient.ingredient)
                .selectinload(Ingredient.products)
                .selectinload(IngredientProduct.product)
                .selectinload(Product.allergens)
            )
        )
        return {dish.id: dish for dish in self.session.scalars(statement).all()}

    def _load_ingredients(self, ingredient_ids: set[int]) -> dict[int, Ingredient]:
        if not ingredient_ids:
            return {}
        statement = (
            select(Ingredient)
            .where(Ingredient.id.in_(ingredient_ids))
            .options(
                selectinload(Ingredient.products)
                .selectinload(IngredientProduct.product)
                .selectinload(Product.allergens)
            )
        )
        return {ingredient.id: ingredient for ingredient in self.session.scalars(statement).all()}

    def _build_optimization_request(
        self,
        menu: Menu,
        settings: MenuSettings,
    ) -> OptimizationRequest:
        locks = tuple(
            OptimizationLock(
                day_index=entry.day_index,
                slot=entry.slot,
                dish_id=entry.dish_id,
            )
            for entry in menu.entries
            if entry.locked
        )
        pantry = {item.ingredient_id: item.quantity_milli for item in settings.pantry}
        stage1, stage2, fallback = time_limits_from_total(
            get_settings().optimizer_time_limit_seconds
        )
        return OptimizationRequest(
            people=menu.people,
            days=menu.days,
            budget_cents=menu.budget_cents,
            preferences=self._preferences(settings),
            pantry=pantry,
            max_repeats=settings.max_repeats,
            locks=locks,
            stage1_seconds=stage1,
            stage2_seconds=stage2,
            fallback_seconds=fallback,
        )

    @staticmethod
    def _entry_from_dish(
        dish: Dish,
        day_index: int,
        slot: str,
        *,
        locked: bool,
        dish_name: str | None = None,
        protein_source: str | None = None,
    ) -> MenuEntry:
        return MenuEntry(
            day_index=day_index,
            slot=slot,
            dish=dish,
            dish_id=dish.id,
            dish_name=dish_name or dish.name,
            locked=locked,
            entry_protein_source=protein_source or MenuService._protein_source(dish),
        )

    @staticmethod
    def _protein_source(dish: Dish) -> str | None:
        sources = dish.protein_sources_json or []
        return str(sources[0]) if sources else None

    @staticmethod
    def _estimated_dish_cents(
        dish: Dish,
        people: int,
        formats_by_ingredient: Mapping[int, Sequence[ProductFormat]],
    ) -> int:
        """Coste aproximado de una aparición para ordenar reemplazos baratos."""
        total = 0
        for link in dish.ingredients:
            formats = formats_by_ingredient.get(link.ingredient_id)
            if not formats:
                return 2**31 - 1
            coef = scale_quantity(link.quantity_milli, people, dish.base_servings)
            total += min(
                (coef * fmt.package_price_cents) // fmt.package_quantity_milli for fmt in formats
            )
        return total

    @staticmethod
    def _compatible_with_slot(dish: Dish, slot: str) -> bool:
        meal_types = set(dish.meal_types_json or [])
        return slot in meal_types or "both" in meal_types

    @staticmethod
    def _shopping_signature(items: Sequence[ShoppingItem]) -> _ShoppingSignature:
        return frozenset(
            (
                item.product_id,
                item.packages,
                item.package_quantity_milli,
                item.package_price_cents,
                item.subtotal_cents,
            )
            for item in items
        )

    def _enforce_budget(self, menu: Menu, enforce_budget: bool) -> None:
        if enforce_budget and menu.ticket_cents > menu.budget_cents:
            raise MenuServiceError(
                "BUDGET_EXCEEDED",
                "El menú supera el presupuesto.",
                reason="budget",
                details={
                    "ticket_cents": menu.ticket_cents,
                    "budget_cents": menu.budget_cents,
                },
            )

    @staticmethod
    def _mark_manual_change(menu: Menu) -> None:
        """Una mutación manual deja de ser óptima; sigue siendo un menú válido."""
        if menu.status != "relaxed":
            menu.status = "feasible"
        menu.price_status = "current"
        menu.revalidated_ticket_cents = None

    @staticmethod
    def _occurrences(menu: Menu, dish_id: int, *, exclude_entry_id: int) -> int:
        """Apariciones de un plato en el menú, ignorando una entrada concreta."""
        return sum(
            1 for entry in menu.entries if entry.dish_id == dish_id and entry.id != exclude_entry_id
        )

    @staticmethod
    def _validate_persistible_result(
        optimization: OptimizationResult,
        days: int,
        *,
        code: str,
        status_code: int = 422,
    ) -> None:
        """Rechaza previews, estados no persistibles y menús incompletos."""
        if (
            optimization.status not in _PERSISTED_STATUSES
            or optimization.is_preview
            or not optimization.assignments
            or len(optimization.assignments) != days * 2
        ):
            raise MenuServiceError(
                code,
                "El resultado del optimizador no es persistible.",
                status_code=status_code,
                details={
                    "status": optimization.status,
                    "is_preview": optimization.is_preview,
                    "assignments": len(optimization.assignments),
                    "expected_assignments": days * 2,
                },
            )

    @staticmethod
    def _validate_assignment_coverage(
        assignments: Sequence[OptimizationAssignment],
        days: int,
        *,
        code: str,
        status_code: int = 422,
    ) -> None:
        expected = {(day, slot) for day in range(days) for slot in MENU_SLOTS}
        actual = {(assignment.day_index, assignment.slot) for assignment in assignments}
        if actual != expected:
            raise MenuServiceError(
                code,
                "Las asignaciones no cubren todos los huecos del menú.",
                status_code=status_code,
                details={
                    "expected_slots": sorted(expected),
                    "actual_slots": sorted(actual),
                },
            )

    @classmethod
    def _validate_assignment_rules(
        cls,
        assignments: Sequence[OptimizationAssignment],
        eligibility_by_dish: Mapping[int, DishEligibility],
        settings: MenuSettings,
        *,
        code: str,
        status_code: int = 422,
    ) -> None:
        """Comprueba compatibilidad de hueco, repeticiones y plato único por día."""
        counts: dict[int, int] = {}
        seen_day_dish: set[tuple[int, int]] = set()
        for assignment in assignments:
            dish = eligibility_by_dish[assignment.dish_id].dish
            if not cls._compatible_with_slot(dish, assignment.slot):
                raise MenuServiceError(
                    code,
                    "El plato asignado no es compatible con el hueco.",
                    status_code=status_code,
                    details={
                        "dish_id": assignment.dish_id,
                        "slot": assignment.slot,
                        "meal_types": list(dish.meal_types_json or []),
                    },
                )
            day_dish = (assignment.day_index, assignment.dish_id)
            if day_dish in seen_day_dish:
                raise MenuServiceError(
                    code,
                    "El mismo plato aparece dos veces en el mismo día.",
                    status_code=status_code,
                    details={
                        "dish_id": assignment.dish_id,
                        "day_index": assignment.day_index,
                    },
                )
            seen_day_dish.add(day_dish)
            counts[assignment.dish_id] = counts.get(assignment.dish_id, 0) + 1
            if counts[assignment.dish_id] > settings.max_repeats:
                raise MenuServiceError(
                    code,
                    "El menú supera el máximo de repeticiones de un plato.",
                    status_code=status_code,
                    details={
                        "dish_id": assignment.dish_id,
                        "max_repeats": settings.max_repeats,
                        "occurrences": counts[assignment.dish_id],
                    },
                )

    @staticmethod
    def _not_found(message: str, **details: object) -> MenuServiceError:
        return MenuServiceError(
            "NOT_FOUND",
            message,
            status_code=404,
            details=details,
        )

    @staticmethod
    def _inconsistent_menu(message: str, **details: object) -> MenuServiceError:
        return MenuServiceError(
            "INCONSISTENT_MENU",
            message,
            status_code=500,
            details=details,
        )
