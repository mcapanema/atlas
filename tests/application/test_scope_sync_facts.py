from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.scope import ScopeSampleLoader
from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import RuleOverrides
from app.domain.teams.entities import Team
from app.domain.work_items.entities import StateType, WorkItem, WorkItemType
from tests.fakes import (
    InMemoryEventRepository,
    InMemoryMetricRuleOverridesRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)
ORG = uuid4()
TEAM = Team(organization_id=ORG, name="Platform")
OTHER = Team(organization_id=ORG, name="Data")


def _at(item: WorkItem, type_: EventType, days_ago: int, **fields: object) -> Event:
    return Event(
        work_item_id=item.id,
        type=type_,
        occurred_at=NOW - timedelta(days=days_ago),
        **fields,  # type: ignore[arg-type]
    )


def _loader(
    items: list[WorkItem], events: list[Event], team_overrides: dict[str, object]
) -> tuple[
    ScopeSampleLoader, InMemoryWorkItemRepository, InMemoryEventRepository, MetricRulesResolver
]:
    work_items = InMemoryWorkItemRepository(items)
    event_repo = InMemoryEventRepository(events)
    resolver = MetricRulesResolver(
        InMemoryMetricRuleOverridesRepository(
            [RuleOverrides(organization_id=ORG, team_id=TEAM.id, overrides=team_overrides)]
        ),
        InMemoryTeamRepository([TEAM, OTHER]),
        InMemoryProjectRepository(),
    )
    return ScopeSampleLoader(work_items, event_repo, resolver), work_items, event_repo, resolver


async def test_parents_leave_the_scope_by_their_teams_rule_even_with_children_elsewhere() -> None:
    parent = WorkItem(team_id=TEAM.id, title="Epic")
    child = WorkItem(team_id=OTHER.id, title="Sub-task", parent_id=parent.id)
    events = [_at(parent, EventType.CREATED, 9), _at(child, EventType.CREATED, 9)]

    counted, *_ = _loader([parent, child], events, {})
    excluded, *_ = _loader([parent, child], events, {"count_parent_issues": False})

    assert (await counted.load(team_id=TEAM.id)).item_count == 1
    assert (await excluded.load(team_id=TEAM.id)).item_count == 0
    assert (await excluded.load(team_id=OTHER.id)).item_count == 1  # the leaf still counts


async def test_type_filter_matches_the_effective_type() -> None:
    bug = WorkItem(team_id=TEAM.id, title="Crash", labels=("Bug",))
    chore = WorkItem(team_id=TEAM.id, title="Chore")
    events = [_at(bug, EventType.CREATED, 3), _at(chore, EventType.CREATED, 3)]
    loader, *_ = _loader([bug, chore], events, {"type_labels": [{"label": "bug", "type": "bug"}]})

    scope = await loader.load(team_id=TEAM.id, types={WorkItemType.BUG})

    assert [item.title for item, _ in scope.items_with_samples] == ["Crash"]


async def test_remaining_count_at_defaults_equals_open_items() -> None:
    done = WorkItem(team_id=TEAM.id, title="Done", state_type=StateType.COMPLETED)
    canceled = WorkItem(team_id=TEAM.id, title="Dropped", state_type=StateType.CANCELED)
    backlog = WorkItem(team_id=TEAM.id, title="Later", state_type=StateType.BACKLOG)
    eventless = WorkItem(team_id=TEAM.id, title="Manual")
    events = [
        _at(done, EventType.CREATED, 9),
        _at(done, EventType.COMPLETED, 2),
        _at(canceled, EventType.CREATED, 9),
        _at(canceled, EventType.CANCELED, 2),
        _at(backlog, EventType.CREATED, 9),
    ]
    loader, *_ = _loader([done, canceled, backlog, eventless], events, {})

    scope = await loader.load(team_id=TEAM.id)

    closed = sum(1 for s in scope.samples if s.completed_at is not None or s.canceled)
    assert scope.remaining_count == scope.item_count - closed == 2


async def test_remaining_state_types_filter_open_items_and_unknown_types_count() -> None:
    backlog = WorkItem(team_id=TEAM.id, title="Later", state_type=StateType.BACKLOG)
    todo = WorkItem(team_id=TEAM.id, title="Next", state_type=StateType.UNSTARTED)
    manual = WorkItem(team_id=TEAM.id, title="Manual")
    events = [_at(i, EventType.CREATED, 5) for i in (backlog, todo, manual)]
    loader, *_ = _loader(
        [backlog, todo, manual], events, {"remaining_state_types": ["unstarted", "started"]}
    )

    scope = await loader.load(team_id=TEAM.id)

    assert scope.remaining_count == 2  # Todo + the untyped manual item


async def test_an_as_of_load_uses_the_state_type_as_it_was() -> None:
    item = WorkItem(team_id=TEAM.id, title="Picked up", state_type=StateType.STARTED)
    events = [
        _at(item, EventType.CREATED, 20),
        _at(
            item,
            EventType.STARTED,
            5,
            from_state_type=StateType.BACKLOG,
            to_state_type=StateType.STARTED,
        ),
    ]
    loader, *_ = _loader([item], events, {"remaining_state_types": ["unstarted", "started"]})

    data = await loader.load_data(team_id=TEAM.id)

    assert data.samples(as_of=NOW - timedelta(days=10)).remaining_count == 0  # in Backlog then
    assert data.samples().remaining_count == 1


async def test_forecast_remaining_follows_the_rule() -> None:
    backlog = WorkItem(team_id=TEAM.id, title="Later", state_type=StateType.BACKLOG)
    todo = WorkItem(team_id=TEAM.id, title="Next", state_type=StateType.UNSTARTED)
    events = [_at(i, EventType.CREATED, 5) for i in (backlog, todo)]
    _, work_items, event_repo, resolver = _loader(
        [backlog, todo], events, {"remaining_state_types": ["unstarted"]}
    )

    forecast = await ForecastService(work_items, event_repo, resolver).get_forecast(
        team_id=TEAM.id, now=NOW
    )

    assert forecast.remaining == 1
