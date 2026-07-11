from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.events.service import EventService
from app.domain.events.entities import Event, EventType
from app.domain.events.timeline import StatePeriod


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: list[Event] = []

    async def add(self, event: Event) -> None:
        self._events.append(event)

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return [e for e in self._events if e.work_item_id == work_item_id]

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        wanted = set(work_item_ids)
        return [e for e in self._events if e.work_item_id in wanted]

    async def get_by_external_id(self, external_id: str) -> Event | None:
        return next((e for e in self._events if e.external_id == external_id), None)

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        wanted = set(external_ids)
        return {
            e.external_id
            for e in self._events
            if e.external_id is not None and e.external_id in wanted
        }


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
