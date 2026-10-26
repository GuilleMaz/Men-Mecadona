"""catálogo inicial

Revision ID: 20261026_0001
Revises:
Create Date: 2026-10-26 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_food", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("level >= 0", name="ck_categories_level"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_level", "categories", ["level"], unique=False)
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("postal_code", sa.String(length=5), nullable=False),
        sa.Column("warehouse", sa.String(length=8), nullable=True),
        sa.Column("categories_ok", sa.Integer(), server_default="0", nullable=False),
        sa.Column("categories_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("products_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("categories_failed >= 0", name="ck_sync_runs_categories_failed"),
        sa.CheckConstraint("categories_ok >= 0", name="ck_sync_runs_categories_ok"),
        sa.CheckConstraint("products_seen >= 0", name="ck_sync_runs_products_seen"),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_sync_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("ean", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("packaging", sa.String(length=120), nullable=True),
        sa.Column("package_quantity_milli", sa.BigInteger(), nullable=True),
        sa.Column("package_unit", sa.String(length=8), nullable=True),
        sa.Column("is_estimated", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("package_price_cents", sa.Integer(), nullable=True),
        sa.Column("reference_price_cents", sa.Integer(), nullable=True),
        sa.Column("reference_unit", sa.String(length=8), nullable=True),
        sa.Column("is_pack", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("approx_size", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("selling_method", sa.Integer(), nullable=True),
        sa.Column(
            "allergen_status", sa.String(length=16), server_default="unknown", nullable=False
        ),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("published", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("unavailable_from", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("last_sync_run_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "allergen_status IN ('known', 'partial', 'unknown')",
            name="ck_products_allergen_status",
        ),
        sa.CheckConstraint(
            "package_price_cents IS NULL OR package_price_cents >= 0",
            name="ck_products_package_price",
        ),
        sa.CheckConstraint(
            "package_quantity_milli IS NULL OR package_quantity_milli > 0",
            name="ck_products_package_quantity",
        ),
        sa.CheckConstraint(
            "package_unit IS NULL OR package_unit IN ('g', 'ml', 'unit')",
            name="ck_products_package_unit",
        ),
        sa.CheckConstraint(
            "reference_price_cents IS NULL OR reference_price_cents >= 0",
            name="ck_products_reference_price",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_products_external_id"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
    op.create_index("ix_products_last_seen_at", "products", ["last_seen_at"], unique=False)
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index("ix_products_published", "products", ["published"], unique=False)

    op.create_table(
        "product_allergens",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("allergen_code", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "allergen_code IN ('gluten', 'crustaceans', 'eggs', 'fish', 'peanuts', "
            "'soybeans', 'milk', 'nuts', 'celery', 'mustard', 'sesame', 'sulphites', "
            "'lupin', 'molluscs', 'unknown')",
            name="ck_product_allergens_code",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "allergen_code"),
    )

    op.create_table(
        "sync_category_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sync_run_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("products_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('success', 'failed')", name="ck_sync_category_runs_status"),
        sa.CheckConstraint("products_seen >= 0", name="ck_sync_category_runs_products_seen"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sync_run_id", "category_id", name="uq_sync_category_runs_run_category"
        ),
    )
    op.create_index(
        "ix_sync_category_runs_category_id",
        "sync_category_runs",
        ["category_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_category_runs_category_id", table_name="sync_category_runs")
    op.drop_table("sync_category_runs")
    op.drop_table("product_allergens")
    op.drop_index("ix_products_published", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_last_seen_at", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_index("ix_categories_level", table_name="categories")
    op.drop_table("categories")
