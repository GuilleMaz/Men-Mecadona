"""ingredientes, platos y preferencias

Revision ID: 20261026_0002
Revises: 20261026_0001
Create Date: 2026-10-26 00:00:01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0002"
down_revision: str | None = "20261026_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("group", sa.String(length=16), nullable=False),
        sa.Column("base_unit", sa.String(length=8), nullable=False),
        sa.Column("grams_per_unit", sa.Integer(), nullable=True),
        sa.Column("protein_source", sa.String(length=32), nullable=True),
        sa.Column("serving_group", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("serving_size_milli", sa.BigInteger(), server_default="100000", nullable=False),
        sa.Column("allergens_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("tags_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
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
        sa.CheckConstraint("active IN (0, 1)", name="ck_ingredients_active"),
        sa.CheckConstraint("base_unit IN ('g', 'ml', 'unit')", name="ck_ingredients_base_unit"),
        sa.CheckConstraint(
            "grams_per_unit IS NULL OR grams_per_unit > 0",
            name="ck_ingredients_grams_per_unit",
        ),
        sa.CheckConstraint(
            "\"group\" IN ('vegetable', 'protein', 'carb', 'dairy', 'fat', "
            "'fruit', 'pantry', 'other')",
            name="ck_ingredients_group",
        ),
        sa.CheckConstraint(
            "serving_group IN ('vegetable', 'protein', 'carb', 'none')",
            name="ck_ingredients_serving_group",
        ),
        sa.CheckConstraint("serving_size_milli > 0", name="ck_ingredients_serving_size"),
        sa.CheckConstraint("length(slug) > 0", name="ck_ingredients_slug"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_ingredients_active", "ingredients", ["active"], unique=False)
    op.create_index("ix_ingredients_group", "ingredients", ["group"], unique=False)

    op.create_table(
        "ingredient_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("is_default IN (0, 1)", name="ck_ingredient_products_default"),
        sa.CheckConstraint("priority >= 1", name="ck_ingredient_products_priority"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_ingredient_products_product_id"),
        sa.UniqueConstraint("ingredient_id", "priority", name="uq_ingredient_products_priority"),
    )
    op.create_index(
        "ix_ingredient_products_ingredient_id",
        "ingredient_products",
        ["ingredient_id"],
        unique=False,
    )
    op.create_index(
        "uq_ingredient_products_default",
        "ingredient_products",
        ["ingredient_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )

    op.create_table(
        "dishes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_servings", sa.Integer(), nullable=False),
        sa.Column("meal_types_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "protein_sources_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("has_vegetables", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("light", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("carbs", sa.String(length=32), nullable=True),
        sa.Column("tags_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("seed_version", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint("active IN (0, 1)", name="ck_dishes_active"),
        sa.CheckConstraint("base_servings > 0", name="ck_dishes_base_servings"),
        sa.CheckConstraint("length(slug) > 0", name="ck_dishes_slug"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_dishes_active", "dishes", ["active"], unique=False)
    op.create_index("ix_dishes_name", "dishes", ["name"], unique=False)

    op.create_table(
        "dish_ingredients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dish_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("quantity_milli", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity_milli > 0", name="ck_dish_ingredients_quantity"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dish_id", "ingredient_id", name="uq_dish_ingredients_dish_ingredient"),
    )
    op.create_index(
        "ix_dish_ingredients_ingredient_id",
        "dish_ingredients",
        ["ingredient_id"],
        unique=False,
    )

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("people", sa.Integer(), server_default="2", nullable=False),
        sa.Column("days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("budget_cents", sa.Integer(), server_default="7000", nullable=False),
        sa.Column("allergen_codes_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
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
        sa.CheckConstraint("budget_cents > 0", name="ck_profiles_budget"),
        sa.CheckConstraint("days >= 1 AND days <= 14", name="ck_profiles_days"),
        sa.CheckConstraint("people >= 1 AND people <= 10", name="ck_profiles_people"),
        sa.CheckConstraint("id = 1", name="ck_profiles_single_row"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "exclusions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=True),
        sa.Column("dish_id", sa.Integer(), nullable=True),
        sa.Column("tag", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "((ingredient_id IS NOT NULL) + (dish_id IS NOT NULL) + (tag IS NOT NULL)) = 1",
            name="ck_exclusions_one_target",
        ),
        sa.CheckConstraint("tag IS NULL OR length(trim(tag)) > 0", name="ck_exclusions_tag"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exclusions_profile_id", "exclusions", ["profile_id"], unique=False)
    op.create_index(
        "uq_exclusions_profile_dish",
        "exclusions",
        ["profile_id", "dish_id"],
        unique=True,
        sqlite_where=sa.text("dish_id IS NOT NULL"),
    )
    op.create_index(
        "uq_exclusions_profile_ingredient",
        "exclusions",
        ["profile_id", "ingredient_id"],
        unique=True,
        sqlite_where=sa.text("ingredient_id IS NOT NULL"),
    )
    op.create_index(
        "uq_exclusions_profile_tag",
        "exclusions",
        ["profile_id", "tag"],
        unique=True,
        sqlite_where=sa.text("tag IS NOT NULL"),
    )

    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("quantity_milli", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity_milli >= 0", name="ck_pantry_items_quantity"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "ingredient_id", name="uq_pantry_items_profile_ingredient"
        ),
    )
    op.create_index(
        "ix_pantry_items_ingredient_id", "pantry_items", ["ingredient_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_pantry_items_ingredient_id", table_name="pantry_items")
    op.drop_table("pantry_items")
    op.drop_index("uq_exclusions_profile_tag", table_name="exclusions")
    op.drop_index("uq_exclusions_profile_ingredient", table_name="exclusions")
    op.drop_index("uq_exclusions_profile_dish", table_name="exclusions")
    op.drop_index("ix_exclusions_profile_id", table_name="exclusions")
    op.drop_table("exclusions")
    op.drop_table("profiles")
    op.drop_index("ix_dish_ingredients_ingredient_id", table_name="dish_ingredients")
    op.drop_table("dish_ingredients")
    op.drop_index("ix_dishes_name", table_name="dishes")
    op.drop_index("ix_dishes_active", table_name="dishes")
    op.drop_table("dishes")
    op.drop_index("uq_ingredient_products_default", table_name="ingredient_products")
    op.drop_index("ix_ingredient_products_ingredient_id", table_name="ingredient_products")
    op.drop_table("ingredient_products")
    op.drop_index("ix_ingredients_group", table_name="ingredients")
    op.drop_index("ix_ingredients_active", table_name="ingredients")
    op.drop_table("ingredients")
