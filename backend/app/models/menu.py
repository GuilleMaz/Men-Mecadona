"""Menús persistidos, entradas, consumo por entrada y lista de la compra (F4.1).

Un menú guarda su propio snapshot de nombres, costes, preferencias y precios de
compra. El historial no depende de que los platos sigan vivos en el catálogo ni
de que los precios actuales coincidan con los usados al generar.

``settings_json`` contiene un ``MenuSettings`` validado y versionado (ver
``app.schemas.menu``); las columnas de dinero están en céntimos enteros y las
cantidades en milésimas de la unidad base del ingrediente.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    case,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import EXPECTED_WAREHOUSE, POSTAL_CODE
from app.db import Base
from app.models.types import UtcDateTime, utcnow

if TYPE_CHECKING:
    from app.models.catalog import Product, SyncRun
    from app.models.dishes import Dish
    from app.models.ingredients import Ingredient
    from app.models.profile import Profile

#: Estados de generación que se persisten (`PLAN.md` §10.3).
MENU_STATUSES: tuple[str, ...] = ("optimal", "feasible", "relaxed")
#: Estado de precios, independiente del estado de generación.
MENU_PRICE_STATUSES: tuple[str, ...] = ("current", "stale")
#: Huecos del menú.
MENU_SLOTS: tuple[str, ...] = ("lunch", "dinner")

_MENU_STATUS_SQL = ", ".join(f"'{status}'" for status in MENU_STATUSES)
_MENU_PRICE_STATUS_SQL = ", ".join(f"'{status}'" for status in MENU_PRICE_STATUSES)
_MENU_SLOT_SQL = ", ".join(f"'{slot}'" for slot in MENU_SLOTS)


class Menu(Base):
    """Menú generado y congelado en el momento de su creación."""

    __tablename__ = "menus"
    __table_args__ = (
        CheckConstraint(f"status IN ({_MENU_STATUS_SQL})", name="ck_menus_status"),
        CheckConstraint(
            f"price_status IN ({_MENU_PRICE_STATUS_SQL})", name="ck_menus_price_status"
        ),
        CheckConstraint("people >= 1 AND people <= 10", name="ck_menus_people"),
        CheckConstraint("days >= 1 AND days <= 14", name="ck_menus_days"),
        CheckConstraint("budget_cents > 0", name="ck_menus_budget"),
        CheckConstraint(
            "ticket_cents >= 0 AND consumption_cents >= 0 "
            "AND pantry_consumption_cents >= 0 AND leftover_value_cents >= 0",
            name="ck_menus_amounts",
        ),
        CheckConstraint("violations >= 0", name="ck_menus_violations"),
        CheckConstraint("ticket_cents <= budget_cents", name="ck_menus_ticket_within_budget"),
        CheckConstraint(
            "revalidated_ticket_cents IS NULL OR revalidated_ticket_cents >= 0",
            name="ck_menus_revalidated_ticket",
        ),
        CheckConstraint("timed_out IN (0, 1)", name="ck_menus_timed_out"),
        Index("ix_menus_created_at", "created_at"),
        Index("ix_menus_profile_id", "profile_id"),
        Index("ix_menus_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False
    )

    people: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    price_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    timed_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    ticket_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    consumption_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pantry_consumption_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    leftover_value_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: Reglas de variedad relajadas, con los códigos estables del optimizador.
    relaxation_codes_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    revalidated_ticket_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    postal_code: Mapped[str] = mapped_column(
        String(5), nullable=False, default=POSTAL_CODE, server_default=POSTAL_CODE
    )
    warehouse: Mapped[str] = mapped_column(
        String(8), nullable=False, default=EXPECTED_WAREHOUSE, server_default=EXPECTED_WAREHOUSE
    )
    prices_captured_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    sync_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True
    )

    optimizer_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1", server_default="1"
    )
    #: ``MenuSettings`` serializado: exclusiones, despensa, alérgenos y repeticiones.
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
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

    profile: Mapped[Profile] = relationship()
    sync_run: Mapped[SyncRun | None] = relationship()
    entries: Mapped[list[MenuEntry]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by=lambda: (
            MenuEntry.day_index,
            case((MenuEntry.slot == "lunch", 0), else_=1),
            MenuEntry.id,
        ),
    )
    shopping_items: Mapped[list[ShoppingItem]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by="ShoppingItem.id",
    )


class MenuEntry(Base):
    """Plato asignado a un día y hueco, con snapshot de nombre y coste."""

    __tablename__ = "menu_entries"
    __table_args__ = (
        UniqueConstraint("menu_id", "day_index", "slot", name="uq_menu_entries_menu_slot"),
        CheckConstraint("day_index >= 0", name="ck_menu_entries_day_index"),
        CheckConstraint(f"slot IN ({_MENU_SLOT_SQL})", name="ck_menu_entries_slot"),
        CheckConstraint("entry_consumption_cents >= 0", name="ck_menu_entries_consumption"),
        CheckConstraint("locked IN (0, 1)", name="ck_menu_entries_locked"),
        Index("ix_menu_entries_menu_id", "menu_id"),
        Index("ix_menu_entries_dish_id", "dish_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[str] = mapped_column(String(8), nullable=False)
    dish_id: Mapped[int] = mapped_column(
        ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=False
    )
    #: Snapshot: el historial no cambia si el plato se renombra o desactiva.
    dish_name: Mapped[str] = mapped_column(String(200), nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    entry_consumption_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    entry_protein_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    menu: Mapped[Menu] = relationship(back_populates="entries")
    dish: Mapped[Dish] = relationship()
    ingredients: Mapped[list[MenuEntryIngredient]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="MenuEntryIngredient.id",
    )


class MenuEntryIngredient(Base):
    """Parte de un ingrediente consumida por una entrada concreta.

    ``used_milli`` está en la unidad base del ingrediente y ``consumption_cents``
    es la parte exacta del consumo del menú asignada a esta entrada. La suma por
    entrada y por menú se verifica en ``MenuService``.
    """

    __tablename__ = "menu_entry_ingredients"
    __table_args__ = (
        UniqueConstraint(
            "entry_id", "ingredient_id", name="uq_menu_entry_ingredients_entry_ingredient"
        ),
        CheckConstraint("used_milli >= 0", name="ck_menu_entry_ingredients_used"),
        CheckConstraint("consumption_cents >= 0", name="ck_menu_entry_ingredients_consumption"),
        Index("ix_menu_entry_ingredients_ingredient_id", "ingredient_id"),
        Index("ix_menu_entry_ingredients_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("menu_entries.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    used_milli: Mapped[int] = mapped_column(BigInteger, nullable=False)
    consumption_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    entry: Mapped[MenuEntry] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship()
    product: Mapped[Product] = relationship()


class ShoppingItem(Base):
    """Línea de compra materializada desde el plan canónico de compra."""

    __tablename__ = "shopping_items"
    __table_args__ = (
        UniqueConstraint("menu_id", "product_id", name="uq_shopping_items_menu_product"),
        CheckConstraint("packages > 0", name="ck_shopping_items_packages"),
        CheckConstraint("package_quantity_milli > 0", name="ck_shopping_items_package_quantity"),
        CheckConstraint("package_price_cents >= 0", name="ck_shopping_items_package_price"),
        CheckConstraint("subtotal_cents >= 0", name="ck_shopping_items_subtotal"),
        CheckConstraint("pantry_quantity_milli >= 0", name="ck_shopping_items_pantry"),
        CheckConstraint("checked IN (0, 1)", name="ck_shopping_items_checked"),
        Index("ix_shopping_items_menu_id", "menu_id"),
        Index("ix_shopping_items_ingredient_id", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False
    )
    packages: Mapped[int] = mapped_column(Integer, nullable=False)
    package_quantity_milli: Mapped[int] = mapped_column(BigInteger, nullable=False)
    package_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Despensa del ingrediente, guardada una sola vez en su primera línea.
    pantry_quantity_milli: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    menu: Mapped[Menu] = relationship(back_populates="shopping_items")
    product: Mapped[Product] = relationship()
    ingredient: Mapped[Ingredient] = relationship()
