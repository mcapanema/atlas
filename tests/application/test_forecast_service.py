from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.application.forecasting.service import ForecastService
from app.application.scope import ScopeSamples
from app.domain.events.entities import Event, EventType
from app.domain.metrics.samples import derive_flow_sample
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
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        return [
            item
            for item in self._items
            if (team_id is None or item.team_id == team_id)
            and (project_id is None or item.project_id == project_id)
        ]

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
