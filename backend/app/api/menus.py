"""API de menús (F4.6): generación, ajustes, lista de la compra y exportación.

El router no contiene lógica de negocio: resuelve preferencias, orquesta el
optimizador y ``MenuService`` y traduce los errores de dominio al sobre
homogéneo de la API. Toda lectura usa carga anticipada de relaciones para no
provocar N+1 y nunca expone ``raw_json`` ni datos internos.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.domain import get_or_create_profile
from app.api.errors import ApiError
from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE, get_settings
from app.db import get_session
from app.models.catalog import Category, Product
from app.models.ingredients import Ingredient
from app.models.menu import (
    Menu,
)
from app.models.menu import (
    MenuEntry as MenuEntryModel,
)
from app.models.menu import (
    MenuEntryIngredient as MenuEntryIngredientModel,
)
from app.models.menu import (
    ShoppingItem as ShoppingItemModel,
)
from app.models.profile import Exclusion, PantryItem, Profile
from app.schemas.menu import MenuSettings, PantrySnapshot
from app.schemas.menu_api import (
    ExportFormat,
    MenuDetail,
    MenuEntry,
    MenuEntryComplementCreate,
    MenuEntryExclude,
    MenuEntryIngredient,
    MenuEntryLockUpdate,
    MenuEntrySwap,
    MenuGenerateRequest,
    MenuGenerateResponse,
    MenuPage,
    MenuSummary,
    ShoppingItem,
    ShoppingItemUpdate,
    ShoppingList,
    ShoppingPantryItem,
    ShoppingSection,
)
from app.services.eligibility import (
    PreferenceSnapshot,
    evaluate_dishes,
)
from app.services.menu_service import MenuService, MenuServiceError
from app.services.optimizer import (
    OPTIMIZER_VERSION,
    OptimizationRequest,
    OptimizerError,
    optimize_menu,
    time_limits_from_total,
)

router = APIRouter(prefix="/menus", tags=["menús"])

SessionDep = Annotated[Session, Depends(get_session)]


# ----------------------------------------------------------------------
# Traducción de errores de dominio
# ----------------------------------------------------------------------


def _raise_menu_error(exc: MenuServiceError) -> NoReturn:
    """Convierte un error del servicio de menús en el sobre de la API."""
    details: dict[str, object] = dict(exc.details)
    if exc.reason is not None:
        details["reason"] = exc.reason
    raise ApiError(
        exc.code,
        exc.message,
        status_code=exc.status_code,
        details=details,
    ) from exc


def _raise_optimizer_error(exc: OptimizerError) -> NoReturn:
    """Traduce el contrato del optimizador a códigos HTTP estables."""
    details: dict[str, object] = dict(exc.details)
    if exc.reason is not None:
        details["reason"] = exc.reason
    if exc.code in {"NO_ELIGIBLE_DISHES", "NO_FEASIBLE_MENU"}:
        raise ApiError(exc.code, exc.message, status_code=422, details=details) from exc
    if exc.code == "INVALID_INPUT":
        raise ApiError(
            "VALIDATION_ERROR",
            exc.message,
            status_code=422,
            details=details,
        ) from exc
    raise ApiError(
        "INTERNAL_ERROR",
        exc.message,
        status_code=500,
        details=details,
    ) from exc


# ----------------------------------------------------------------------
# Carga de menús y presentación
# ----------------------------------------------------------------------


def _load_menu(
    session: Session,
    menu_id: int,
    *,
    with_entries: bool = False,
    with_shopping: bool = False,
) -> Menu:
    """Carga un menú con las relaciones que necesita cada respuesta."""
    statement = select(Menu).where(Menu.id == menu_id).execution_options(populate_existing=True)
    if with_entries:
        statement = statement.options(
            selectinload(Menu.entries)
            .selectinload(MenuEntryModel.ingredients)
            .selectinload(MenuEntryIngredientModel.ingredient),
            selectinload(Menu.entries).selectinload(MenuEntryModel.dish),
        )
    if with_shopping:
        statement = statement.options(
            selectinload(Menu.shopping_items)
            .selectinload(ShoppingItemModel.product)
            .selectinload(Product.category)
            .selectinload(Category.parent),
            selectinload(Menu.shopping_items).selectinload(ShoppingItemModel.ingredient),
        )
    menu = session.scalar(statement)
    if menu is None:
        raise ApiError(
            "NOT_FOUND",
            "El menú no existe.",
            status_code=404,
            details={"menu_id": menu_id},
        )
    return menu


def _require_entry(session: Session, menu: Menu, entry_id: int) -> MenuEntryModel:
    entry = session.scalar(
        select(MenuEntryModel).where(
            MenuEntryModel.id == entry_id,
            MenuEntryModel.menu_id == menu.id,
        )
    )
    if entry is None:
        raise ApiError(
            "NOT_FOUND",
            "La entrada no existe en este menú.",
            status_code=404,
            details={"menu_id": menu.id, "entry_id": entry_id},
        )
    return entry


def _settings(menu: Menu) -> MenuSettings:
    try:
        return MenuSettings.model_validate(menu.settings_json)
    except ValidationError as exc:
        raise ApiError(
            "INCONSISTENT_MENU",
            "El snapshot de preferencias del menú no es válido.",
            status_code=500,
            details={
                "menu_id": menu.id,
                "errors": exc.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                ),
            },
        ) from exc


def _menu_summary(menu: Menu) -> MenuSummary:
    price_delta = (
        menu.revalidated_ticket_cents - menu.previous_ticket_cents
        if menu.revalidated_ticket_cents is not None and menu.previous_ticket_cents is not None
        else None
    )
    return MenuSummary(
        id=menu.id,
        people=menu.people,
        days=menu.days,
        budget_cents=menu.budget_cents,
        status=menu.status,  # type: ignore[arg-type]
        price_status=menu.price_status,  # type: ignore[arg-type]
        timed_out=menu.timed_out,
        ticket_cents=menu.ticket_cents,
        consumption_cents=menu.consumption_cents,
        pantry_consumption_cents=menu.pantry_consumption_cents,
        leftover_value_cents=menu.leftover_value_cents,
        revalidated_ticket_cents=menu.revalidated_ticket_cents,
        previous_ticket_cents=menu.previous_ticket_cents,
        price_delta_cents=price_delta,
        revalidated_at=menu.revalidated_at,
        violations=menu.violations,
        relaxations=list(menu.relaxation_codes_json or []),
        postal_code=menu.postal_code,
        warehouse=menu.warehouse,
        prices_captured_at=menu.prices_captured_at,
        optimizer_version=menu.optimizer_version,
        created_at=menu.created_at,
        updated_at=menu.updated_at,
    )


def _entry_out(entry: MenuEntryModel) -> MenuEntry:
    return MenuEntry(
        id=entry.id,
        day_index=entry.day_index,
        slot=entry.slot,  # type: ignore[arg-type]
        course=entry.course,  # type: ignore[arg-type]
        dish_id=entry.dish_id,
        dish_name=entry.dish_name,
        locked=entry.locked,
        entry_consumption_cents=entry.entry_consumption_cents,
        protein_source=entry.entry_protein_source,
        tags=list(entry.dish.tags_json or []),
        ingredients=[
            MenuEntryIngredient(
                ingredient_id=row.ingredient_id,
                ingredient_name=row.ingredient.name,
                base_unit=row.ingredient.base_unit,  # type: ignore[arg-type]
                used_milli=row.used_milli,
                consumption_cents=row.consumption_cents,
                product_id=row.product_id,
            )
            for row in entry.ingredients
        ],
    )


def _menu_detail(session: Session, menu_id: int) -> MenuDetail:
    return _detail_out(_load_menu(session, menu_id, with_entries=True))


def _detail_out(menu: Menu) -> MenuDetail:
    summary = _menu_summary(menu)
    entries = sorted(
        (_entry_out(entry) for entry in menu.entries),
        key=lambda entry: (
            entry.day_index,
            0 if entry.slot == "lunch" else 1,
            entry.id,
        ),
    )
    return MenuDetail(
        **summary.model_dump(),
        settings=_settings(menu),
        entries=entries,
    )


def _round_half_up_div(numerator: int, denominator: int) -> int:
    """División entera con redondeo half-up para importes no negativos."""
    if denominator <= 0:
        raise ValueError("El divisor debe ser positivo.")
    return (numerator * 2 + denominator) // (2 * denominator)


def _item_section(product: Product) -> tuple[int, str]:
    category = product.category
    section = category.parent if category.parent is not None else category
    return section.id, section.name


def _shopping_item_out(item: ShoppingItemModel) -> ShoppingItem:
    product = item.product
    return ShoppingItem(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name,
        brand=product.brand,
        ingredient_id=item.ingredient_id,
        ingredient_name=item.ingredient.name,
        packages=item.packages,
        package_quantity_milli=item.package_quantity_milli,
        # El snapshot no guarda la unidad del paquete; al comprar, el formato
        # siempre comparte la unidad base del ingrediente.
        package_unit=item.ingredient.base_unit,
        package_price_cents=item.package_price_cents,
        subtotal_cents=item.subtotal_cents,
        pantry_quantity_milli=item.pantry_quantity_milli,
        checked=item.checked,
    )


def _pantry_items(session: Session, settings: MenuSettings) -> list[ShoppingPantryItem]:
    if not settings.pantry:
        return []
    ingredient_ids = {item.ingredient_id for item in settings.pantry}
    ingredients = {
        ingredient.id: ingredient
        for ingredient in session.scalars(
            select(Ingredient).where(Ingredient.id.in_(ingredient_ids))
        ).all()
    }
    items: list[ShoppingPantryItem] = []
    for snapshot in settings.pantry:
        ingredient = ingredients.get(snapshot.ingredient_id)
        if ingredient is None:
            continue
        items.append(
            ShoppingPantryItem(
                ingredient_id=snapshot.ingredient_id,
                ingredient_name=ingredient.name,
                base_unit=ingredient.base_unit,  # type: ignore[arg-type]
                quantity_milli=snapshot.quantity_milli,
            )
        )
    return items


def _shopping_list_out(session: Session, menu: Menu) -> ShoppingList:
    settings = _settings(menu)
    grouped: dict[tuple[int, str], list[ShoppingItem]] = {}
    for item in menu.shopping_items:
        section_id, section_name = _item_section(item.product)
        grouped.setdefault((section_id, section_name), []).append(_shopping_item_out(item))

    sections: list[ShoppingSection] = []
    for (section_id, section_name), items in sorted(
        grouped.items(),
        key=lambda entry: (entry[0][1].casefold(), entry[0][0]),
    ):
        items.sort(key=lambda item: (item.product_name.casefold(), item.id))
        sections.append(
            ShoppingSection(
                section_id=section_id,
                section_name=section_name,
                subtotal_cents=sum(item.subtotal_cents for item in items),
                items=items,
            )
        )

    entries = list(menu.shopping_items)
    return ShoppingList(
        menu_id=menu.id,
        status=menu.status,  # type: ignore[arg-type]
        price_status=menu.price_status,  # type: ignore[arg-type]
        timed_out=menu.timed_out,
        people=menu.people,
        days=menu.days,
        budget_cents=menu.budget_cents,
        ticket_cents=menu.ticket_cents,
        consumption_cents=menu.consumption_cents,
        pantry_consumption_cents=menu.pantry_consumption_cents,
        leftover_value_cents=menu.leftover_value_cents,
        revalidated_ticket_cents=menu.revalidated_ticket_cents,
        previous_ticket_cents=menu.previous_ticket_cents,
        price_delta_cents=(
            menu.revalidated_ticket_cents - menu.previous_ticket_cents
            if menu.revalidated_ticket_cents is not None and menu.previous_ticket_cents is not None
            else None
        ),
        revalidated_at=menu.revalidated_at,
        checked_total_cents=sum(item.subtotal_cents for item in entries if item.checked),
        item_count=len(entries),
        checked_count=sum(1 for item in entries if item.checked),
        cost_per_meal_cents=_round_half_up_div(menu.ticket_cents, menu.days * 2),
        cost_per_day_cents=_round_half_up_div(menu.ticket_cents, menu.days),
        cost_per_person_day_cents=_round_half_up_div(
            menu.ticket_cents,
            menu.days * menu.people,
        ),
        postal_code=menu.postal_code,
        warehouse=menu.warehouse,
        prices_captured_at=menu.prices_captured_at,
        updated_at=menu.updated_at,
        sections=sections,
        pantry_items=_pantry_items(session, settings),
    )


def _load_shopping_list(session: Session, menu_id: int) -> ShoppingList:
    menu = _load_menu(session, menu_id, with_shopping=True)
    return _shopping_list_out(session, menu)


# ----------------------------------------------------------------------
# Resolución de preferencias y generación
# ----------------------------------------------------------------------


def _profile_exclusions(
    session: Session,
    profile: Profile,
) -> tuple[list[int], list[int], list[str]]:
    exclusions = session.scalars(
        select(Exclusion).where(Exclusion.profile_id == profile.id).order_by(Exclusion.id)
    ).all()
    ingredient_ids = [
        int(exclusion.ingredient_id)
        for exclusion in exclusions
        if exclusion.ingredient_id is not None
    ]
    dish_ids = [int(exclusion.dish_id) for exclusion in exclusions if exclusion.dish_id is not None]
    tags = [str(exclusion.tag) for exclusion in exclusions if exclusion.tag is not None]
    return ingredient_ids, dish_ids, tags


def _profile_pantry(session: Session, profile: Profile) -> list[PantrySnapshot]:
    items = session.scalars(
        select(PantryItem).where(PantryItem.profile_id == profile.id).order_by(PantryItem.id)
    ).all()
    return [
        PantrySnapshot(
            ingredient_id=item.ingredient_id,
            quantity_milli=item.quantity_milli,
        )
        for item in items
    ]


def _validate_pantry(session: Session, pantry: list[PantrySnapshot]) -> None:
    ingredient_ids = {item.ingredient_id for item in pantry}
    if not ingredient_ids:
        return
    found = set(
        session.scalars(select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids))).all()
    )
    missing = ingredient_ids - found
    if missing:
        raise ApiError(
            "VALIDATION_ERROR",
            "La despensa contiene ingredientes inexistentes.",
            status_code=422,
            details={"ingredient_ids": sorted(missing)},
        )


def _resolve_settings(
    session: Session,
    profile: Profile,
    payload: MenuGenerateRequest,
) -> MenuSettings:
    """Combina los valores explícitos con el perfil; ``None`` hereda."""
    if payload.allergen_codes is None:
        allergen_codes = list(profile.allergen_codes_json or [])
    else:
        allergen_codes = list(payload.allergen_codes)

    profile_ingredients, profile_dishes, profile_tags = _profile_exclusions(session, profile)
    excluded_ingredient_ids = (
        profile_ingredients
        if payload.excluded_ingredient_ids is None
        else list(payload.excluded_ingredient_ids)
    )
    excluded_dish_ids = (
        profile_dishes if payload.excluded_dish_ids is None else list(payload.excluded_dish_ids)
    )
    excluded_tags = profile_tags if payload.excluded_tags is None else list(payload.excluded_tags)

    pantry = _profile_pantry(session, profile) if payload.pantry is None else list(payload.pantry)
    _validate_pantry(session, pantry)

    try:
        return MenuSettings(
            allergen_codes=allergen_codes,
            excluded_ingredient_ids=excluded_ingredient_ids,
            excluded_dish_ids=excluded_dish_ids,
            excluded_tags=excluded_tags,
            pantry=pantry,
            max_repeats=payload.max_repeats,
            optimizer_version=OPTIMIZER_VERSION,
        )
    except ValidationError as exc:
        raise ApiError(
            "VALIDATION_ERROR",
            "Las preferencias del menú no son válidas.",
            status_code=422,
            details={
                "errors": exc.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                ),
            },
        ) from exc


def _preferences(settings: MenuSettings) -> PreferenceSnapshot:
    return PreferenceSnapshot(
        allergen_codes=frozenset(settings.allergen_codes),
        excluded_ingredient_ids=frozenset(settings.excluded_ingredient_ids),
        excluded_dish_ids=frozenset(settings.excluded_dish_ids),
        excluded_tags=frozenset(settings.excluded_tags),
    )


def _prices_captured_at(session: Session) -> datetime | None:
    value = session.scalar(select(func.max(Product.last_seen_at)))
    return value if isinstance(value, datetime) else None


@router.post("/generate", response_model=MenuGenerateResponse)
def generate_menu(
    payload: MenuGenerateRequest,
    session: SessionDep,
) -> MenuGenerateResponse:
    """Genera un menú o devuelve un preview de inviabilidad/timeout sin persistir."""
    profile = get_or_create_profile(session)
    settings = _resolve_settings(session, profile, payload)
    preferences = _preferences(settings)
    eligibility = evaluate_dishes(session, preferences)

    stage1, stage2, fallback = time_limits_from_total(get_settings().optimizer_time_limit_seconds)
    request = OptimizationRequest(
        people=payload.people,
        days=payload.days,
        budget_cents=payload.budget_cents,
        preferences=preferences,
        pantry={item.ingredient_id: item.quantity_milli for item in settings.pantry},
        max_repeats=settings.max_repeats,
        stage1_seconds=stage1,
        stage2_seconds=stage2,
        fallback_seconds=fallback,
    )
    try:
        result = optimize_menu(eligibility, request)
    except OptimizerError as exc:
        _raise_optimizer_error(exc)

    prices_captured_at = _prices_captured_at(session)

    if result.status == "infeasible":
        return MenuGenerateResponse(
            status="infeasible",
            is_preview=True,
            reason="budget",
            menu_id=None,
            people=payload.people,
            days=payload.days,
            budget_cents=payload.budget_cents,
            ticket_cents=None,
            consumption_cents=None,
            pantry_consumption_cents=None,
            leftover_value_cents=None,
            minimum_ticket_cents=result.minimum_ticket_cents,
            minimum_is_estimate=result.minimum_is_estimate,
            shortfall_cents=result.shortfall_cents,
            relaxations=list(result.relaxation_codes),
            suggestions=list(result.suggestions),
            price_status=None,
            timed_out=result.timed_out,
            postal_code=POSTAL_CODE,
            warehouse=EXPECTED_WAREHOUSE,
            prices_captured_at=prices_captured_at,
            entries=[],
        )
    if result.status == "timeout":
        return MenuGenerateResponse(
            status="timeout",
            is_preview=False,
            reason="timeout",
            menu_id=None,
            people=payload.people,
            days=payload.days,
            budget_cents=payload.budget_cents,
            ticket_cents=None,
            consumption_cents=None,
            pantry_consumption_cents=None,
            leftover_value_cents=None,
            minimum_ticket_cents=None,
            minimum_is_estimate=False,
            shortfall_cents=0,
            relaxations=list(result.relaxation_codes),
            suggestions=[],
            price_status=None,
            timed_out=True,
            postal_code=POSTAL_CODE,
            warehouse=EXPECTED_WAREHOUSE,
            prices_captured_at=prices_captured_at,
            entries=[],
        )

    try:
        menu = MenuService(session).generate(
            profile_id=profile.id,
            people=payload.people,
            days=payload.days,
            budget_cents=payload.budget_cents,
            settings=settings,
            optimization=result,
            prices_captured_at=prices_captured_at,
        )
    except MenuServiceError as exc:
        _raise_menu_error(exc)

    detail = _menu_detail(session, menu.id)
    return MenuGenerateResponse(
        status=menu.status,  # type: ignore[arg-type]
        is_preview=False,
        reason=None,
        menu_id=menu.id,
        people=payload.people,
        days=payload.days,
        budget_cents=payload.budget_cents,
        ticket_cents=menu.ticket_cents,
        consumption_cents=menu.consumption_cents,
        pantry_consumption_cents=menu.pantry_consumption_cents,
        leftover_value_cents=menu.leftover_value_cents,
        minimum_ticket_cents=None,
        minimum_is_estimate=False,
        shortfall_cents=0,
        relaxations=list(menu.relaxation_codes_json or []),
        suggestions=[],
        price_status=menu.price_status,  # type: ignore[arg-type]
        timed_out=menu.timed_out,
        postal_code=POSTAL_CODE,
        warehouse=EXPECTED_WAREHOUSE,
        prices_captured_at=prices_captured_at,
        entries=detail.entries,
    )


# ----------------------------------------------------------------------
# Historial y detalle
# ----------------------------------------------------------------------


@router.get("", response_model=MenuPage)
def list_menus(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MenuPage:
    """Historial paginado, del menú más reciente al más antiguo."""
    total = session.scalar(select(func.count()).select_from(Menu)) or 0
    menus = session.scalars(
        select(Menu).order_by(Menu.created_at.desc(), Menu.id.desc()).limit(limit).offset(offset)
    ).all()
    return MenuPage(
        items=[_menu_summary(menu) for menu in menus],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{menu_id}", response_model=MenuDetail)
def get_menu(menu_id: int, session: SessionDep) -> MenuDetail:
    """Detalle completo del menú con snapshot y entradas."""
    return _menu_detail(session, menu_id)


# ----------------------------------------------------------------------
# Ajustes del menú
# ----------------------------------------------------------------------


@router.patch("/{menu_id}/entries/{entry_id}", response_model=MenuDetail)
def update_entry_lock(
    menu_id: int,
    entry_id: int,
    payload: MenuEntryLockUpdate,
    session: SessionDep,
) -> MenuDetail:
    """Bloquea o desbloquea una entrada sin recalcular el menú."""
    menu = _load_menu(session, menu_id)
    entry = _require_entry(session, menu, entry_id)
    entry.locked = payload.locked
    session.commit()
    return _menu_detail(session, menu.id)


@router.post("/{menu_id}/entries/{entry_id}/swap", response_model=MenuDetail)
def swap_entry(
    menu_id: int,
    entry_id: int,
    payload: MenuEntrySwap,
    session: SessionDep,
) -> MenuDetail:
    """Sustituye el plato de una entrada y recalcula ticket y lista."""
    try:
        menu = MenuService(session).swap_entry(menu_id, entry_id, payload.dish_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


@router.post("/{menu_id}/entries/{entry_id}/complement", response_model=MenuDetail)
def add_complement(
    menu_id: int,
    entry_id: int,
    payload: MenuEntryComplementCreate,
    session: SessionDep,
) -> MenuDetail:
    """Añade un acompañamiento al hueco del principal indicado."""
    try:
        menu = MenuService(session).add_complement(menu_id, entry_id, payload.dish_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


@router.delete("/{menu_id}/entries/{entry_id}/complement", response_model=MenuDetail)
def remove_complement(menu_id: int, entry_id: int, session: SessionDep) -> MenuDetail:
    """Quita el acompañamiento del hueco del principal indicado."""
    try:
        menu = MenuService(session).remove_complement(menu_id, entry_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


@router.post("/{menu_id}/entries/{entry_id}/exclude", response_model=MenuDetail)
def exclude_entry(
    menu_id: int,
    entry_id: int,
    payload: MenuEntryExclude,
    session: SessionDep,
) -> MenuDetail:
    """Excluye el plato del menú o del perfil y busca un reemplazo elegible."""
    try:
        menu = MenuService(session).exclude_entry(menu_id, entry_id, payload.scope)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


@router.post("/{menu_id}/regenerate", response_model=MenuDetail)
def regenerate_menu(menu_id: int, session: SessionDep) -> MenuDetail:
    """Regenera el menú conservando bloqueos y snapshot de preferencias."""
    try:
        menu = MenuService(session).regenerate(menu_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


@router.post("/{menu_id}/revalidate", response_model=MenuDetail)
def revalidate_menu(menu_id: int, session: SessionDep) -> MenuDetail:
    """Recalcula precios y marca ``stale`` si el ticket ya no cabe."""
    try:
        menu = MenuService(session).revalidate(menu_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _menu_detail(session, menu.id)


# ----------------------------------------------------------------------
# Lista de la compra
# ----------------------------------------------------------------------


@router.get("/{menu_id}/shopping-list", response_model=ShoppingList)
def get_shopping_list(menu_id: int, session: SessionDep) -> ShoppingList:
    """Lista agrupada por sección con totales y despensa del snapshot."""
    return _load_shopping_list(session, menu_id)


@router.patch(
    "/{menu_id}/shopping-list/items/{item_id}",
    response_model=ShoppingList,
)
def update_shopping_item(
    menu_id: int,
    item_id: int,
    payload: ShoppingItemUpdate,
    session: SessionDep,
) -> ShoppingList:
    """Marca una línea o aplica «ya lo tengo» y devuelve la lista recalculada."""
    menu = _load_menu(session, menu_id)
    item = session.get(ShoppingItemModel, item_id)
    if item is None or item.menu_id != menu.id:
        raise ApiError(
            "NOT_FOUND",
            "La línea de compra no existe en este menú.",
            status_code=404,
            details={"menu_id": menu.id, "item_id": item_id},
        )
    service = MenuService(session)
    try:
        if payload.checked is not None:
            service.set_shopping_item_checked(menu.id, item_id, payload.checked)
        else:
            service.set_pantry_sufficient(menu.id, item.ingredient_id)
    except MenuServiceError as exc:
        _raise_menu_error(exc)
    return _load_shopping_list(session, menu.id)


# ----------------------------------------------------------------------
# Exportación
# ----------------------------------------------------------------------


def _euros(cents: int) -> str:
    amount = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f} €".replace(".", ",")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "sin datos"
    resolved = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return resolved.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _quantity(value_milli: int, unit: str) -> str:
    """Cantidad legible en unidades base, sin ``float`` para el valor exacto."""
    amount = (Decimal(value_milli) / Decimal(1000)).normalize()
    text = format(amount, "f").replace(".", ",")
    suffix = "ud" if unit == "unit" else unit
    return f"{text} {suffix}"


def _entry_cell(entry: MenuEntry | None) -> str:
    if entry is None:
        return "—"
    return _markdown_cell(f"{entry.dish_name} ({_euros(entry.entry_consumption_cents)})")


def _slot_cell(entries: list[MenuEntry]) -> str:
    """Celda de un hueco: principal y, si existe, acompañamiento."""
    if not entries:
        return "—"
    ordered = sorted(entries, key=lambda entry: 0 if entry.course == "main" else 1)
    return " + ".join(_entry_cell(entry) for entry in ordered)


def _markdown_export(detail: MenuDetail, shopping: ShoppingList) -> str:
    lines = [
        f"# Menú #{detail.id}",
        "",
        f"- Personas: {detail.people}",
        f"- Días: {detail.days}",
        f"- Presupuesto: {_euros(detail.budget_cents)}",
        f"- Ticket: {_euros(detail.ticket_cents)}",
        f"- Consumo: {_euros(detail.consumption_cents)}",
        f"- Despensa: {_euros(detail.pantry_consumption_cents)}",
        f"- Sobras: {_euros(detail.leftover_value_cents)}",
        f"- Estado: {detail.status}",
        f"- Precios: {detail.price_status} ({_format_datetime(detail.prices_captured_at)})",
        f"- CP: {detail.postal_code} · Almacén: {detail.warehouse}",
        "",
        "## Días",
        "",
        "| Día | Comida | Cena |",
        "| --- | --- | --- |",
    ]
    by_day: dict[int, dict[str, list[MenuEntry]]] = {}
    for entry in detail.entries:
        by_day.setdefault(entry.day_index, {}).setdefault(entry.slot, []).append(entry)
    for day_index in range(detail.days):
        slots = by_day.get(day_index, {})
        lines.append(
            f"| {day_index + 1} | {_slot_cell(slots.get('lunch', []))} "
            f"| {_slot_cell(slots.get('dinner', []))} |"
        )

    lines.extend(["", "## Lista de la compra", ""])
    for section in shopping.sections:
        lines.append(f"### {section.section_name}")
        lines.append("")
        for item in section.items:
            lines.append(
                f"- {item.product_name}: {item.packages} × "
                f"{_quantity(item.package_quantity_milli, item.package_unit)} — "
                f"{_euros(item.subtotal_cents)}"
            )
        lines.append("")
        lines.append(f"Subtotal: {_euros(section.subtotal_cents)}")
        lines.append("")

    lines.append(f"**Total: {_euros(shopping.ticket_cents)}**")
    lines.append("")
    return "\n".join(lines)


def _formula_safe(value: str) -> str:
    """Neutraliza fórmulas de hoja de cálculo en celdas de texto."""
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _csv_export(shopping: ShoppingList) -> str:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "seccion",
            "producto",
            "ingrediente",
            "paquetes",
            "cantidad_paquete",
            "unidad",
            "precio_paquete_cents",
            "subtotal_cents",
            "marcado",
        ]
    )
    for section in shopping.sections:
        for item in section.items:
            writer.writerow(
                [
                    _formula_safe(section.section_name),
                    _formula_safe(item.product_name),
                    _formula_safe(item.ingredient_name),
                    item.packages,
                    item.package_quantity_milli,
                    _formula_safe(item.package_unit),
                    item.package_price_cents,
                    item.subtotal_cents,
                    _formula_safe("si" if item.checked else "no"),
                ]
            )
    return buffer.getvalue()


@router.get("/{menu_id}/export")
def export_menu(
    menu_id: int,
    session: SessionDep,
    format: Annotated[ExportFormat, Query()] = "markdown",
) -> Response:
    """Exporta el menú y la lista como markdown o CSV con fórmulas neutralizadas."""
    menu = _load_menu(session, menu_id, with_entries=True, with_shopping=True)
    shopping = _shopping_list_out(session, menu)
    if format == "csv":
        return Response(
            content=_csv_export(shopping),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="menu-{menu.id}.csv"',
            },
        )

    detail = _detail_out(menu)
    return Response(
        content=_markdown_export(detail, shopping),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="menu-{menu.id}.md"',
        },
    )
