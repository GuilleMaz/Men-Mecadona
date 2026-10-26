"""Esquemas de entrada y salida de la API de menús (F4.6).

Los importes son céntimos enteros, las cantidades milésimas de la unidad base y
las fechas ISO-8601 UTC. ``MenuSettings`` se reutiliza del snapshot persistido
para que el contrato del menú guardado y el de la API no divergan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.allergens import ALLERGEN_CODE_SET
from app.schemas.domain import BaseUnit, MealType
from app.schemas.menu import MenuSettings, PantrySnapshot

MenuStatus = Literal["optimal", "feasible", "relaxed"]
MenuPriceStatus = Literal["current", "stale"]
GenerateStatus = Literal["optimal", "feasible", "relaxed", "infeasible", "timeout"]
GenerateReason = Literal["budget", "timeout"]
ExclusionScope = Literal["menu", "profile"]
ExportFormat = Literal["markdown", "csv"]


class MenuGenerateRequest(BaseModel):
    """Parámetros de generación; ``None`` hereda las preferencias del perfil."""

    people: int = Field(ge=1, le=10)
    days: int = Field(ge=1, le=14)
    budget_cents: int = Field(gt=0, le=1_000_000)
    #: ``None``/omitido usa los alérgenos del perfil; una lista los reemplaza.
    allergen_codes: list[str] | None = None
    #: ``None``/omitido usa las exclusiones del perfil; una lista las reemplaza.
    excluded_ingredient_ids: list[Annotated[int, Field(ge=1)]] | None = None
    excluded_dish_ids: list[Annotated[int, Field(ge=1)]] | None = None
    excluded_tags: list[str] | None = None
    #: ``None``/omitido usa la despensa del perfil; una lista la reemplaza.
    pantry: list[PantrySnapshot] | None = None
    max_repeats: int = Field(default=1, ge=1, le=14)

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

    @field_validator("pantry")
    @classmethod
    def _unique_pantry(
        cls,
        value: list[PantrySnapshot] | None,
    ) -> list[PantrySnapshot] | None:
        if value is None:
            return None
        ingredient_ids = [item.ingredient_id for item in value]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Hay ingredientes repetidos en la despensa.")
        return value


class MenuSummary(BaseModel):
    """Cabecera de un menú persistido para historial y listados."""

    id: int
    people: int
    days: int
    budget_cents: int
    status: MenuStatus
    price_status: MenuPriceStatus
    timed_out: bool
    ticket_cents: int
    consumption_cents: int
    pantry_consumption_cents: int
    leftover_value_cents: int
    revalidated_ticket_cents: int | None
    previous_ticket_cents: int | None = None
    price_delta_cents: int | None = None
    revalidated_at: datetime | None = None
    violations: int
    relaxations: list[str] = Field(default_factory=list)
    postal_code: str
    warehouse: str
    prices_captured_at: datetime | None
    optimizer_version: str
    created_at: datetime
    updated_at: datetime


class MenuEntryIngredient(BaseModel):
    """Parte de un ingrediente consumida por una entrada concreta."""

    ingredient_id: int
    ingredient_name: str
    base_unit: BaseUnit
    used_milli: int
    consumption_cents: int
    product_id: int


class MenuEntry(BaseModel):
    """Plato asignado a un día y hueco, con su coste y composición."""

    id: int
    day_index: int
    slot: MealType
    dish_id: int
    dish_name: str
    locked: bool
    entry_consumption_cents: int
    protein_source: str | None
    tags: list[str] = Field(default_factory=list)
    ingredients: list[MenuEntryIngredient] = Field(default_factory=list)


class MenuDetail(MenuSummary):
    """Menú completo con su snapshot de preferencias y sus entradas."""

    settings: MenuSettings
    entries: list[MenuEntry] = Field(default_factory=list)


class MenuPage(BaseModel):
    """Listado paginado de menús, del más reciente al más antiguo."""

    items: list[MenuSummary]
    total: int
    limit: int
    offset: int


class MenuGenerateResponse(BaseModel):
    """Resultado de generar: menú persistido, preview de inviabilidad o timeout."""

    status: GenerateStatus
    is_preview: bool
    reason: GenerateReason | None
    menu_id: int | None
    people: int
    days: int
    budget_cents: int
    ticket_cents: int | None
    consumption_cents: int | None
    pantry_consumption_cents: int | None
    leftover_value_cents: int | None
    minimum_ticket_cents: int | None
    minimum_is_estimate: bool
    shortfall_cents: int
    relaxations: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    price_status: MenuPriceStatus | None
    timed_out: bool
    postal_code: str
    warehouse: str
    prices_captured_at: datetime | None
    entries: list[MenuEntry] = Field(default_factory=list)


class MenuEntryLockUpdate(BaseModel):
    """Bloqueo o desbloqueo de una entrada; no recalcula el menú."""

    model_config = ConfigDict(extra="forbid")

    locked: bool


class MenuEntrySwap(BaseModel):
    """Plato de reemplazo para una entrada."""

    model_config = ConfigDict(extra="forbid")

    dish_id: int = Field(ge=1)


class MenuEntryExclude(BaseModel):
    """Ámbito de la exclusión: solo este menú o el perfil completo."""

    model_config = ConfigDict(extra="forbid")

    scope: ExclusionScope


class ShoppingItem(BaseModel):
    """Línea de compra materializada desde el plan canónico."""

    id: int
    product_id: int
    product_name: str
    brand: str | None
    ingredient_id: int
    ingredient_name: str
    packages: int
    package_quantity_milli: int
    package_unit: str
    package_price_cents: int
    subtotal_cents: int
    pantry_quantity_milli: int
    checked: bool


class ShoppingSection(BaseModel):
    """Sección padre (o categoría) con sus líneas y subtotal."""

    section_id: int | None
    section_name: str
    subtotal_cents: int
    items: list[ShoppingItem] = Field(default_factory=list)


class ShoppingPantryItem(BaseModel):
    """Ingrediente cubierto por la despensa del snapshot del menú."""

    ingredient_id: int
    ingredient_name: str
    base_unit: BaseUnit
    quantity_milli: int


class ShoppingList(BaseModel):
    """Lista de la compra agrupada por secciones con totales e identidad."""

    menu_id: int
    status: MenuStatus
    price_status: MenuPriceStatus
    timed_out: bool
    people: int
    days: int
    budget_cents: int
    ticket_cents: int
    consumption_cents: int
    pantry_consumption_cents: int
    leftover_value_cents: int
    revalidated_ticket_cents: int | None = None
    previous_ticket_cents: int | None = None
    price_delta_cents: int | None = None
    revalidated_at: datetime | None = None
    checked_total_cents: int
    item_count: int
    checked_count: int
    cost_per_meal_cents: int
    cost_per_day_cents: int
    cost_per_person_day_cents: int
    postal_code: str
    warehouse: str
    prices_captured_at: datetime | None
    updated_at: datetime
    sections: list[ShoppingSection] = Field(default_factory=list)
    pantry_items: list[ShoppingPantryItem] = Field(default_factory=list)


class ShoppingItemUpdate(BaseModel):
    """Marca una línea o aplica «ya lo tengo»; exactamente una de las dos."""

    model_config = ConfigDict(extra="forbid")

    checked: bool | None = None
    already_have: Literal[True] | None = None

    @model_validator(mode="after")
    def _exactly_one_action(self) -> ShoppingItemUpdate:
        if (self.checked is None) == (self.already_have is None):
            raise ValueError("Indica 'checked' o 'already_have', pero no ambos.")
        return self
