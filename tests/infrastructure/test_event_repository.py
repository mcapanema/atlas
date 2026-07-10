from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events.entities import Event, EventType
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def _work_item_id(session: AsyncSession) -> UUID:
    """FK enforcement is on (see conftest) — events need a real work item."""
    team = Team(organization_id=uuid4(), name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    item = WorkItem(team_id=team.id, title="Item")
    await SqlAlchemyWorkItemRepository(session).add(item)
    return item.id


async def test_add_then_list_orders_by_occurred_at(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    work_item_id = await _work_item_id(session)
    await repo.add(
        Event(
            work_item_id=work_item_id,
            type=EventType.STARTED,
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=work_item_id,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    events = await repo.list_for_work_item(work_item_id)

    assert [e.type for e in events] == [EventType.CREATED, EventType.STARTED]


async def test_list_scopes_by_work_item(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_a, item_b = await _work_item_id(session), await _work_item_id(session)
    await repo.add(
        Event(
            work_item_id=item_a,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_b,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert len(await repo.list_for_work_item(item_a)) == 1


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    event = Event(
        work_item_id=await _work_item_id(session),
        type=EventType.STATE_CHANGED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        from_state="backlog",
        to_state="in_progress",
        external_id="lin_hist_1",
    )
    await repo.add(event)

    fetched = await repo.get_by_external_id("lin_hist_1")

    assert fetched is not None
    assert fetched.id == event.id
    assert fetched.from_state == "backlog"
    assert fetched.to_state == "in_progress"
    assert await repo.get_by_external_id("nope") is None


async def test_list_for_work_items_filters_and_orders(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_a, item_b, item_c = (
        await _work_item_id(session),
        await _work_item_id(session),
        await _work_item_id(session),
    )
    await repo.add(
        Event(
            work_item_id=item_b,
            type=EventType.STARTED,
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_a,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_c,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    events = await repo.list_for_work_items([item_a, item_b])

    assert [(e.work_item_id, e.type) for e in events] == [
        (item_a, EventType.CREATED),
        (item_b, EventType.STARTED),
    ]


async def test_list_for_work_items_with_no_ids_is_empty(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    await repo.add(
        Event(
            work_item_id=await _work_item_id(session),
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert await repo.list_for_work_items([]) == []
