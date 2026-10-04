"""sync-captured flow facts

State types and a detail on events; state type, labels and parent on work
items (ADR-0011). The Linear mapping stops deriving BLOCKED/UNBLOCKED from
labels (blocked is decided at read time from raw label events), so the
stored Linear-derived ones (external_ids ending ":blocked"/":unblocked")
are deleted; REST-created blocked events carry other external_ids and stay.

Revision ID: e5b8d2a7c913
Revises: c0f1a6e5b2d4
Create Date: 2026-10-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b8d2a7c913"
down_revision: str | Sequence[str] | None = "c0f1a6e5b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("from_state_type", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("to_state_type", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("detail", sa.String(length=255), nullable=True))
    with op.batch_alter_table("work_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("state_type", sa.String(length=16), nullable=True))
        batch_op.add_column(
            sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(sa.Column("parent_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_work_items_parent_id", ["parent_id"], unique=False)
        batch_op.create_foreign_key("fk_work_items_parent_id", "work_items", ["parent_id"], ["id"])
    op.execute(
        sa.text(
            "DELETE FROM events WHERE external_id LIKE :blocked OR external_id LIKE :unblocked"
        ).bindparams(blocked="%:blocked", unblocked="%:unblocked")
    )


def downgrade() -> None:
    """Drop the columns. Purged events aren't restored; a sync on the old code re-derives them."""
    with op.batch_alter_table("work_items", schema=None) as batch_op:
        batch_op.drop_constraint("fk_work_items_parent_id", type_="foreignkey")
        batch_op.drop_index("ix_work_items_parent_id")
        batch_op.drop_column("parent_id")
        batch_op.drop_column("labels")
        batch_op.drop_column("state_type")
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_column("detail")
        batch_op.drop_column("to_state_type")
        batch_op.drop_column("from_state_type")
