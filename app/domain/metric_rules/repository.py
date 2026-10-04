from typing import Protocol
from uuid import UUID

from app.domain.metric_rules.entities import RuleOverrides


class MetricRuleOverridesRepository(Protocol):
    """Persistence port for the metric-rule override layers."""

    async def get(
        self, organization_id: UUID, *, team_id: UUID | None = None
    ) -> RuleOverrides | None:
        """The organization's row (team_id None) or one team's row."""
        ...

    async def list_for_organization(self, organization_id: UUID) -> list[RuleOverrides]:
        """The organization's row and every team row under it."""
        ...

    async def list_recomputing(self) -> list[RuleOverrides]:
        """Organization rows whose recompute state is "running"."""
        ...

    async def save(self, overrides: RuleOverrides) -> None:
        """Insert, or replace the row with the same id."""
        ...
