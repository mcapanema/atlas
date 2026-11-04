from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.codebases.sync import BACKFILL
from app.application.incidents.sync import IncidentSyncService
from app.domain.sync.source import SourceIncident
from tests.fakes import InMemoryIncidentSource, InMemoryServiceIncidentRepository

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
T1 = datetime(2026, 10, 20, 9, tzinfo=UTC)
ORG = uuid4()


def _source_incident(external_id: str, severity: str | None = None) -> SourceIncident:
    return SourceIncident(external_id=external_id, title="Down", opened_at=T1, severity=severity)


async def test_sync_stores_new_incidents_and_is_idempotent() -> None:
    source = InMemoryIncidentSource([_source_incident("i1"), _source_incident("i2")])
    repo = InMemoryServiceIncidentRepository()
    service = IncidentSyncService(source, repo)

    assert (await service.sync(ORG, now=NOW)).incidents == 2
    assert (await service.sync(ORG, now=NOW)).incidents == 0
    assert len(await repo.list(ORG)) == 2


async def test_sync_updates_a_restored_incident() -> None:
    source = InMemoryIncidentSource([_source_incident("i1")])
    repo = InMemoryServiceIncidentRepository()
    service = IncidentSyncService(source, repo)
    await service.sync(ORG, now=NOW)

    restored = T1 + timedelta(hours=1)
    source.incidents = [replace(source.incidents[0], restored_at=restored)]

    assert (await service.sync(ORG, now=NOW)).incidents == 1
    assert (await repo.list(ORG))[0].restored_at == restored


async def test_sync_asks_for_incidents_since_the_backfill() -> None:
    source = InMemoryIncidentSource()
    await IncidentSyncService(source, InMemoryServiceIncidentRepository()).sync(ORG, now=NOW)

    assert source.calls == [NOW - BACKFILL]


async def test_an_incident_another_organization_owns_is_not_re_inserted() -> None:
    org_b = uuid4()
    source = InMemoryIncidentSource([_source_incident("i1")])
    repo = InMemoryServiceIncidentRepository()
    service = IncidentSyncService(source, repo)
    await service.sync(ORG, now=NOW)
    source.incidents = [_source_incident("i1", severity="SEV-1")]

    assert (await service.sync(org_b, now=NOW)).incidents == 1

    assert await repo.list(org_b) == []
    [stored] = await repo.list(ORG)
    assert stored.severity == "SEV-1"
