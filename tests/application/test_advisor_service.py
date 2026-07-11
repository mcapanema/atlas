from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.advisor.service import AdvisorService
from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.domain.events.entities import Event
from app.domain.work_items.entities import WorkItem


class InMemoryWorkItems:
    """Structurally satisfies the full WorkItemRepository Protocol (mypy strict)."""

    async def add(self, work_item: WorkItem) -> None:
        raise NotImplementedError

    async def update(self, work_item: WorkItem) -> None:
        raise NotImplementedError

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        return []

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return None

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        return None


class InMemoryEvents:
    """Structurally satisfies the full EventRepository Protocol (mypy strict)."""

    async def add(self, event: Event) -> None:
        raise NotImplementedError

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return []

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        return []

    async def get_by_external_id(self, external_id: str) -> Event | None:
        return None


async def test_build_context_assembles_scope_metrics() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = InMemoryWorkItems()
    events = InMemoryEvents()
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


class CountingWorkItems(InMemoryWorkItems):
    def __init__(self) -> None:
        self.list_calls = 0

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        self.list_calls += 1
        return []


async def test_build_context_loads_the_scope_once() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    work_items = CountingWorkItems()
    events = InMemoryEvents()
    service = AdvisorService(
        MetricsService(work_items, events), ForecastService(work_items, events)
    )

    await service.build_context(team_id=uuid4(), now=now)

    # One shared load for flow + distribution + forecast (was three).
    assert work_items.list_calls == 1
