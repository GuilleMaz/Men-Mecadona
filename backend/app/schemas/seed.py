"""Validación de los YAML de ingredientes y platos (F2.2, F2.5 y F2.7)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.allergens import ALLERGEN_CODE_SET

IngredientGroup = Literal[
    "vegetable", "protein", "carb", "dairy", "fat", "fruit", "pantry", "other"
]
ServingGroup = Literal["vegetable", "protein", "carb", "none"]
BaseUnit = Literal["g", "ml", "unit"]
MealType = Literal["lunch", "dinner"]


class SeedProduct(BaseModel):
    """Producto de Mercadona referenciado por su `external_id` estable."""

    model_config = ConfigDict(extra="forbid")

    external_id: str = Field(min_length=1, max_length=64)
    priority: int = Field(ge=1)
    is_default: bool = False


class SeedIngredient(BaseModel):
    """Ingrediente del YAML, con su mapeo explícito a 1-3 productos."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=64)
    group: IngredientGroup
    base_unit: BaseUnit
    grams_per_unit: int | None = Field(default=None, gt=0)
    protein_source: str | None = Field(default=None, max_length=32)
    serving_group: ServingGroup = "none"
    serving_size_milli: int = Field(gt=0)
    allergens: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    products: list[SeedProduct] = Field(min_length=1, max_length=3)

    @field_validator("allergens")
    @classmethod
    def _valid_allergens(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - ALLERGEN_CODE_SET)
        if unknown:
            raise ValueError(f"Alérgenos desconocidos: {', '.join(unknown)}")
        if len(value) != len(set(value)):
            raise ValueError("Hay alérgenos repetidos.")
        return value

    @field_validator("tags")
    @classmethod
    def _unique_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Hay etiquetas repetidas.")
        return value

    @model_validator(mode="after")
    def _valid_products(self) -> SeedIngredient:
        priorities = [product.priority for product in self.products]
        if len(priorities) != len(set(priorities)):
            raise ValueError("Hay prioridades de producto repetidas.")
        external_ids = [product.external_id for product in self.products]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("Hay productos repetidos en el ingrediente.")
        defaults = sum(1 for product in self.products if product.is_default)
        if defaults != 1:
            raise ValueError("Cada ingrediente debe tener exactamente un producto por defecto.")
        if self.grams_per_unit is not None and self.base_unit != "unit":
            raise ValueError("grams_per_unit solo tiene sentido con base_unit='unit'.")
        return self


class SeedDishIngredient(BaseModel):
    """Ingrediente y cantidad de un plato, en su unidad base humana."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str = Field(min_length=2, max_length=80)
    quantity: Decimal = Field(gt=0)
    unit: BaseUnit


class SeedDish(BaseModel):
    """Plato del YAML. Los flags se comparan con la composición en el validador."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    base_servings: int = Field(gt=0, le=20)
    meal_types: list[MealType] = Field(min_length=1)
    protein_sources: list[str] = Field(default_factory=list)
    has_vegetables: bool
    light: bool
    carbs: str | None = Field(default=None, max_length=32)
    tags: list[str] = Field(default_factory=list)
    ingredients: list[SeedDishIngredient] = Field(min_length=4, max_length=8)

    @field_validator("meal_types")
    @classmethod
    def _unique_meals(cls, value: list[MealType]) -> list[MealType]:
        if len(value) != len(set(value)):
            raise ValueError("Hay tipos de comida repetidos.")
        return value

    @field_validator("protein_sources", "tags")
    @classmethod
    def _unique_strings(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Hay valores repetidos.")
        return value

    @model_validator(mode="after")
    def _unique_ingredients(self) -> SeedDish:
        slugs = [item.ingredient for item in self.ingredients]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Hay ingredientes repetidos en el plato.")
        return self
