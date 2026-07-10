from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events.entities import Event, EventType
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def test_duplicate_team_external_id_is_rejected(session: AsyncSession) -> None:
    repo = SqlAlchemyTeamRepository(session)
    await repo.add(Team(organization_id=uuid4(), name="A", external_id="lin_t1"))

    with pytest.raises(IntegrityError):
        await repo.add(Team(organization_id=uuid4(), name="B", external_id="lin_t1"))


async def test_duplicate_project_external_id_is_rejected(session: AsyncSession) -> None:
    team = Team(organization_id=uuid4(), name="A")
    await SqlAlchemyTeamRepository(session).add(team)
    repo = SqlAlchemyProjectRepository(session)
    await repo.add(Project(team_id=team.id, name="P1", external_id="lin_p1"))

    with pytest.raises(IntegrityError):
        await repo.add(Project(team_id=team.id, name="P2", external_id="lin_p1"))


async def test_duplicate_work_item_external_id_is_rejected(session: AsyncSession) -> None:
    team = Team(organization_id=uuid4(), name="A")
    await SqlAlchemyTeamRepository(session).add(team)
    repo = SqlAlchemyWorkItemRepository(session)
    await repo.add(WorkItem(team_id=team.id, title="A", external_id="lin_i1"))

    with pytest.raises(IntegrityError):
        await repo.add(WorkItem(team_id=team.id, title="B", external_id="lin_i1"))


async def test_duplicate_event_external_id_is_rejected(session: AsyncSession) -> None:
    team = Team(organization_id=uuid4(), name="A")
    await SqlAlchemyTeamRepository(session).add(team)
    item = WorkItem(team_id=team.id, title="A")
    await SqlAlchemyWorkItemRepository(session).add(item)
    repo = SqlAlchemyEventRepository(session)
    occurred = datetime(2026, 1, 1, tzinfo=UTC)
    await repo.add(
        Event(work_item_id=item.id, type=EventType.CREATED, occurred_at=occurred,
              external_id="lin_h1")
    )

    with pytest.raises(IntegrityError):
        await repo.add(
            Event(work_item_id=item.id, type=EventType.STARTED, occurred_at=occurred,
                  external_id="lin_h1")
        )


async def test_multiple_null_external_ids_are_allowed(session: AsyncSession) -> None:
    """Manually created entities carry no external_id — NULLs must not collide."""
    repo = SqlAlchemyTeamRepository(session)
    await repo.add(Team(organization_id=uuid4(), name="A"))
    await repo.add(Team(organization_id=uuid4(), name="B"))

    assert len(await repo.list()) == 2
