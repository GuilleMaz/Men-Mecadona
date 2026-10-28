"""plato principal y acompanamientos (F6)

Revision ID: 20261026_0006
Revises: 20261026_0005
Create Date: 2026-10-26 00:00:05

Añade el rol derivado de cada plato (`main`/`complement`), su proteína principal
y el curso de cada entrada de menú. La unicidad pasa de
`(menu_id, day_index, slot)` a `(menu_id, day_index, slot, course)`: cada hueco
conserva exactamente un principal y admite como máximo un acompañamiento.
Los menús históricos quedan interpretados como `course='main'` y no se invalidan.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0006"
down_revision: str | None = "20261026_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("dishes") as batch:
        batch.add_column(
            sa.Column("role", sa.String(length=16), server_default="main", nullable=False)
        )
        batch.add_column(sa.Column("primary_protein", sa.String(length=32), nullable=True))
        batch.create_check_constraint(
            "ck_dishes_role",
            "role IN ('main', 'complement')",
        )
        batch.create_index("ix_dishes_role", ["role"])
        batch.create_index("ix_dishes_primary_protein", ["primary_protein"])

    with op.batch_alter_table("menu_entries") as batch:
        batch.drop_constraint("uq_menu_entries_menu_slot", type_="unique")
        batch.add_column(
            sa.Column("course", sa.String(length=16), server_default="main", nullable=False)
        )
        batch.create_check_constraint(
            "ck_menu_entries_course",
            "course IN ('main', 'complement')",
        )
        batch.create_unique_constraint(
            "uq_menu_entries_menu_slot_course",
            ["menu_id", "day_index", "slot", "course"],
        )
        batch.create_index("ix_menu_entries_course", ["course"])


def downgrade() -> None:
    with op.batch_alter_table("menu_entries") as batch:
        batch.drop_index("ix_menu_entries_course")
        batch.drop_constraint("uq_menu_entries_menu_slot_course", type_="unique")
        batch.drop_constraint("ck_menu_entries_course", type_="check")
        batch.drop_column("course")
        batch.create_unique_constraint(
            "uq_menu_entries_menu_slot",
            ["menu_id", "day_index", "slot"],
        )

    with op.batch_alter_table("dishes") as batch:
        batch.drop_index("ix_dishes_primary_protein")
        batch.drop_index("ix_dishes_role")
        batch.drop_constraint("ck_dishes_role", type_="check")
        batch.drop_column("primary_protein")
        batch.drop_column("role")
