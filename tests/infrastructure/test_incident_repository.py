from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.incidents.entities import ServiceIncident
from app.domain.organizations.entities import Organization
from app.infrastructure.repositories.incidents import SqlAlchemyServiceIncidentRepository
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository

T0 = datetime(2026, 10, 1, tzinfo=UTC)


async def _org(session: AsyncSession, name: str) -> UUID:
    org = Organization(name=name)
    await SqlAlchemyOrganizationRepository(session).add(org)
    return org.id


def _incident(organization_id: UUID, external_id: str) -> ServiceIncident:
    return ServiceIncident(
        organization_id=organization_id,
        external_id=external_id,
        title="Checkout down",
        opened_at=T0,
        restored_at=datetime(2026, 10, 1, 2, tzinfo=UTC),
        services=("api", "web"),
        severity="SEV-2",
        url="https://example.test/i",
    )


async def test_incident_round_trips_with_services_as_a_tuple(session: AsyncSession) -> None:
    repo = SqlAlchemyServiceIncidentRepository(session)
    incident = _incident(await _org(session, "Acme"), "i1")
    await repo.add(incident)
    session.expunge_all()

    assert (await repo.get_by_external_ids(["i1", "nope"])) == {"i1": incident}


async def test_update_changes_the_stored_row(session: AsyncSession) -> None:
    repo = SqlAlchemyServiceIncidentRepository(session)
    incident = _incident(await _org(session, "Acme"), "i1")
    await repo.add(incident)
    incident.title = "Renamed"
    await repo.update(incident)

    assert (await repo.get_by_external_ids(["i1"]))["i1"].title == "Renamed"


async def test_list_filters_by_organization_and_get_spans_organizations(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyServiceIncidentRepository(session)
    org_a, org_b = await _org(session, "A"), await _org(session, "B")
    await repo.add(_incident(org_a, "i1"))
    await repo.add(_incident(org_b, "i2"))

    assert [i.external_id for i in await repo.list(org_a)] == ["i1"]
    assert set(await repo.get_by_external_ids(["i1", "i2"])) == {"i1", "i2"}
