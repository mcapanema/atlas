from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.application.forecasting.service import ForecastService
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


def _steady_service(team_id: UUID) -> ForecastService:
    """Three items, one completed on each of the last three days."""
    items = [_item(team_id) for _ in range(3)]
    events = [_event(item, EventType.COMPLETED, days_ago) for days_ago, item in enumerate(items)]
    return ForecastService(InMemoryWorkItemRepository(items), InMemoryEventRepository(events))


async def test_forecast_counts_open_scope_including_eventless_backlog() -> None:
    team_id = uuid4()
    done, doing, backlog = _item(team_id), _item(team_id), _item(team_id)
    service = ForecastService(
        InMemoryWorkItemRepository([done, doing, backlog]),
        InMemoryEventRepository(
            [
                _event(done, EventType.CREATED, 10),
                _event(done, EventType.COMPLETED, 2),
                _event(doing, EventType.CREATED, 5),
                _event(doing, EventType.STARTED, 4),
            ]
        ),
    )

    forecast = await service.get_forecast(team_id=team_id, now=NOW)

    assert forecast.remaining == 2  # doing + eventless backlog
    assert forecast.window_end == NOW
    assert forecast.completion is not None
    assert forecast.completion.trials == 2_000
    assert forecast.confidence is None  # no target date given


async def test_steady_throughput_forecasts_exactly_and_scores_confidence() -> None:
    team_id = uuid4()
    service = _steady_service(team_id)

    # 1 completion/day over a 3-day window -> every trial finishes 5 items in 5 days.
    forecast = await service.get_forecast(
        team_id=team_id,
        window_days=3,
        remaining=5,
        target_date=date(2026, 7, 20),
        now=NOW,
    )

    assert forecast.remaining == 5
    assert forecast.completion is not None
    assert forecast.completion.p50_days == 5
    assert forecast.completion.p95_days == 5
    assert forecast.confidence == 1.0  # 10 days of runway for a 5-day job

    tight = await service.get_forecast(
        team_id=team_id,
        window_days=3,
        remaining=5,
        target_date=date(2026, 7, 12),
        now=NOW,
    )

    assert tight.confidence == 0.0  # 2 days of runway for a 5-day job


async def test_forecast_is_deterministic() -> None:
    team_id = uuid4()
    service = _steady_service(team_id)

    first = await service.get_forecast(team_id=team_id, now=NOW)
    second = await service.get_forecast(team_id=team_id, now=NOW)

    assert first == second


async def test_no_history_yields_no_forecast() -> None:
    team_id = uuid4()
    service = ForecastService(
        InMemoryWorkItemRepository([_item(team_id)]), InMemoryEventRepository([])
    )

    forecast = await service.get_forecast(team_id=team_id, now=NOW)

    assert forecast.remaining == 1
    assert forecast.completion is None
    assert forecast.confidence is None


async def test_precomputed_scope_skips_repository_loading() -> None:
    # Repositories are empty — remaining must come from the passed-in scope.
    service = ForecastService(
        InMemoryWorkItemRepository([]), InMemoryEventRepository([])
    )
    item = _item(uuid4())
    stream = [_event(item, EventType.COMPLETED, 1)]
    sample = derive_flow_sample(stream)
    assert sample is not None
    scope = ScopeSamples(streams=[stream], samples=[sample], item_count=3)

    forecast = await service.get_forecast(now=NOW, scope=scope)

    assert forecast.remaining == 2  # 3 in scope, 1 completed — all from `scope`


async def test_load_scope_applies_exclude_states() -> None:
    team_id = uuid4()
    keep, drop = _item(team_id), WorkItem(team_id=team_id, title="Trash", state="trash")
    service = ForecastService(
        InMemoryWorkItemRepository([keep, drop]), InMemoryEventRepository([])
    )

    scope = await service.load_scope(team_id=team_id, exclude_states={"trash"})

    assert scope.item_count == 1
