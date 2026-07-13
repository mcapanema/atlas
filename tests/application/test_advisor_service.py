from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.application.advisor.service import AdvisorService
from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.domain.work_items.entities import WorkItem
from tests.fakes import InMemoryEventRepository, InMemoryWorkItemRepository


async def test_build_context_assembles_scope_metrics() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = InMemoryWorkItemRepository()
    events = InMemoryEventRepository()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    context = await service.build_context(team_id=uuid4(), window_days=7, now=now)

    # flow summary covers the requested window …
    assert context.flow.window_end == now
    assert context.flow.window_start == now - timedelta(days=7)
    # … while distribution and forecast keep their 90-day dashboard defaults
    assert context.distribution.window_start == now - timedelta(days=90)
    assert context.forecast.window_end == now
    assert context.forecast.remaining == 0


class CountingWorkItems(InMemoryWorkItemRepository):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        self.list_calls += 1
        return await super().list(
            team_id=team_id, project_id=project_id, limit=limit, offset=offset
        )


async def test_build_context_loads_the_scope_once() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = CountingWorkItems()
    events = InMemoryEventRepository()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    await service.build_context(team_id=uuid4(), now=now)

    # One shared load for flow + distribution + forecast (was three).
    assert work_items.list_calls == 1


async def test_build_meeting_context_assembles_the_full_picture() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = InMemoryWorkItemRepository()
    events = InMemoryEventRepository()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    context = await service.build_meeting_context(team_id=uuid4(), window_days=14, now=now)

    # flow + health honor the requested window; aging is an as-of-now view
    assert context.delivery.flow.window_start == now - timedelta(days=14)
    assert context.health.window_start == now - timedelta(days=14)
    assert context.aging.now == now
    assert context.aging.items == ()
    # distribution and forecast keep their 90-day dashboard defaults
    assert context.delivery.distribution.window_start == now - timedelta(days=90)
    assert context.delivery.forecast.window_end == now


async def test_build_meeting_context_forwards_planning_what_ifs() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = InMemoryWorkItemRepository()
    events = InMemoryEventRepository()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    context = await service.build_meeting_context(
        team_id=uuid4(), remaining=8, target_date=date(2026, 8, 1), now=now
    )

    assert context.delivery.forecast.remaining == 8  # the what-if, not the scope count


async def test_build_meeting_context_loads_the_scope_once() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = CountingWorkItems()
    events = InMemoryEventRepository()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    await service.build_meeting_context(team_id=uuid4(), now=now)

    # One shared load for flow + distribution + forecast + health + aging.
    assert work_items.list_calls == 1
