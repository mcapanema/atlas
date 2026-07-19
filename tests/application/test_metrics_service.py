from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.metrics.service import MetricsService
from app.application.scope import ScopeSamples
from app.domain.events.entities import Event, EventType
from app.domain.metrics.samples import derive_flow_sample
from app.domain.work_items.entities import WorkItem
from tests.fakes import InMemoryEventRepository, InMemoryWorkItemRepository

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _item(team_id: UUID) -> WorkItem:
    return WorkItem(team_id=team_id, title="Item")


def _event(item: WorkItem, type_: EventType, days_ago: int) -> Event:
    return Event(
        work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days_ago)
    )


async def test_team_metrics_across_completed_and_in_progress_items() -> None:
    team_id = uuid4()
    done, doing = _item(team_id), _item(team_id)
    service = MetricsService(
        InMemoryWorkItemRepository([done, doing]),
        InMemoryEventRepository(
            [
                _event(done, EventType.CREATED, 10),
                _event(done, EventType.STARTED, 8),
                _event(done, EventType.COMPLETED, 2),
                _event(doing, EventType.CREATED, 5),
                _event(doing, EventType.STARTED, 4),
            ]
        ),
    )

    metrics = await service.get_flow_metrics(team_id=team_id, now=NOW)

    assert metrics.completed == 1
    assert metrics.wip == 1
    assert metrics.lead_time is not None
    assert metrics.lead_time.p50 == timedelta(days=8)
    assert metrics.cycle_time is not None
    assert metrics.cycle_time.p50 == timedelta(days=6)
    assert metrics.flow_efficiency == 1.0


async def test_team_metrics_scope_to_the_requested_team() -> None:
    other_teams_item = _item(uuid4())
    service = MetricsService(
        InMemoryWorkItemRepository([other_teams_item]),
        InMemoryEventRepository(
            [
                _event(other_teams_item, EventType.CREATED, 10),
                _event(other_teams_item, EventType.COMPLETED, 2),
            ]
        ),
    )

    metrics = await service.get_flow_metrics(team_id=uuid4(), now=NOW)

    assert metrics.completed == 0
    assert metrics.wip == 0
    assert metrics.lead_time is None


async def test_window_days_is_forwarded() -> None:
    team_id = uuid4()
    done = _item(team_id)
    service = MetricsService(
        InMemoryWorkItemRepository([done]),
        InMemoryEventRepository(
            [
                _event(done, EventType.CREATED, 60),
                _event(done, EventType.COMPLETED, 45),
            ]
        ),
    )

    narrow = await service.get_flow_metrics(team_id=team_id, window_days=30, now=NOW)
    wide = await service.get_flow_metrics(team_id=team_id, window_days=90, now=NOW)

    assert narrow.completed == 0
    assert wide.completed == 1


async def test_metrics_scoped_by_project() -> None:
    team_id = uuid4()
    project_id = uuid4()
    in_project = WorkItem(team_id=team_id, title="In project", project_id=project_id)
    outside = WorkItem(team_id=team_id, title="Outside")
    events = [
        Event(
            work_item_id=in_project.id,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(days=1),
        ),
        Event(
            work_item_id=outside.id,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(days=1),
        ),
    ]
    service = MetricsService(
        InMemoryWorkItemRepository([in_project, outside]),
        InMemoryEventRepository(events),
    )

    metrics = await service.get_flow_metrics(project_id=project_id, now=NOW)

    assert metrics.completed == 1


async def test_flow_history_for_team() -> None:
    team_id = uuid4()
    item = WorkItem(team_id=team_id, title="Ship")
    events = [
        Event(
            work_item_id=item.id,
            type=EventType.CREATED,
            occurred_at=NOW - timedelta(days=5),
        ),
        Event(
            work_item_id=item.id,
            type=EventType.COMPLETED,
            occurred_at=NOW - timedelta(days=1),
        ),
    ]
    service = MetricsService(
        InMemoryWorkItemRepository([item]), InMemoryEventRepository(events)
    )

    history = await service.get_flow_history(team_id=team_id, window_days=14, now=NOW)

    assert history.window_end == NOW
    assert len(history.days) == 15
    assert history.days[-1].done == 1
    assert sum(b.completed for b in history.buckets) == 1


async def test_lead_time_distribution_for_team() -> None:
    team_id = uuid4()
    done = _item(team_id)
    service = MetricsService(
        InMemoryWorkItemRepository([done]),
        InMemoryEventRepository(
            [
                _event(done, EventType.CREATED, 10),
                _event(done, EventType.COMPLETED, 2),
            ]
        ),
    )

    dist = await service.get_lead_time_distribution(team_id=team_id, now=NOW)

    assert dist.window_end == NOW
    assert sum(b.count for b in dist.bins) == 1
    assert dist.bins[8].count == 1  # 8-day lead time


async def test_precomputed_scope_skips_repository_loading() -> None:
    # Repositories are empty — if the result reflects the passed-in scope,
    # the service used it instead of loading.
    service = MetricsService(InMemoryWorkItemRepository([]), InMemoryEventRepository([]))
    item = _item(uuid4())
    stream = [_event(item, EventType.CREATED, 10), _event(item, EventType.COMPLETED, 2)]
    sample = derive_flow_sample(stream)
    assert sample is not None
    scope = ScopeSamples(streams=[stream], samples=[sample], item_count=1)

    metrics = await service.get_flow_metrics(now=NOW, scope=scope)
    history = await service.get_flow_history(now=NOW, scope=scope)
    distribution = await service.get_lead_time_distribution(now=NOW, scope=scope)

    assert metrics.completed == 1
    assert sum(b.completed for b in history.buckets) == 1
    assert sum(b.count for b in distribution.bins) == 1


async def test_aging_wip_lists_in_progress_items_oldest_first() -> None:
    team_id = uuid4()
    old, young, done = _item(team_id), _item(team_id), _item(team_id)
    service = MetricsService(
        InMemoryWorkItemRepository([old, young, done]),
        InMemoryEventRepository(
            [
                _event(old, EventType.CREATED, 12),
                _event(old, EventType.STARTED, 10),
                _event(young, EventType.CREATED, 3),
                _event(young, EventType.STARTED, 2),
                _event(done, EventType.CREATED, 9),
                _event(done, EventType.STARTED, 8),
                _event(done, EventType.COMPLETED, 1),
            ]
        ),
    )

    aging = await service.get_aging_wip(team_id=team_id, now=NOW)

    assert [a.work_item_id for a in aging.items] == [old.id, young.id]
    assert aging.items[0].age == timedelta(days=10)
    assert aging.cycle_time_p85 == timedelta(days=7)
    assert aging.items[0].over_p85 is True
    assert aging.items[1].over_p85 is False


async def test_delivery_health_for_team() -> None:
    team_id = uuid4()
    done, doing = _item(team_id), _item(team_id)
    service = MetricsService(
        InMemoryWorkItemRepository([done, doing]),
        InMemoryEventRepository(
            [
                _event(done, EventType.CREATED, 10),
                _event(done, EventType.STARTED, 8),
                _event(done, EventType.COMPLETED, 2),
                _event(doing, EventType.CREATED, 5),
                _event(doing, EventType.STARTED, 4),
            ]
        ),
    )

    health = await service.get_delivery_health(team_id=team_id, now=NOW)

    assert health.score is not None
    assert health.band in ("healthy", "warning", "critical")
    assert any(c.name == "risk" for c in health.components)
