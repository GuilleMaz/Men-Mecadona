"""Modelos persistentes de Cesta.

La importación de este paquete registra todas las tablas en `Base.metadata`, que
es lo que consume Alembic para generar y aplicar migraciones.
"""

from app.db import Base
from app.models.catalog import (
    ALLERGEN_STATUSES,
    SYNC_STATUSES,
    Category,
    Product,
    ProductAllergen,
    SyncCategoryRun,
    SyncRun,
)
from app.models.dishes import Dish, DishIngredient
from app.models.ingredients import (
    BASE_UNITS,
    INGREDIENT_GROUPS,
    SERVING_GROUPS,
    Ingredient,
    IngredientProduct,
)
from app.models.profile import Exclusion, PantryItem, Profile
from app.models.types import UtcDateTime, utcnow

__all__ = [
    "ALLERGEN_STATUSES",
    "BASE_UNITS",
    "INGREDIENT_GROUPS",
    "SERVING_GROUPS",
    "SYNC_STATUSES",
    "Base",
    "Category",
    "Dish",
    "DishIngredient",
    "Exclusion",
    "Ingredient",
    "IngredientProduct",
    "PantryItem",
    "Product",
    "ProductAllergen",
    "Profile",
    "SyncCategoryRun",
    "SyncRun",
    "UtcDateTime",
    "utcnow",
]
