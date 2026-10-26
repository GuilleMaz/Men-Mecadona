"""Snapshot validado de preferencias de un menú (F4.1).

``Menu.settings_json`` guarda este esquema para que el menú sea reproducible
aunque el perfil cambie después. Las claves son estables y versionadas; un
cambio incompatible debe incrementar ``version`` y migrar los menús guardados.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.allergens import ALLERGEN_CODE_SET


class PantrySnapshot(BaseModel):
    """Cantidad de despensa usada al generar o recalcular un menú."""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: int = Field(ge=1)
    quantity_milli: int = Field(ge=0)


class MenuSettings(BaseModel):
    """Preferencias y despensa congeladas en el menú."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    allergen_codes: list[str] = Field(default_factory=list)
    excluded_ingredient_ids: list[int] = Field(default_factory=list)
    excluded_dish_ids: list[int] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)
    pantry: list[PantrySnapshot] = Field(default_factory=list)
    max_repeats: int = Field(default=1, ge=1, le=14)
    optimizer_version: str = Field(default="1", min_length=1, max_length=32)

    @field_validator("allergen_codes")
    @classmethod
    def _validate_allergens(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for code in value:
            if code not in ALLERGEN_CODE_SET:
                raise ValueError(f"Alérgeno desconocido: {code}")
            if code not in normalized:
                normalized.append(code)
        return normalized

    @field_validator("excluded_ingredient_ids", "excluded_dish_ids")
    @classmethod
    def _unique_ids(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value):
            raise ValueError("Los identificadores deben ser positivos.")
        return list(dict.fromkeys(value))

    @field_validator("excluded_tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in value:
            clean = tag.strip()
            if not clean:
                raise ValueError("Las etiquetas no pueden estar vacías.")
            if clean not in normalized:
                normalized.append(clean)
        return normalized

    @field_validator("pantry")
    @classmethod
    def _unique_pantry(cls, value: list[PantrySnapshot]) -> list[PantrySnapshot]:
        ingredient_ids = [item.ingredient_id for item in value]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Hay ingredientes repetidos en la despensa del menú.")
        return value
