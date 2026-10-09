"""retire the predictability_worst_ratio metric rule

ADR-0016 replaced the lead-time spread score, and its
`predictability_worst_ratio` rule, with a service-level hit rate. A stored
override of the retired rule is ignored, but the write schema forbids
unknown keys, so it could never be cleared, and the resolver logged it as
unknown on every scope load. Drop the key from every overrides row; every
other key is kept as is.

Revision ID: c4e7a2d9b1f3
Revises: 5b3beedabfc0
Create Date: 2026-10-09 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e7a2d9b1f3"
down_revision: str | Sequence[str] | None = "5b3beedabfc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRED = "predictability_worst_ratio"
_overrides = sa.table(
    "metric_rule_overrides",
    sa.column("id", sa.Uuid),
    sa.column("overrides", sa.JSON),
)


def upgrade() -> None:
    """Remove the retired rule from every stored overrides row."""
    connection = op.get_bind()
    for row_id, overrides in connection.execute(sa.select(_overrides.c.id, _overrides.c.overrides)):
        if _RETIRED in overrides:
            kept = {name: value for name, value in overrides.items() if name != _RETIRED}
            connection.execute(
                _overrides.update().where(_overrides.c.id == row_id).values(overrides=kept)
            )


def downgrade() -> None:
    """Nothing to restore: the old code reads a missing rule as its built-in value."""
