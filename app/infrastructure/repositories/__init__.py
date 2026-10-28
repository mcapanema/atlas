# Importing each repository module registers its ORM model on Base.metadata,
# so a single `import app.infrastructure.repositories` makes the whole schema
# visible to Alembic autogenerate and to test table creation.
from app.infrastructure.repositories import (
    advice_runs,
    events,
    metric_rules,
    organizations,
    people,
    personas,
    projects,
    snapshots,
    sync_schedules,
    teams,
    work_items,
)

__all__ = [
    "advice_runs",
    "events",
    "metric_rules",
    "organizations",
    "people",
    "personas",
    "projects",
    "snapshots",
    "sync_schedules",
    "teams",
    "work_items",
]
