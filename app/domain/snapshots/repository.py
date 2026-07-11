from datetime import date
from typing import Protocol
from uuid import UUID

from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot


class MetricSnapshotRepository(Protocol):
    """Persistence port for MetricSnapshot."""

    async def add(self, snapshot: MetricSnapshot) -> None: ...

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[MetricSnapshot]:
        """Scope's snapshots ordered by captured_on ascending."""
        ...

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool: ...


class ForecastSnapshotRepository(Protocol):
    """Persistence port for ForecastSnapshot."""

    async def add(self, snapshot: ForecastSnapshot) -> None: ...

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[ForecastSnapshot]:
        """Scope's snapshots ordered by captured_on ascending."""
        ...

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool: ...
