from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.sync_schedules.entities import SyncRun, SyncSchedule


class SyncScheduleRepository(Protocol):
    """Port for auto-sync schedules, one per organization. Implemented in Infrastructure."""

    async def get(self, organization_id: UUID) -> SyncSchedule | None: ...

    async def list_enabled(self) -> list[SyncSchedule]: ...

    async def save(self, schedule: SyncSchedule) -> None:
        """Insert, or update an existing schedule's settings, never its last run."""
        ...

    async def record_run(self, organization_id: UUID, run: SyncRun) -> None:
        """Write only the schedule's last run; a no-op if the organization has none."""
        ...

    async def record_manual_sync(self, organization_id: UUID, at: datetime) -> None:
        """Write only when a manual sync finished; a no-op if the organization has none."""
        ...
