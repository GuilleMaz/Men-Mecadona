"""API del preview de coste (F3.5).

Calcula ticket, consumo, despensa y sobras de un conjunto de platos sin
persistir ningún menú y sin aplicar filtros de alérgenos: es un preview de
coste. La despensa puede venir en la petición o tomarse del perfil local.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import ApiError
from app.api.presenters import ingredient_out
from app.db import get_session
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import Ingredient, IngredientProduct
from app.models.profile import PantryItem, Profile
from app.schemas.pricing import (
    PricingDishOut,
    PricingIngredientOut,
    PricingPreviewIn,
    PricingPreviewOut,
    PricingProductLineOut,
)
from app.services.pricing import BasketCost, PricingError, price_basket

router = APIRouter(tags=["coste"])

SessionDep = Annotated[Session, Depends(get_session)]


def _load_dishes(session: Session, dish_ids: set[int]) -> dict[int, Dish]:
    """Carga platos activos con composición, productos y precios."""
    if not dish_ids:
        return {}
    statement = (
        select(Dish)
        .where(Dish.active.is_(True), Dish.id.in_(dish_ids))
        .options(
            selectinload(Dish.ingredients)
            .selectinload(DishIngredient.ingredient)
            .selectinload(Ingredient.products)
            .selectinload(IngredientProduct.product)
        )
    )
    return {dish.id: dish for dish in session.scalars(statement).all()}


def _resolve_pantry(session: Session, payload: PricingPreviewIn) -> dict[int, int]:
    """Despensa explícita del preview o, si se omite, la del perfil local."""
    if payload.pantry is not None:
        ingredient_ids = {item.ingredient_id for item in payload.pantry}
        if ingredient_ids:
            found = set(
                session.scalars(
                    select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids))
                ).all()
            )
            missing = ingredient_ids - found
            if missing:
                raise ApiError(
                    "VALIDATION_ERROR",
                    "La despensa contiene ingredientes inexistentes.",
                    status_code=422,
                    details={"ingredient_ids": sorted(missing)},
                )
        return {item.ingredient_id: item.quantity_milli for item in payload.pantry}

    profile = session.get(Profile, 1)
    if profile is None:
        return {}
    items = session.scalars(select(PantryItem).where(PantryItem.profile_id == profile.id)).all()
    return {item.ingredient_id: item.quantity_milli for item in items}


def _raise_pricing_error(exc: PricingError) -> NoReturn:
    """Traduce un error del motor puro al contrato HTTP de la API."""
    if exc.code == "PRODUCT_UNAVAILABLE":
        raise ApiError(
            "PRODUCT_UNAVAILABLE",
            exc.message,
            status_code=409,
            details=exc.details,
        )
    if exc.code == "INVALID_INPUT":
        raise ApiError(
            "VALIDATION_ERROR",
            exc.message,
            status_code=422,
            details=exc.details,
        )
    raise ApiError(
        "INTERNAL_ERROR",
        "No se pudo calcular el coste del preview.",
        status_code=500,
        details=exc.details,
    )


def _preview_out(basket: BasketCost) -> PricingPreviewOut:
    return PricingPreviewOut(
        people=basket.people,
        dish_count=basket.dish_count,
        ticket_cents=basket.ticket_cents,
        consumption_cents=basket.consumption_cents,
        pantry_consumption_cents=basket.pantry_consumption_cents,
        leftover_value_cents=basket.leftover_value_cents,
        dishes=[
            PricingDishOut(
                index=dish_cost.index,
                dish_id=dish_cost.dish.id,
                dish_name=dish_cost.dish.name,
                servings=dish_cost.servings,
                consumption_cents=dish_cost.consumption_cents,
                per_serving_cents=dish_cost.per_serving_cents,
            )
            for dish_cost in basket.dishes
        ],
        ingredients=[
            PricingIngredientOut(
                ingredient=ingredient_out(cost.ingredient),
                need_milli=cost.need_milli,
                pantry_milli=cost.pantry_milli,
                pantry_used_milli=cost.pantry_used_milli,
                net_need_milli=cost.net_need_milli,
                purchased_milli=cost.purchased_milli,
                leftover_milli=cost.leftover_milli,
                ticket_cents=cost.ticket_cents,
                consumption_cents=cost.consumption_cents,
                pantry_consumption_cents=cost.pantry_consumption_cents,
                leftover_value_cents=cost.leftover_value_cents,
                products=[
                    PricingProductLineOut(
                        product_id=line.product.product_id,
                        external_id=line.product.external_id,
                        name=line.product.name,
                        package_quantity_milli=line.product.package_quantity_milli,
                        package_unit=line.product.package_unit,
                        package_price_cents=line.product.package_price_cents,
                        packages=line.packages,
                        quantity_milli=line.quantity_milli,
                        subtotal_cents=line.subtotal_cents,
                        used_milli=line.used_milli,
                        leftover_milli=line.leftover_milli,
                    )
                    for line in cost.lines
                ],
            )
            for cost in basket.ingredients
        ],
    )


@router.post("/pricing/preview", response_model=PricingPreviewOut)
def preview_pricing(payload: PricingPreviewIn, session: SessionDep) -> PricingPreviewOut:
    """Calcula el coste de un conjunto de platos sin persistir nada."""
    unique_ids = {entry.dish_id for entry in payload.dishes}
    dishes = _load_dishes(session, unique_ids)
    missing = unique_ids - dishes.keys()
    if missing:
        raise ApiError(
            "NOT_FOUND",
            "Algún plato del preview no existe.",
            status_code=404,
            details={"dish_ids": sorted(missing)},
        )

    pantry = _resolve_pantry(session, payload)
    occurrences = [dishes[entry.dish_id] for entry in payload.dishes]
    try:
        basket = price_basket(occurrences, payload.people, pantry)
    except PricingError as exc:
        _raise_pricing_error(exc)
    return _preview_out(basket)
