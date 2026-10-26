"""Platos y su composición de ingredientes (F2.1).

No hay recetas ni pasos de cocina: un plato es una ficha con composición,
etiquetas y flags derivados de la composición. Las cantidades se guardan en la
unidad base del ingrediente y en milésimas.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import UtcDateTime, utcnow

if TYPE_CHECKING:
    from app.models.ingredients import Ingredient

MEAL_TYPES: tuple[str, ...] = ("lunch", "dinner")


class Dish(Base):
    """Ficha de un plato sin instrucciones de elaboración."""

    __tablename__ = "dishes"
    __table_args__ = (
        CheckConstraint("length(slug) > 0", name="ck_dishes_slug"),
        CheckConstraint("base_servings > 0", name="ck_dishes_base_servings"),
        CheckConstraint("active IN (0, 1)", name="ck_dishes_active"),
        Index("ix_dishes_active", "active"),
        Index("ix_dishes_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_servings: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    #: Huecos compatibles: `lunch`, `dinner` o ambos.
    meal_types_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    protein_sources_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    has_vegetables: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    light: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    carbs: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    seed_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
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

    ingredients: Mapped[list[DishIngredient]] = relationship(
        back_populates="dish",
        cascade="all, delete-orphan",
        order_by="DishIngredient.id",
    )


class DishIngredient(Base):
    """Cantidad de un ingrediente dentro de un plato.

    `quantity_milli` está expresada en la unidad base del ingrediente; no se
    duplica la columna `unit`.
    """

    __tablename__ = "dish_ingredients"
    __table_args__ = (
        UniqueConstraint("dish_id", "ingredient_id", name="uq_dish_ingredients_dish_ingredient"),
        CheckConstraint("quantity_milli > 0", name="ck_dish_ingredients_quantity"),
        Index("ix_dish_ingredients_ingredient_id", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dish_id: Mapped[int] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_milli: Mapped[int] = mapped_column(BigInteger, nullable=False)

    dish: Mapped[Dish] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship()
