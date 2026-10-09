from datetime import UTC, datetime
from uuid import uuid4

from app.application.events.service import EventService
from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import StatePeriod
from app.domain.metric_rules.entities import MetricRules
from tests.fakes import InMemoryEventRepository


async def test_record_event_persists_and_returns() -> None:
    repo = InMemoryEventRepository()
    service = EventService(repo)
    work_item_id = uuid4()

    event = await service.record_event(
        work_item_id=work_item_id,
        type=EventType.STARTED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert event.work_item_id == work_item_id
    assert event.type is EventType.STARTED
    assert await repo.list_for_work_item(work_item_id) == [event]


async def test_list_for_work_item_scopes_by_item() -> None:
    repo = InMemoryEventRepository()
    service = EventService(repo)
    item_a, item_b = uuid4(), uuid4()
    await service.record_event(
        work_item_id=item_a, type=EventType.CREATED, occurred_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await service.record_event(
        work_item_id=item_b, type=EventType.CREATED, occurred_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    events = await service.list_for_work_item(item_a)

    assert [e.work_item_id for e in events] == [item_a]


async def test_get_timeline_derives_periods_from_recorded_events() -> None:
    repo = InMemoryEventRepository()
    service = EventService(repo)
    work_item_id = uuid4()
    await service.record_event(
        work_item_id=work_item_id,
        type=EventType.CREATED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await service.record_event(
        work_item_id=work_item_id,
        type=EventType.STARTED,
        occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        from_state="Backlog",
        to_state="In Progress",
    )

    timeline = await service.get_timeline(work_item_id)

    assert timeline.state_periods == (
        StatePeriod(
            state="Backlog",
            entered_at=datetime(2026, 1, 1, tzinfo=UTC),
            exited_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        StatePeriod(
            state="In Progress",
            entered_at=datetime(2026, 1, 3, tzinfo=UTC),
            exited_at=None,
        ),
    )
    assert timeline.blocked_periods == ()


async def test_get_timeline_is_empty_for_unknown_work_item() -> None:
    service = EventService(InMemoryEventRepository())

    timeline = await service.get_timeline(uuid4())

    assert timeline.state_periods == ()
    assert timeline.blocked_periods == ()


async def test_timeline_blocked_periods_follow_the_rules() -> None:
    item_id = uuid4()
    at = datetime(2026, 9, 1, tzinfo=UTC)
    repo = InMemoryEventRepository(
        [
            Event(
                work_item_id=item_id, type=EventType.BLOCKER_ADDED, occurred_at=at, detail="DEP-1"
            ),
        ]
    )
    service = EventService(repo)

    off = await service.get_timeline(item_id, MetricRules(blocked_by_relations=False))
    default = await service.get_timeline(item_id)

    assert off.blocked_periods == ()
    assert [p.started_at for p in default.blocked_periods] == [at]
