from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events.entities import Event, EventType
from app.infrastructure.repositories.events import SqlAlchemyEventRepository


async def test_add_then_list_orders_by_occurred_at(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    work_item_id = uuid4()
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
    item_a, item_b = uuid4(), uuid4()
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
        work_item_id=uuid4(),
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
