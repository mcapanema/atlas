from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.scope import ScopeSampleLoader
from app.domain.events.entities import Event, EventType
from app.domain.work_items.entities import WorkItem, WorkItemType
from tests.fakes import InMemoryEventRepository, InMemoryWorkItemRepository

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _item(team_id: UUID) -> WorkItem:
    return WorkItem(team_id=team_id, title="Item")


def _event(item: WorkItem, type_: EventType, days_ago: int) -> Event:
    return Event(work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days_ago))


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
    loader = ScopeSampleLoader(InMemoryWorkItemRepository([item]), InMemoryEventRepository(events))

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


async def test_load_pairs_items_with_their_samples() -> None:
    team_id = uuid4()
    done, backlog = _item(team_id), _item(team_id)
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([done, backlog]),
        InMemoryEventRepository(
            [_event(done, EventType.CREATED, 10), _event(done, EventType.COMPLETED, 2)]
        ),
    )

    scope = await loader.load(team_id=team_id)

    assert [(item.id, sample) for item, sample in scope.items_with_samples] == [
        (done.id, scope.samples[0])
    ]


async def test_load_filters_by_type() -> None:
    team_id = uuid4()
    story = WorkItem(team_id=team_id, title="Story", type=WorkItemType.STORY)
    bug = WorkItem(team_id=team_id, title="Bug", type=WorkItemType.BUG)
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([story, bug]), InMemoryEventRepository([])
    )

    scope = await loader.load(team_id=team_id, types={WorkItemType.STORY})

    assert scope.item_count == 1


async def test_load_excludes_states_case_insensitively() -> None:
    team_id = uuid4()
    live = WorkItem(team_id=team_id, title="Live", state="in_progress")
    junk = WorkItem(team_id=team_id, title="Junk", state="Canceled")
    events = [_event(junk, EventType.CREATED, 10), _event(junk, EventType.STARTED, 9)]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([live, junk]), InMemoryEventRepository(events)
    )

    scope = await loader.load(team_id=team_id, exclude_states={"canceled"})

    assert scope.item_count == 1  # "Canceled" matched despite the capital C
    assert scope.streams == []  # the junk item's events are gone too


async def test_load_without_filters_is_unchanged() -> None:
    team_id = uuid4()
    item = WorkItem(team_id=team_id, title="Item", state="Canceled")
    loader = ScopeSampleLoader(InMemoryWorkItemRepository([item]), InMemoryEventRepository([]))

    scope = await loader.load(team_id=team_id)

    assert scope.item_count == 1


async def test_load_leaves_born_done_items_out_of_every_count() -> None:
    team_id = uuid4()
    logged, done, still_open = _item(team_id), _item(team_id), _item(team_id)
    events = [
        _event(logged, EventType.CREATED, 4),
        _event(logged, EventType.COMPLETED, 4),  # completed at its creation instant
        _event(done, EventType.CREATED, 10),
        _event(done, EventType.COMPLETED, 2),
        _event(still_open, EventType.CREATED, 5),
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([logged, done, still_open]),
        InMemoryEventRepository(events),
    )

    scope = await loader.load(team_id=team_id)

    assert scope.item_count == 2
    assert len(scope.streams) == 2
    assert [item for item, _ in scope.items_with_samples] == [done, still_open]
    assert not any(sample.born_done for sample in scope.samples)
    # Forecast remaining (item_count minus closed) is unchanged: the logged
    # item was closed anyway.
    closed = sum(1 for sample in scope.samples if sample.completed_at is not None)
    assert scope.item_count - closed == 1


async def test_filtered_without_filters_is_the_same_data() -> None:
    team_id = uuid4()
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([_item(team_id)]), InMemoryEventRepository([])
    )

    data = await loader.load_data(team_id=team_id)

    assert data.filtered() is data


async def test_filtered_matches_a_filtered_load() -> None:
    team_id = uuid4()
    story = WorkItem(team_id=team_id, title="Story", type=WorkItemType.STORY, state="Done")
    bug = WorkItem(team_id=team_id, title="Bug", type=WorkItemType.BUG)
    junk = WorkItem(team_id=team_id, title="Junk", type=WorkItemType.STORY, state="Canceled")
    events = [
        _event(story, EventType.CREATED, 10),
        _event(story, EventType.COMPLETED, 2),
        _event(bug, EventType.CREATED, 8),
        _event(junk, EventType.CREATED, 9),
        _event(junk, EventType.STARTED, 7),
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([story, bug, junk]), InMemoryEventRepository(events)
    )

    data = await loader.load_data(team_id=team_id)
    narrowed = data.filtered(types={WorkItemType.STORY}, exclude_states={"canceled"}).samples()
    loaded = await loader.load(
        team_id=team_id, types={WorkItemType.STORY}, exclude_states={"canceled"}
    )

    assert narrowed.item_count == loaded.item_count == 1
    assert narrowed.samples == loaded.samples
    assert narrowed.streams == loaded.streams
    assert narrowed.remaining_count == loaded.remaining_count
