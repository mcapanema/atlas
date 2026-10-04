"""create metric_rule_overrides

Revision ID: c0f1a6e5b2d4
Revises: b1c0ed5e0a01
Create Date: 2026-10-03 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0f1a6e5b2d4"
down_revision: str | Sequence[str] | None = "b1c0ed5e0a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "metric_rule_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("recompute_state", sa.String(length=16), nullable=False),
        sa.Column("recompute_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recompute_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recompute_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("metric_rule_overrides", schema=None) as batch_op:
        batch_op.create_index(
            "ix_metric_rule_overrides_org_team", ["organization_id", "team_id"], unique=True
        )
        batch_op.create_index(
            "ix_metric_rule_overrides_org_default",
            ["organization_id"],
            unique=True,
            sqlite_where=sa.text("team_id IS NULL"),
            postgresql_where=sa.text("team_id IS NULL"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("metric_rule_overrides", schema=None) as batch_op:
        batch_op.drop_index("ix_metric_rule_overrides_org_default")
        batch_op.drop_index("ix_metric_rule_overrides_org_team")
    op.drop_table("metric_rule_overrides")
