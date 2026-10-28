"""recompute snapshot history for multi-team projects

A project whose items span several teams now reads the workspace rules
instead of its home team's. Its stored snapshots were computed under the
home team's rules, so mark the recompute "running" for every organization
that holds such a project: the app's lifespan resumes those as a
snapshot-history rewrite on the next start (RecomputeRunner.resume). An
organization without an overrides row gets an empty one, as
`save_recompute` would create.

Revision ID: c4e8a2b7d913
Revises: 8b2d5f6a1c47
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a2b7d913"
down_revision: str | Sequence[str] | None = "8b2d5f6a1c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_teams = sa.table("teams", sa.column("id", sa.Uuid), sa.column("organization_id", sa.Uuid))
_projects = sa.table("projects", sa.column("id", sa.Uuid), sa.column("team_id", sa.Uuid))
_items = sa.table("work_items", sa.column("project_id", sa.Uuid), sa.column("team_id", sa.Uuid))
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
    """Mark the history of every organization holding a multi-team project for a recompute."""
    connection = op.get_bind()
    now = datetime.now(UTC)
    multi_team = (
        sa.select(_items.c.project_id)
        .group_by(_items.c.project_id)
        .having(sa.func.count(sa.distinct(_items.c.team_id)) > 1)
    )
    affected = set(
        connection.scalars(
            sa.select(_teams.c.organization_id)
            .join(_projects, _projects.c.team_id == _teams.c.id)
            .where(_projects.c.id.in_(multi_team))
        )
    )
    if not affected:
        return
    with_row = set(
        connection.scalars(
            sa.select(_overrides.c.organization_id).where(
                _overrides.c.team_id.is_(None), _overrides.c.organization_id.in_(affected)
            )
        )
    )
    connection.execute(
        _overrides.update()
        .where(_overrides.c.team_id.is_(None), _overrides.c.organization_id.in_(affected))
        .values(recompute_state="running", recompute_started_at=now, recompute_error=None)
    )
    if missing := affected - with_row:
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
    """Nothing to undo: a recompute under the old code rewrites with the old rules."""
