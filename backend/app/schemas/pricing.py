"""Esquemas del preview de coste (F3.5).

El preview es de coste: no aplica filtros de alérgenos ni persiste menús. Las
cantidades están en milésimas de la unidad base y los importes en céntimos.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.domain import IngredientOut, PantryItemIn


class PreviewDishIn(BaseModel):
    """Una aparición de un plato en el menú que se quiere valorar."""

    dish_id: int = Field(ge=1)


class PricingPreviewIn(BaseModel):
    """Personas, platos y despensa opcional para calcular el coste."""

    people: int = Field(ge=1, le=10)
    dishes: list[PreviewDishIn] = Field(min_length=1, max_length=100)
    #: Si se omite, se usa la despensa del perfil local.
    pantry: list[PantryItemIn] | None = Field(default=None, max_length=200)

    @field_validator("pantry")
    @classmethod
    def _unique_ingredients(cls, value: list[PantryItemIn] | None) -> list[PantryItemIn] | None:
        if value is None:
            return None
        ingredient_ids = [item.ingredient_id for item in value]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Hay ingredientes repetidos en la despensa.")
        return value


class PricingProductLineOut(BaseModel):
    """Formato comprado para un ingrediente, con su consumo y sobras."""

    product_id: int
    external_id: str
    name: str
    package_quantity_milli: int
    package_unit: str
    package_price_cents: int
    packages: int
    quantity_milli: int
    subtotal_cents: int
    used_milli: int
    leftover_milli: int


class PricingIngredientOut(BaseModel):
    """Coste, consumo y sobras de un ingrediente."""

    ingredient: IngredientOut
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
    products: list[PricingProductLineOut] = Field(default_factory=list)


class PricingDishOut(BaseModel):
    """Coste de una aparición concreta de un plato."""

    index: int
    dish_id: int
    dish_name: str
    servings: int
    consumption_cents: int
    per_serving_cents: int


class PricingPreviewOut(BaseModel):
    """Resultado del cálculo de coste sin persistencia."""

    people: int
    dish_count: int
    ticket_cents: int
    consumption_cents: int
    pantry_consumption_cents: int
    leftover_value_cents: int
    dishes: list[PricingDishOut]
    ingredients: list[PricingIngredientOut]
