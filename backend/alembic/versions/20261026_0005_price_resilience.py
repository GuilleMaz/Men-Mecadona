"""resiliencia de precios e índices de entrega

Revision ID: 20261026_0005
Revises: 20261026_0004
Create Date: 2026-10-26 00:00:04

Añade el ticket anterior y la fecha de revalidación para poder mostrar el delta
de precios sin romper el snapshot válido del menú. También añade índices para el
historial y para localizar la última copia de precios de 22002/4389.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0005"
down_revision: str | None = "20261026_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "menus",
        sa.Column("previous_ticket_cents", sa.Integer(), nullable=True),
    )
    op.add_column(
        "menus",
        sa.Column("revalidated_at", sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table("menus") as batch:
        batch.create_check_constraint(
            "ck_menus_previous_ticket",
            "previous_ticket_cents IS NULL OR previous_ticket_cents >= 0",
        )
        batch.create_index(
            "ix_menus_profile_created_at",
            ["profile_id", "created_at"],
        )
    op.create_index(
        "ix_sync_runs_status_finished_at",
        "sync_runs",
        ["status", "finished_at"],
    )
    op.create_index(
        "ix_products_last_sync_run_id",
        "products",
        ["last_sync_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_products_last_sync_run_id", table_name="products")
    op.drop_index("ix_sync_runs_status_finished_at", table_name="sync_runs")
    with op.batch_alter_table("menus") as batch:
        batch.drop_index("ix_menus_profile_created_at")
        batch.drop_constraint("ck_menus_previous_ticket", type_="check")
    op.drop_column("menus", "revalidated_at")
    op.drop_column("menus", "previous_ticket_cents")
