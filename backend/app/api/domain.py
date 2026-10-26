"""API de ingredientes, platos, alérgenos y preferencias (F2.8)."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.allergens import ALLERGEN_CODES, ALLERGEN_LABELS
from app.api.errors import ApiError
from app.db import get_session
from app.models.dishes import Dish
from app.models.ingredients import Ingredient
from app.models.profile import Exclusion, PantryItem, Profile
from app.schemas.domain import (
    AllergenOut,
    DishDetail,
    DishIngredientOut,
    DishPage,
    DishSummary,
    ExclusionCreate,
    ExclusionOut,
    IngredientOut,
    IngredientPage,
    PantryItemOut,
    PantryUpdate,
    ProductOptionOut,
    ProfileOut,
    ProfileUpdate,
)
from app.services.eligibility import (
    DishEligibility,
    IngredientEligibility,
    evaluate_dishes,
    preferences_from_profile,
)

router = APIRouter(tags=["platos y preferencias"])

SessionDep = Annotated[Session, Depends(get_session)]
_ALLERGEN_ORDER = {code: index for index, code in enumerate(ALLERGEN_CODES)}


def _get_or_create_profile(session: Session) -> Profile:
    profile = session.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1, people=2, days=7, budget_cents=7000, allergen_codes_json=[])
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def _profile_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        people=profile.people,
        days=profile.days,
        budget_cents=profile.budget_cents,
        allergen_codes=list(profile.allergen_codes_json or []),
    )


def _sort_allergens(codes: set[str] | frozenset[str]) -> list[str]:
    return sorted(codes, key=lambda code: (_ALLERGEN_ORDER.get(code, 999), code))


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _ingredient_out(ingredient: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=ingredient.id,
        slug=ingredient.slug,
        name=ingredient.name,
        category=ingredient.category,
        group=ingredient.group,  # type: ignore[arg-type]
        base_unit=ingredient.base_unit,  # type: ignore[arg-type]
        grams_per_unit=ingredient.grams_per_unit,
        protein_source=ingredient.protein_source,
        serving_group=ingredient.serving_group,  # type: ignore[arg-type]
        serving_size_milli=ingredient.serving_size_milli,
        allergens=list(ingredient.allergens_json or []),
        tags=list(ingredient.tags_json or []),
        active=ingredient.active,
    )


def _dish_summary(result: DishEligibility) -> DishSummary:
    dish = result.dish
    return DishSummary(
        id=dish.id,
        slug=dish.slug,
        name=dish.name,
        description=dish.description,
        base_servings=dish.base_servings,
        meal_types=list(dish.meal_types_json or []),  # type: ignore[arg-type]
        protein_sources=list(dish.protein_sources_json or []),
        has_vegetables=dish.has_vegetables,
        light=dish.light,
        carbs=dish.carbs,
        tags=list(dish.tags_json or []),
        allergens=_sort_allergens(result.allergens),
        eligible=result.eligible,
        exclusion_reasons=list(result.reasons),
    )


def _dish_detail(result: DishEligibility) -> DishDetail:
    summary = _dish_summary(result)
    by_ingredient = {item.ingredient.id: item for item in result.ingredients}
    ingredients: list[DishIngredientOut] = []
    for link in result.dish.ingredients:
        ingredient = link.ingredient
        eligibility = by_ingredient.get(
            ingredient.id,
            IngredientEligibility(
                ingredient=ingredient,
                eligible_products=(),
                allergens=frozenset(ingredient.allergens_json or []),
                reason="no_eligible_product",
            ),
        )
        eligible_ids = {mapping.id for mapping in eligibility.eligible_products}
        products = [
            ProductOptionOut(
                id=mapping.product.id,
                external_id=mapping.product.external_id,
                name=mapping.product.name,
                package_quantity_milli=mapping.product.package_quantity_milli,
                package_unit=mapping.product.package_unit,
                package_price_cents=mapping.product.package_price_cents,
                is_default=mapping.is_default,
                priority=mapping.priority,
                allergen_status=mapping.product.allergen_status,
                published=mapping.product.published,
                eligible=mapping.id in eligible_ids,
            )
            for mapping in ingredient.products
        ]
        ingredients.append(
            DishIngredientOut(
                ingredient=_ingredient_out(ingredient),
                quantity_milli=link.quantity_milli,
                products=products,
            )
        )
    return DishDetail(**summary.model_dump(), ingredients=ingredients)


@router.get("/allergens", response_model=list[AllergenOut])
def list_allergens() -> list[AllergenOut]:
    """Lista canónica de alérgenos con etiquetas en español."""
    return [AllergenOut(code=code, name=ALLERGEN_LABELS[code]) for code in ALLERGEN_CODES]


@router.get("/ingredients", response_model=IngredientPage)
def list_ingredients(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    group: Annotated[
        Literal["vegetable", "protein", "carb", "dairy", "fat", "fruit", "pantry", "other"] | None,
        Query(),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IngredientPage:
    """Ingredientes activos, con búsqueda y filtro por grupo."""
    conditions: list[ColumnElement[bool]] = [Ingredient.active.is_(True)]
    if q is not None and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Ingredient.name.ilike(f"%{term}%", escape="\\"))
    if group is not None:
        conditions.append(Ingredient.group == group)
    total = session.scalar(select(func.count()).select_from(Ingredient).where(*conditions)) or 0
    ingredients = session.scalars(
        select(Ingredient)
        .where(*conditions)
        .order_by(Ingredient.name, Ingredient.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return IngredientPage(
        items=[_ingredient_out(ingredient) for ingredient in ingredients],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dishes", response_model=DishPage)
def list_dishes(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    meal_type: Annotated[Literal["lunch", "dinner"] | None, Query()] = None,
    tag: Annotated[str | None, Query(max_length=64)] = None,
    light: Annotated[bool | None, Query()] = None,
    only_eligible: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DishPage:
    """Catálogo de platos con filtros y elegibilidad según preferencias."""
    profile = _get_or_create_profile(session)
    preferences = preferences_from_profile(session, profile)
    results = evaluate_dishes(session, preferences)
    term = _normalize_text(q.strip()) if q and q.strip() else None
    tag_filter = tag.strip() if tag else None
    filtered: list[DishEligibility] = []
    for result in results:
        dish = result.dish
        if (
            term
            and term not in _normalize_text(dish.name)
            and term not in _normalize_text(dish.description or "")
        ):
            continue
        if meal_type is not None and meal_type not in (dish.meal_types_json or []):
            continue
        if tag_filter is not None and tag_filter not in (dish.tags_json or []):
            continue
        if light is not None and dish.light != light:
            continue
        if only_eligible and not result.eligible:
            continue
        filtered.append(result)
    page = filtered[offset : offset + limit]
    return DishPage(
        items=[_dish_summary(result) for result in page],
        total=len(filtered),
        limit=limit,
        offset=offset,
    )


@router.get("/dishes/{dish_id}", response_model=DishDetail)
def get_dish(dish_id: int, session: SessionDep) -> DishDetail:
    """Detalle del plato con composición, alérgenos y productos asociados."""
    profile = _get_or_create_profile(session)
    preferences = preferences_from_profile(session, profile)
    results = evaluate_dishes(session, preferences, dish_id=dish_id)
    if not results:
        raise ApiError("NOT_FOUND", "El plato no existe.", status_code=404)
    return _dish_detail(results[0])


@router.get("/profile", response_model=ProfileOut)
def get_profile(session: SessionDep) -> ProfileOut:
    """Perfil local; se crea con valores por defecto la primera vez."""
    return _profile_out(_get_or_create_profile(session))


@router.put("/profile", response_model=ProfileOut)
def update_profile(payload: ProfileUpdate, session: SessionDep) -> ProfileOut:
    """Actualiza personas, días, presupuesto y alérgenos declarados."""
    profile = _get_or_create_profile(session)
    profile.people = payload.people
    profile.days = payload.days
    profile.budget_cents = payload.budget_cents
    if payload.allergen_codes is not None:
        profile.allergen_codes_json = list(payload.allergen_codes)
    session.commit()
    session.refresh(profile)
    return _profile_out(profile)


def _exclusion_out(exclusion: Exclusion) -> ExclusionOut:
    if exclusion.ingredient_id is not None:
        label = exclusion.ingredient.name if exclusion.ingredient else "Ingrediente eliminado"
        return ExclusionOut(
            id=exclusion.id,
            kind="ingredient",
            ingredient_id=exclusion.ingredient_id,
            dish_id=None,
            tag=None,
            label=label,
        )
    if exclusion.dish_id is not None:
        label = exclusion.dish.name if exclusion.dish else "Plato eliminado"
        return ExclusionOut(
            id=exclusion.id,
            kind="dish",
            ingredient_id=None,
            dish_id=exclusion.dish_id,
            tag=None,
            label=label,
        )
    return ExclusionOut(
        id=exclusion.id,
        kind="tag",
        ingredient_id=None,
        dish_id=None,
        tag=exclusion.tag,
        label=exclusion.tag or "",
    )


def _load_exclusions(session: Session, profile: Profile) -> list[Exclusion]:
    return list(
        session.scalars(
            select(Exclusion)
            .where(Exclusion.profile_id == profile.id)
            .options(joinedload(Exclusion.ingredient), joinedload(Exclusion.dish))
            .order_by(Exclusion.id)
        ).all()
    )


@router.get("/exclusions", response_model=list[ExclusionOut])
def list_exclusions(session: SessionDep) -> list[ExclusionOut]:
    """Exclusiones activas del perfil."""
    profile = _get_or_create_profile(session)
    return [_exclusion_out(exclusion) for exclusion in _load_exclusions(session, profile)]


@router.post("/exclusions", response_model=ExclusionOut, status_code=status.HTTP_201_CREATED)
def create_exclusion(payload: ExclusionCreate, session: SessionDep) -> ExclusionOut:
    """Crea una exclusión por ingrediente, plato o etiqueta."""
    profile = _get_or_create_profile(session)
    if payload.ingredient_id is not None:
        ingredient = session.get(Ingredient, payload.ingredient_id)
        if ingredient is None or not ingredient.active:
            raise ApiError("INVALID_EXCLUSION", "El ingrediente no existe.", status_code=422)
        duplicate = session.scalar(
            select(Exclusion).where(
                Exclusion.profile_id == profile.id,
                Exclusion.ingredient_id == payload.ingredient_id,
            )
        )
        exclusion = Exclusion(profile_id=profile.id, ingredient_id=payload.ingredient_id)
    elif payload.dish_id is not None:
        dish = session.get(Dish, payload.dish_id)
        if dish is None or not dish.active:
            raise ApiError("INVALID_EXCLUSION", "El plato no existe.", status_code=422)
        duplicate = session.scalar(
            select(Exclusion).where(
                Exclusion.profile_id == profile.id, Exclusion.dish_id == payload.dish_id
            )
        )
        exclusion = Exclusion(profile_id=profile.id, dish_id=payload.dish_id)
    else:
        tag = (payload.tag or "").strip()
        available_tags = {
            tag_value
            for dish in session.scalars(select(Dish).where(Dish.active.is_(True))).all()
            for tag_value in (dish.tags_json or [])
        }
        if tag not in available_tags:
            raise ApiError("INVALID_EXCLUSION", "La etiqueta no existe.", status_code=422)
        duplicate = session.scalar(
            select(Exclusion).where(Exclusion.profile_id == profile.id, Exclusion.tag == tag)
        )
        exclusion = Exclusion(profile_id=profile.id, tag=tag)

    if duplicate is not None:
        raise ApiError("INVALID_EXCLUSION", "Esa exclusión ya existe.", status_code=422)
    session.add(exclusion)
    session.commit()
    session.refresh(exclusion)
    return _exclusion_out(exclusion)


@router.delete("/exclusions/{exclusion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exclusion(exclusion_id: int, session: SessionDep) -> Response:
    """Elimina una exclusión del perfil."""
    profile = _get_or_create_profile(session)
    exclusion = session.get(Exclusion, exclusion_id)
    if exclusion is None or exclusion.profile_id != profile.id:
        raise ApiError("NOT_FOUND", "La exclusión no existe.", status_code=404)
    session.delete(exclusion)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _pantry_items(session: Session, profile: Profile) -> list[PantryItem]:
    return list(
        session.scalars(
            select(PantryItem)
            .where(PantryItem.profile_id == profile.id)
            .options(selectinload(PantryItem.ingredient))
            .order_by(PantryItem.id)
        ).all()
    )


@router.get("/pantry", response_model=list[PantryItemOut])
def get_pantry(session: SessionDep) -> list[PantryItemOut]:
    """Despensa por ingrediente y cantidad en unidad base."""
    profile = _get_or_create_profile(session)
    return [
        PantryItemOut(
            id=item.id,
            ingredient=_ingredient_out(item.ingredient),
            quantity_milli=item.quantity_milli,
        )
        for item in _pantry_items(session, profile)
    ]


@router.put("/pantry", response_model=list[PantryItemOut])
def update_pantry(payload: PantryUpdate, session: SessionDep) -> list[PantryItemOut]:
    """Reemplaza la despensa completa del perfil."""
    profile = _get_or_create_profile(session)
    ingredient_ids = [item.ingredient_id for item in payload.items]
    if ingredient_ids:
        found = set(
            session.scalars(select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids))).all()
        )
        missing = set(ingredient_ids) - found
        if missing:
            raise ApiError(
                "VALIDATION_ERROR",
                "La despensa contiene ingredientes inexistentes.",
                status_code=422,
                details={"ingredient_ids": sorted(missing)},
            )
    session.execute(delete(PantryItem).where(PantryItem.profile_id == profile.id))
    for item in payload.items:
        session.add(
            PantryItem(
                profile_id=profile.id,
                ingredient_id=item.ingredient_id,
                quantity_milli=item.quantity_milli,
            )
        )
    session.commit()
    return get_pantry(session)
