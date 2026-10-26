"""relajaciones de variedad en menus

Revision ID: 20261026_0004
Revises: 20261026_0003
Create Date: 2026-10-26 00:00:03

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0004"
down_revision: str | None = "20261026_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "menus",
        sa.Column("violations", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "menus",
        sa.Column(
            "relaxation_codes_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    with op.batch_alter_table("menus") as batch:
        batch.create_check_constraint("ck_menus_violations", "violations >= 0")
        batch.create_check_constraint(
            "ck_menus_ticket_within_budget",
            "ticket_cents <= budget_cents",
        )


def downgrade() -> None:
    with op.batch_alter_table("menus") as batch:
        batch.drop_constraint("ck_menus_ticket_within_budget", type_="check")
        batch.drop_constraint("ck_menus_violations", type_="check")
    op.drop_column("menus", "relaxation_codes_json")
    op.drop_column("menus", "violations")
