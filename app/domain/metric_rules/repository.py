from typing import Protocol
from uuid import UUID

from app.domain.metric_rules.entities import RecomputeStatus, RuleOverrides


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
        """Insert (with its recompute status), or update an existing row's overrides only."""
        ...

    async def save_recompute(self, organization_id: UUID, status: RecomputeStatus) -> None:
        """Write only the organization row's recompute status; insert it empty if missing."""
        ...
