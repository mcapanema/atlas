"""add team last_synced_at

Revision ID: a9d3e1f4c2b7
Revises: f7a3c1d9e2b5
Create Date: 2026-10-09 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d3e1f4c2b7"
down_revision: str | Sequence[str] | None = "f7a3c1d9e2b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.drop_column("last_synced_at")
