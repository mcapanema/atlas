from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.scope import ScopeSampleLoader
from app.domain.events.entities import Event, EventType
from app.domain.work_items.entities import WorkItem

NOW = datetime(2026, 7, 10, tzinfo=UTC)


class InMemoryWorkItemRepository:
    def __init__(self, items: list[WorkItem]) -> None:
        self._items = items

    async def add(self, work_item: WorkItem) -> None:
        self._items.append(work_item)

    async def update(self, work_item: WorkItem) -> None:
        pass

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        items = [
            item
            for item in self._items
            if (team_id is None or item.team_id == team_id)
            and (project_id is None or item.project_id == project_id)
        ]
        items = items[offset:]
        return items if limit is None else items[:limit]

    async def count(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        return len(await self.list(team_id=team_id, project_id=project_id))

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return next((i for i in self._items if i.id == work_item_id), None)

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        return next((i for i in self._items if i.external_id == external_id), None)


class InMemoryEventRepository:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    async def add(self, event: Event) -> None:
        self._events.append(event)

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return sorted(
            (e for e in self._events if e.work_item_id == work_item_id),
            key=lambda e: e.occurred_at,
        )

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        wanted = set(work_item_ids)
        return sorted(
            (e for e in self._events if e.work_item_id in wanted),
            key=lambda e: e.occurred_at,
        )

    async def get_by_external_id(self, external_id: str) -> Event | None:
        return next((e for e in self._events if e.external_id == external_id), None)

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        wanted = set(external_ids)
        return {
            e.external_id
            for e in self._events
            if e.external_id is not None and e.external_id in wanted
        }


def _item(team_id: UUID) -> WorkItem:
    return WorkItem(team_id=team_id, title="Item")


def _event(item: WorkItem, type_: EventType, days_ago: int) -> Event:
    return Event(
        work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days_ago)
    )


async def test_load_assembles_streams_samples_and_item_count() -> None:
    team_id = uuid4()
    done, doing, backlog = _item(team_id), _item(team_id), _item(team_id)
    events = [
        _event(done, EventType.CREATED, 10),
        _event(done, EventType.COMPLETED, 2),
        _event(doing, EventType.CREATED, 5),
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([done, doing, backlog]),
        InMemoryEventRepository(events),
    )

    scope = await loader.load(team_id=team_id)

    assert scope.item_count == 3  # eventless backlog still counts
    assert len(scope.streams) == 2  # backlog has no events, so no stream
    assert len(scope.samples) == 2
    assert sum(1 for s in scope.samples if s.completed_at is not None) == 1


async def test_load_streams_are_ordered_by_occurred_at() -> None:
    team_id = uuid4()
    item = _item(team_id)
    # inserted out of order; the loader must hand back chronological streams
    events = [
        _event(item, EventType.COMPLETED, 2),
        _event(item, EventType.CREATED, 10),
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([item]), InMemoryEventRepository(events)
    )

    scope = await loader.load(team_id=team_id)

    (stream,) = scope.streams
    assert [e.type for e in stream] == [EventType.CREATED, EventType.COMPLETED]


async def test_load_scopes_by_team_and_project() -> None:
    team_id, project_id = uuid4(), uuid4()
    mine = WorkItem(team_id=team_id, title="Mine", project_id=project_id)
    other_team = WorkItem(team_id=uuid4(), title="Theirs")
    other_project = WorkItem(team_id=team_id, title="Elsewhere")
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([mine, other_team, other_project]),
        InMemoryEventRepository([]),
    )

    by_team = await loader.load(team_id=team_id)
    by_project = await loader.load(project_id=project_id)

    assert by_team.item_count == 2
    assert by_project.item_count == 1
