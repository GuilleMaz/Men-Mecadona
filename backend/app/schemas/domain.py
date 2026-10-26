"""Esquemas de ingredientes, platos y preferencias (F2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.allergens import ALLERGEN_CODE_SET

IngredientGroup = Literal[
    "vegetable", "protein", "carb", "dairy", "fat", "fruit", "pantry", "other"
]
ServingGroup = Literal["vegetable", "protein", "carb", "none"]
BaseUnit = Literal["g", "ml", "unit"]
MealType = Literal["lunch", "dinner"]


class AllergenOut(BaseModel):
    """Alérgeno canónico con su etiqueta en español."""

    code: str
    name: str


class IngredientOut(BaseModel):
    """Ingrediente canónico para listados y selectores."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    category: str
    group: IngredientGroup
    base_unit: BaseUnit
    grams_per_unit: int | None
    protein_source: str | None
    serving_group: ServingGroup
    serving_size_milli: int
    allergens: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool


class ProductOptionOut(BaseModel):
    """Producto mapeado a un ingrediente, tal y como lo verá la UI."""

    id: int
    external_id: str
    name: str
    package_quantity_milli: int | None
    package_unit: str | None
    package_price_cents: int | None
    is_default: bool
    priority: int
    allergen_status: str
    published: bool
    eligible: bool = False


class DishIngredientOut(BaseModel):
    """Composición de un plato."""

    ingredient: IngredientOut
    quantity_milli: int
    products: list[ProductOptionOut] = Field(default_factory=list)


class DishSummary(BaseModel):
    """Plato para el catálogo, con su elegibilidad actual."""

    id: int
    slug: str
    name: str
    description: str | None
    base_servings: int
    meal_types: list[MealType]
    protein_sources: list[str]
    has_vegetables: bool
    light: bool
    carbs: str | None
    tags: list[str]
    allergens: list[str]
    eligible: bool
    exclusion_reasons: list[str] = Field(default_factory=list)


class DishDetail(DishSummary):
    """Detalle del plato con composición y productos asociados."""

    ingredients: list[DishIngredientOut] = Field(default_factory=list)


class DishPage(BaseModel):
    """Listado paginado de platos."""

    items: list[DishSummary]
    total: int
    limit: int
    offset: int


class IngredientPage(BaseModel):
    """Listado paginado de ingredientes."""

    items: list[IngredientOut]
    total: int
    limit: int
    offset: int


class ProfileOut(BaseModel):
    """Perfil local y preferencias estables."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    people: int
    days: int
    budget_cents: int
    allergen_codes: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    """Datos que puede cambiar el usuario desde el formulario inicial."""

    people: int = Field(ge=1, le=10)
    days: int = Field(ge=1, le=14)
    budget_cents: int = Field(gt=0, le=1_000_000)
    #: `None` conserva los alérgenos actuales; una lista los reemplaza.
    allergen_codes: list[str] | None = None

    @field_validator("allergen_codes")
    @classmethod
    def _validate_allergens(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for code in value:
            if code not in ALLERGEN_CODE_SET:
                raise ValueError(f"Alérgeno desconocido: {code}")
            if code not in normalized:
                normalized.append(code)
        return normalized


class ExclusionCreate(BaseModel):
    """Exclusión por ingrediente, plato o etiqueta (exactamente una)."""

    ingredient_id: int | None = Field(default=None, ge=1)
    dish_id: int | None = Field(default=None, ge=1)
    tag: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> ExclusionCreate:
        targets = [self.ingredient_id, self.dish_id, self.tag]
        if sum(target is not None for target in targets) != 1:
            raise ValueError("Indica exactamente un ingrediente, plato o etiqueta.")
        return self


class ExclusionOut(BaseModel):
    """Exclusión con su etiqueta legible para la UI."""

    id: int
    kind: Literal["ingredient", "dish", "tag"]
    ingredient_id: int | None
    dish_id: int | None
    tag: str | None
    label: str


class PantryItemIn(BaseModel):
    """Cantidad de despensa en milésimas de la unidad base del ingrediente."""

    ingredient_id: int = Field(ge=1)
    quantity_milli: int = Field(ge=0)


class PantryUpdate(BaseModel):
    """Reemplaza la despensa completa del perfil."""

    items: list[PantryItemIn] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def _unique_ingredients(cls, value: list[PantryItemIn]) -> list[PantryItemIn]:
        ids = [item.ingredient_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay ingredientes repetidos en la despensa.")
        return value


class PantryItemOut(BaseModel):
    """Entrada de despensa con la unidad base del ingrediente."""

    id: int
    ingredient: IngredientOut
    quantity_milli: int
