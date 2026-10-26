"""Conversión de modelos a esquemas de salida compartidos por los routers."""

from __future__ import annotations

from app.models.ingredients import Ingredient
from app.schemas.domain import IngredientOut


def ingredient_out(ingredient: Ingredient) -> IngredientOut:
    """Ingrediente canónico tal y como lo publica la API."""
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
