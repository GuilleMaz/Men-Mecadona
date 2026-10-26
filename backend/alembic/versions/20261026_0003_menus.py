"""menús, entradas y lista de la compra

Revision ID: 20261026_0003
Revises: 20261026_0002
Create Date: 2026-10-26 00:00:02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0003"
down_revision: str | None = "20261026_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "menus",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("people", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("budget_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("price_status", sa.String(length=16), server_default="current", nullable=False),
        sa.Column("timed_out", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("ticket_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumption_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pantry_consumption_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("leftover_value_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revalidated_ticket_cents", sa.Integer(), nullable=True),
        sa.Column("postal_code", sa.String(length=5), server_default="22002", nullable=False),
        sa.Column("warehouse", sa.String(length=8), server_default="4389", nullable=False),
        sa.Column("prices_captured_at", sa.DateTime(), nullable=True),
        sa.Column("sync_run_id", sa.Integer(), nullable=True),
        sa.Column("optimizer_version", sa.String(length=32), server_default="1", nullable=False),
        sa.Column("settings_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "budget_cents > 0",
            name="ck_menus_budget",
        ),
        sa.CheckConstraint(
            "days >= 1 AND days <= 14",
            name="ck_menus_days",
        ),
        sa.CheckConstraint(
            "people >= 1 AND people <= 10",
            name="ck_menus_people",
        ),
        sa.CheckConstraint(
            "price_status IN ('current', 'stale')",
            name="ck_menus_price_status",
        ),
        sa.CheckConstraint(
            "revalidated_ticket_cents IS NULL OR revalidated_ticket_cents >= 0",
            name="ck_menus_revalidated_ticket",
        ),
        sa.CheckConstraint(
            "status IN ('optimal', 'feasible', 'relaxed')",
            name="ck_menus_status",
        ),
        sa.CheckConstraint(
            "ticket_cents >= 0 AND consumption_cents >= 0 "
            "AND pantry_consumption_cents >= 0 AND leftover_value_cents >= 0",
            name="ck_menus_amounts",
        ),
        sa.CheckConstraint("timed_out IN (0, 1)", name="ck_menus_timed_out"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_menus_created_at", "menus", ["created_at"], unique=False)
    op.create_index("ix_menus_profile_id", "menus", ["profile_id"], unique=False)
    op.create_index("ix_menus_status", "menus", ["status"], unique=False)

    op.create_table(
        "menu_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("slot", sa.String(length=8), nullable=False),
        sa.Column("dish_id", sa.Integer(), nullable=False),
        sa.Column("dish_name", sa.String(length=200), nullable=False),
        sa.Column("locked", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("entry_consumption_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("entry_protein_source", sa.String(length=32), nullable=True),
        sa.CheckConstraint("day_index >= 0", name="ck_menu_entries_day_index"),
        sa.CheckConstraint("entry_consumption_cents >= 0", name="ck_menu_entries_consumption"),
        sa.CheckConstraint("locked IN (0, 1)", name="ck_menu_entries_locked"),
        sa.CheckConstraint("slot IN ('lunch', 'dinner')", name="ck_menu_entries_slot"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "day_index", "slot", name="uq_menu_entries_menu_slot"),
    )
    op.create_index("ix_menu_entries_dish_id", "menu_entries", ["dish_id"], unique=False)
    op.create_index("ix_menu_entries_menu_id", "menu_entries", ["menu_id"], unique=False)

    op.create_table(
        "menu_entry_ingredients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("used_milli", sa.BigInteger(), nullable=False),
        sa.Column("consumption_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("consumption_cents >= 0", name="ck_menu_entry_ingredients_consumption"),
        sa.CheckConstraint("used_milli >= 0", name="ck_menu_entry_ingredients_used"),
        sa.ForeignKeyConstraint(["entry_id"], ["menu_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "ingredient_id", name="uq_menu_entry_ingredients_entry_ingredient"
        ),
    )
    op.create_index(
        "ix_menu_entry_ingredients_ingredient_id",
        "menu_entry_ingredients",
        ["ingredient_id"],
        unique=False,
    )
    op.create_index(
        "ix_menu_entry_ingredients_product_id",
        "menu_entry_ingredients",
        ["product_id"],
        unique=False,
    )

    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("menu_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("packages", sa.Integer(), nullable=False),
        sa.Column("package_quantity_milli", sa.BigInteger(), nullable=False),
        sa.Column("package_price_cents", sa.Integer(), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("pantry_quantity_milli", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("checked", sa.Boolean(), server_default="0", nullable=False),
        sa.CheckConstraint("checked IN (0, 1)", name="ck_shopping_items_checked"),
        sa.CheckConstraint("package_price_cents >= 0", name="ck_shopping_items_package_price"),
        sa.CheckConstraint("package_quantity_milli > 0", name="ck_shopping_items_package_quantity"),
        sa.CheckConstraint("packages > 0", name="ck_shopping_items_packages"),
        sa.CheckConstraint("pantry_quantity_milli >= 0", name="ck_shopping_items_pantry"),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_shopping_items_subtotal"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "product_id", name="uq_shopping_items_menu_product"),
    )
    op.create_index(
        "ix_shopping_items_ingredient_id", "shopping_items", ["ingredient_id"], unique=False
    )
    op.create_index("ix_shopping_items_menu_id", "shopping_items", ["menu_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shopping_items_menu_id", table_name="shopping_items")
    op.drop_index("ix_shopping_items_ingredient_id", table_name="shopping_items")
    op.drop_table("shopping_items")
    op.drop_index("ix_menu_entry_ingredients_product_id", table_name="menu_entry_ingredients")
    op.drop_index("ix_menu_entry_ingredients_ingredient_id", table_name="menu_entry_ingredients")
    op.drop_table("menu_entry_ingredients")
    op.drop_index("ix_menu_entries_menu_id", table_name="menu_entries")
    op.drop_index("ix_menu_entries_dish_id", table_name="menu_entries")
    op.drop_table("menu_entries")
    op.drop_index("ix_menus_status", table_name="menus")
    op.drop_index("ix_menus_profile_id", table_name="menus")
    op.drop_index("ix_menus_created_at", table_name="menus")
    op.drop_table("menus")
