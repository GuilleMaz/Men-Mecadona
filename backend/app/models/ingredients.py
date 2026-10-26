"""Ingredientes canónicos y su mapeo explícito a productos de Mercadona (F2.1).

Un ingrediente pertenece a un único grupo nutricional y tiene una única unidad
base. Las cantidades se guardan en milésimas de esa unidad (mg, µl o
mili-unidades), igual que en el catálogo. Cada producto puede pertenecer a un
solo ingrediente: `UNIQUE(product_id)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.allergens import ALLERGEN_CODES
from app.db import Base
from app.models.types import UtcDateTime, utcnow

if TYPE_CHECKING:
    from app.models.catalog import Product

INGREDIENT_GROUPS: tuple[str, ...] = (
    "vegetable",
    "protein",
    "carb",
    "dairy",
    "fat",
    "fruit",
    "pantry",
    "other",
)
SERVING_GROUPS: tuple[str, ...] = ("vegetable", "protein", "carb", "none")
BASE_UNITS: tuple[str, ...] = ("g", "ml", "unit")

_INGREDIENT_GROUP_SQL = ", ".join(f"'{group}'" for group in INGREDIENT_GROUPS)
_SERVING_GROUP_SQL = ", ".join(f"'{group}'" for group in SERVING_GROUPS)
_BASE_UNIT_SQL = ", ".join(f"'{unit}'" for unit in BASE_UNITS)
_ALLERGEN_SQL = ", ".join(f"'{code}'" for code in ALLERGEN_CODES)


class Ingredient(Base):
    """Concepto culinario canónico, independiente de un producto concreto."""

    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("length(slug) > 0", name="ck_ingredients_slug"),
        CheckConstraint(f'"group" IN ({_INGREDIENT_GROUP_SQL})', name="ck_ingredients_group"),
        CheckConstraint(f"base_unit IN ({_BASE_UNIT_SQL})", name="ck_ingredients_base_unit"),
        CheckConstraint(
            f"serving_group IN ({_SERVING_GROUP_SQL})",
            name="ck_ingredients_serving_group",
        ),
        CheckConstraint("serving_size_milli > 0", name="ck_ingredients_serving_size"),
        CheckConstraint(
            "grams_per_unit IS NULL OR grams_per_unit > 0",
            name="ck_ingredients_grams_per_unit",
        ),
        CheckConstraint("active IN (0, 1)", name="ck_ingredients_active"),
        Index("ix_ingredients_group", "group"),
        Index("ix_ingredients_active", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    group: Mapped[str] = mapped_column(String(16), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(8), nullable=False)

    #: Peso medio de una pieza o unidad, en gramos. Solo para `base_unit=unit`.
    grams_per_unit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    serving_group: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    serving_size_milli: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=100_000, server_default="100000"
    )

    #: Lista JSON de códigos canónicos. `[]` significa «sin alérgenos conocidos»;
    #: `["unknown"]` significa que no se pudo confirmar.
    allergens_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    tags_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, server_default="CURRENT_TIMESTAMP"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default="CURRENT_TIMESTAMP",
    )

    products: Mapped[list[IngredientProduct]] = relationship(
        back_populates="ingredient",
        cascade="all, delete-orphan",
        order_by="IngredientProduct.priority",
    )


class IngredientProduct(Base):
    """Producto concreto que cubre un ingrediente, con prioridad y respaldo.

    `priority` es 1 para el producto preferido. Exactamente uno de los mapeos
    activos de un ingrediente puede ser `is_default` (índice único parcial).
    """

    __tablename__ = "ingredient_products"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_ingredient_products_product_id"),
        UniqueConstraint("ingredient_id", "priority", name="uq_ingredient_products_priority"),
        CheckConstraint("priority >= 1", name="ck_ingredient_products_priority"),
        CheckConstraint("is_default IN (0, 1)", name="ck_ingredient_products_default"),
        Index(
            "uq_ingredient_products_default",
            "ingredient_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
        Index("ix_ingredient_products_ingredient_id", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    ingredient: Mapped[Ingredient] = relationship(back_populates="products")
    product: Mapped[Product] = relationship("Product")
