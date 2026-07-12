"""created_at must come back tz-aware from SQLite on every persisted aggregate.

SQLite's DATETIME drops tzinfo on read; the UTCDateTime decorator reattaches
UTC. Events were fixed in Phase 2a — this pins the other four tables (M13).
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.organizations.entities import Organization
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def test_created_at_round_trips_timezone_aware(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(name="Acme")
    team = Team(organization_id=org.id, name="Platform")
    project = Project(team_id=team.id, name="Apollo")
    item = WorkItem(team_id=team.id, title="Ship it")

    async with sessionmaker() as write_session:
        await SqlAlchemyOrganizationRepository(write_session).add(org)
        await SqlAlchemyTeamRepository(write_session).add(team)
        await SqlAlchemyProjectRepository(write_session).add(project)
        await SqlAlchemyWorkItemRepository(write_session).add(item)
        await write_session.commit()

    # A second session forces a real DB read (no identity-map shortcut).
    async with sessionmaker() as read_session:
        loaded = [
            await SqlAlchemyOrganizationRepository(read_session).get(org.id),
            await SqlAlchemyTeamRepository(read_session).get(team.id),
            await SqlAlchemyProjectRepository(read_session).get(project.id),
            await SqlAlchemyWorkItemRepository(read_session).get(item.id),
        ]

    for entity in loaded:
        assert entity is not None
        assert entity.created_at.tzinfo is not None
