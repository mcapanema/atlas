from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from app.application.codebases.sync import BACKFILL
from app.application.upsert import upsert_by_external_id
from app.domain.incidents.entities import ServiceIncident
from app.domain.incidents.repository import ServiceIncidentRepository
from app.domain.sync.port import IncidentSource


@dataclass(frozen=True)
class IncidentSyncSummary:
    """Count of incidents created or changed by one incident sync run."""

    incidents: int


class IncidentSyncService:
    """Copies an incident tracker's incidents into stored ServiceIncidents."""

    def __init__(self, source: IncidentSource, incidents: ServiceIncidentRepository) -> None:
        self._source = source
        self._incidents = incidents

    async def sync(self, organization_id: UUID, *, now: datetime) -> IncidentSyncSummary:
        fetched = await self._source.fetch_incidents(now - BACKFILL)
        rows = [
            ServiceIncident(
                organization_id=organization_id,
                external_id=i.external_id,
                title=i.title,
                opened_at=i.opened_at,
                restored_at=i.restored_at,
                services=i.services,
                severity=i.severity,
                url=i.url,
            )
            for i in fetched
        ]
        # An incident keeps the organization that first synced it; later syncs
        # update its fields in place and never re-insert it.
        stored = await self._incidents.get_by_external_ids([r.external_id for r in rows])
        rows = [
            replace(r, organization_id=stored[r.external_id].organization_id)
            if r.external_id in stored
            else r
            for r in rows
        ]
        return IncidentSyncSummary(incidents=await upsert_by_external_id(self._incidents, rows))
