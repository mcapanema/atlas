"""recompute snapshot history for the explicit blocked defaults

ADR-0025 turned two blocked sources off by default: the built-in label
pattern and Linear "blocked by" relations (blocked-named workflow states
and listed labels still count). Stored metric snapshots were computed with
both on, so mark every organization's recompute "running": the app's
lifespan resumes those as a snapshot-history rewrite on the next start
(RecomputeRunner.resume). An organization without an overrides row gets an
empty one, as `save_recompute` would create.

Revision ID: 259c45818cf8
Revises: 8e8cbbb28dcd
Create Date: 2026-10-29 12:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "259c45818cf8"
down_revision: str | Sequence[str] | None = "8e8cbbb28dcd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_organizations = sa.table("organizations", sa.column("id", sa.Uuid))
_overrides = sa.table(
    "metric_rule_overrides",
    sa.column("id", sa.Uuid),
    sa.column("organization_id", sa.Uuid),
    sa.column("team_id", sa.Uuid),
    sa.column("overrides", sa.JSON),
    sa.column("recompute_state", sa.String),
    sa.column("recompute_started_at", sa.DateTime(timezone=True)),
    sa.column("recompute_finished_at", sa.DateTime(timezone=True)),
    sa.column("recompute_error", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    """Mark every organization's snapshot history for a recompute."""
    connection = op.get_bind()
    now = datetime.now(UTC)
    with_row = set(
        connection.scalars(
            sa.select(_overrides.c.organization_id).where(_overrides.c.team_id.is_(None))
        )
    )
    connection.execute(
        _overrides.update()
        .where(_overrides.c.team_id.is_(None))
        .values(recompute_state="running", recompute_started_at=now, recompute_error=None)
    )
    missing = [
        org for org in connection.scalars(sa.select(_organizations.c.id)) if org not in with_row
    ]
    if missing:
        connection.execute(
            _overrides.insert(),
            [
                {
                    "id": uuid4(),
                    "organization_id": org,
                    "team_id": None,
                    "overrides": {},
                    "recompute_state": "running",
                    "recompute_started_at": now,
                    "updated_at": now,
                }
                for org in missing
            ],
        )


def downgrade() -> None:
    """Nothing to undo: a recompute under the old code rewrites with the old defaults."""
