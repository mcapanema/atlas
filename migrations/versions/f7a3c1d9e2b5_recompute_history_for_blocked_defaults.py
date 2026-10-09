"""recompute snapshot history for the new blocked defaults

ADR-0015 turned every blocked source on by default: blocked workflow
states (added with #116), Portuguese blocked words and Linear "blocked by"
relations. Stored metric snapshots were computed under the old defaults —
blocked time and flow efficiency read 0m / 100% — so mark every
organization's recompute "running": the app's lifespan resumes those as a
snapshot-history rewrite on the next start (RecomputeRunner.resume). An
organization without an overrides row gets an empty one, as
`save_recompute` would create.

Revision ID: f7a3c1d9e2b5
Revises: e3aa72adf0b8
Create Date: 2026-10-08 23:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "f7a3c1d9e2b5"
down_revision: str | Sequence[str] | None = "e3aa72adf0b8"
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
