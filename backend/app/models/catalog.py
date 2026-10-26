"""Modelos del catálogo de Mercadona y de las ejecuciones de sincronización.

No se persiste `raw_json` ni instantáneas históricas de precios en el MVP. El
catálogo es una copia local de la tienda online para CP 22002 / almacén 4389.
Ver `PLAN.md` §9.1, §12.4 y §12.5.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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

from app.allergens import ALLERGEN_CODES
from app.db import Base
from app.models.types import UtcDateTime, utcnow

ALLERGEN_STATUSES: tuple[str, ...] = ("known", "partial", "unknown")
SYNC_STATUSES: tuple[str, ...] = ("running", "success", "partial", "failed")
SYNC_CATEGORY_STATUSES: tuple[str, ...] = ("success", "failed")
PACKAGE_UNITS: tuple[str, ...] = ("g", "ml", "unit")

_ALLERGEN_SQL = ", ".join(f"'{code}'" for code in ALLERGEN_CODES)
_ALLERGEN_STATUS_SQL = ", ".join(f"'{status}'" for status in ALLERGEN_STATUSES)
_SYNC_STATUS_SQL = ", ".join(f"'{status}'" for status in SYNC_STATUSES)
_SYNC_CATEGORY_STATUS_SQL = ", ".join(f"'{status}'" for status in SYNC_CATEGORY_STATUSES)
_PACKAGE_UNIT_SQL = ", ".join(f"'{unit}'" for unit in PACKAGE_UNITS)


class Category(Base):
    """Sección o subcategoría del árbol de Mercadona.

    El `id` es el identificador de la API: es estable y evita una tabla de alias.
    Las secciones tienen nivel 0 y las subcategorías nivel 1.
    """

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("level >= 0", name="ck_categories_level"),
        Index("ix_categories_parent_id", "parent_id"),
        Index("ix_categories_level", "level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_food: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    parent: Mapped[Category | None] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Category.sort_order",
    )
    products: Mapped[list[Product]] = relationship(back_populates="category")


class SyncRun(Base):
    """Ejecución completa de sincronización del catálogo."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_SYNC_STATUS_SQL})", name="ck_sync_runs_status"),
        CheckConstraint("categories_ok >= 0", name="ck_sync_runs_categories_ok"),
        CheckConstraint("categories_failed >= 0", name="ck_sync_runs_categories_failed"),
        CheckConstraint("products_seen >= 0", name="ck_sync_runs_products_seen"),
        Index("ix_sync_runs_started_at", "started_at"),
        Index("ix_sync_runs_status_finished_at", "status", "finished_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, server_default="CURRENT_TIMESTAMP"
    )
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    postal_code: Mapped[str] = mapped_column(String(5), nullable=False)
    warehouse: Mapped[str | None] = mapped_column(String(8), nullable=True)
    categories_ok: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    categories_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    products_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_runs: Mapped[list[SyncCategoryRun]] = relationship(
        back_populates="sync_run", cascade="all, delete-orphan"
    )
    products: Mapped[list[Product]] = relationship(back_populates="last_sync_run")


class SyncCategoryRun(Base):
    """Resultado de descargar una subcategoría dentro de una sync."""

    __tablename__ = "sync_category_runs"
    __table_args__ = (
        UniqueConstraint("sync_run_id", "category_id", name="uq_sync_category_runs_run_category"),
        CheckConstraint(
            f"status IN ({_SYNC_CATEGORY_STATUS_SQL})", name="ck_sync_category_runs_status"
        ),
        CheckConstraint("products_seen >= 0", name="ck_sync_category_runs_products_seen"),
        Index("ix_sync_category_runs_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    products_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    sync_run: Mapped[SyncRun] = relationship(back_populates="category_runs")
    category: Mapped[Category] = relationship()


class Product(Base):
    """Producto de Mercadona normalizado a céntimos y milésimas de unidad base."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_products_external_id"),
        CheckConstraint(
            "package_price_cents IS NULL OR package_price_cents >= 0",
            name="ck_products_package_price",
        ),
        CheckConstraint(
            "reference_price_cents IS NULL OR reference_price_cents >= 0",
            name="ck_products_reference_price",
        ),
        CheckConstraint(
            "package_quantity_milli IS NULL OR package_quantity_milli > 0",
            name="ck_products_package_quantity",
        ),
        CheckConstraint(
            f"package_unit IS NULL OR package_unit IN ({_PACKAGE_UNIT_SQL})",
            name="ck_products_package_unit",
        ),
        CheckConstraint(
            f"allergen_status IN ({_ALLERGEN_STATUS_SQL})",
            name="ck_products_allergen_status",
        ),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_name", "name"),
        Index("ix_products_published", "published"),
        Index("ix_products_last_seen_at", "last_seen_at"),
        Index("ix_products_last_sync_run_id", "last_sync_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ean: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    packaging: Mapped[str | None] = mapped_column(String(120), nullable=True)

    package_quantity_milli: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    package_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    package_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)

    is_pack: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    approx_size: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    selling_method: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allergen_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )

    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    unavailable_from: Mapped[str | None] = mapped_column(String(64), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, server_default="CURRENT_TIMESTAMP"
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, server_default="CURRENT_TIMESTAMP"
    )
    last_sync_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[Category] = relationship(back_populates="products")
    last_sync_run: Mapped[SyncRun | None] = relationship(back_populates="products")
    allergens: Mapped[list[ProductAllergen]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductAllergen(Base):
    """Alérgeno detectado en un producto, con su origen y confianza.

    La ausencia de filas no implica «sin alérgenos»: eso lo determina
    `products.allergen_status` y la política fail-closed de F2.4.
    """

    __tablename__ = "product_allergens"
    __table_args__ = (
        CheckConstraint(f"allergen_code IN ({_ALLERGEN_SQL})", name="ck_product_allergens_code"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    allergen_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    product: Mapped[Product] = relationship(back_populates="allergens")
