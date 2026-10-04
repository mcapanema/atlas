"""purge Linear-derived blocked/unblocked events

The blocked-label match used a "block" substring and flagged the
"regras-blockly" label as blocked. Events are insert-only, so tightening
the match can't remove what was stored: delete every Linear-derived
blocked/unblocked event (their external_ids end in ":blocked" /
":unblocked") and let the next sync re-insert the legitimate ones. Events
recorded through the events API carry other external_ids and stay.

Revision ID: b1c0ed5e0a01
Revises: 28361edf3e47
Create Date: 2026-10-03 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c0ed5e0a01"
down_revision: str | Sequence[str] | None = "28361edf3e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Delete the stored Linear-derived blocked/unblocked events."""
    op.execute(
        sa.text(
            "DELETE FROM events WHERE external_id LIKE :blocked OR external_id LIKE :unblocked"
        ).bindparams(blocked="%:blocked", unblocked="%:unblocked")
    )


def downgrade() -> None:
    """Nothing to restore: the next sync re-derives the legitimate events."""
