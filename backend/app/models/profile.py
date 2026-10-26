"""Perfil local, exclusiones y despensa (F2.1).

El MVP tiene un único perfil (`id=1`). Las exclusiones apuntan a un ingrediente,
un plato o una etiqueta, nunca a más de uno. SQLite trata `NULL` como distinto,
así que la unicidad se garantiza con tres índices únicos parciales.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.types import UtcDateTime, utcnow

if TYPE_CHECKING:
    from app.models.dishes import Dish
    from app.models.ingredients import Ingredient


class Profile(Base):
    """Fila única con los últimos valores y preferencias del usuario."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_profiles_single_row"),
        CheckConstraint("people >= 1 AND people <= 10", name="ck_profiles_people"),
        CheckConstraint("days >= 1 AND days <= 14", name="ck_profiles_days"),
        CheckConstraint("budget_cents > 0", name="ck_profiles_budget"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    people: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=7, server_default="7")
    budget_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7000, server_default="7000"
    )
    allergen_codes_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
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

    exclusions: Mapped[list[Exclusion]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    pantry_items: Mapped[list[PantryItem]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Exclusion(Base):
    """Exclusión persistente por ingrediente, plato o etiqueta."""

    __tablename__ = "exclusions"
    __table_args__ = (
        CheckConstraint(
            "((ingredient_id IS NOT NULL) + (dish_id IS NOT NULL) + (tag IS NOT NULL)) = 1",
            name="ck_exclusions_one_target",
        ),
        CheckConstraint("tag IS NULL OR length(trim(tag)) > 0", name="ck_exclusions_tag"),
        Index(
            "uq_exclusions_profile_ingredient",
            "profile_id",
            "ingredient_id",
            unique=True,
            sqlite_where=text("ingredient_id IS NOT NULL"),
        ),
        Index(
            "uq_exclusions_profile_dish",
            "profile_id",
            "dish_id",
            unique=True,
            sqlite_where=text("dish_id IS NOT NULL"),
        ),
        Index(
            "uq_exclusions_profile_tag",
            "profile_id",
            "tag",
            unique=True,
            sqlite_where=text("tag IS NOT NULL"),
        ),
        Index("ix_exclusions_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=True
    )
    dish_id: Mapped[int | None] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), nullable=True
    )
    tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, server_default="CURRENT_TIMESTAMP"
    )

    profile: Mapped[Profile] = relationship(back_populates="exclusions")
    ingredient: Mapped[Ingredient | None] = relationship()
    dish: Mapped[Dish | None] = relationship()


class PantryItem(Base):
    """Cantidad de un ingrediente que el usuario ya tiene en casa."""

    __tablename__ = "pantry_items"
    __table_args__ = (
        UniqueConstraint("profile_id", "ingredient_id", name="uq_pantry_items_profile_ingredient"),
        CheckConstraint("quantity_milli >= 0", name="ck_pantry_items_quantity"),
        Index("ix_pantry_items_ingredient_id", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_milli: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default="CURRENT_TIMESTAMP",
    )

    profile: Mapped[Profile] = relationship(back_populates="pantry_items")
    ingredient: Mapped[Ingredient] = relationship()
    #: La unidad se toma de `ingredients.base_unit`; no se duplica.
