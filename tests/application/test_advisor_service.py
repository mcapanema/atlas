from datetime import UTC, datetime, timedelta
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
