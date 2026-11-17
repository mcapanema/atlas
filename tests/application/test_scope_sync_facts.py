from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.scope import ScopeSampleLoader
from app.domain._time import utcnow
from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import RuleOverrides
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import Iteration, StateType, WorkItem, WorkItemType
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


def _iteration(name: str, starts_in_days: float, length_days: float = 14) -> Iteration:
    """An iteration starting `starts_in_days` from the wall clock (negative: already started)."""
    starts_at = utcnow() + timedelta(days=starts_in_days)
    return Iteration(
        external_id=name,
        name=name,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=length_days),
    )


def _todo(title: str, iteration: Iteration | None, team: Team = TEAM, **fields: object) -> WorkItem:
    return WorkItem(
        team_id=team.id,
        title=title,
        state_type=StateType.UNSTARTED,
        iteration=iteration,
        **fields,  # type: ignore[arg-type]
    )


async def test_current_iteration_rule_counts_the_current_iteration_and_unplanned_work() -> None:
    c_now, c_next = _iteration("Cycle 38", -3), _iteration("Cycle 39", 11)
    items = [_todo("Now", c_now), _todo("Next", c_next), _todo("Unplanned", None)]
    current, *_ = _loader(items, [], {"remaining_iterations": "current"})
    any_, *_ = _loader(items, [], {})

    narrowed = await current.load(team_id=TEAM.id)
    unchanged = await any_.load(team_id=TEAM.id)

    assert (narrowed.remaining_count, narrowed.iterations) == (2, ("Cycle 38",))
    assert (unchanged.remaining_count, unchanged.iterations) == (3, ())


async def test_current_iteration_rule_has_no_effect_without_iterations() -> None:
    items = [_todo(f"Item {n}", None) for n in range(3)]
    loader, *_ = _loader(items, [], {"remaining_iterations": "current"})

    scope = await loader.load(team_id=TEAM.id)

    assert scope.remaining_count == 3
    assert scope.iterations == ()


async def test_page_filters_do_not_move_the_current_iteration() -> None:
    c_now, c_next = _iteration("Cycle 38", -3), _iteration("Cycle 39", 11)
    bug = _todo("Crash", c_now, type=WorkItemType.BUG)
    task = _todo("Later", c_next)
    loader, *_ = _loader([bug, task], [], {"remaining_iterations": "current"})

    scope = await loader.load(team_id=TEAM.id, types={WorkItemType.TASK})

    assert scope.remaining_count == 0  # Cycle 38 stays current with its only item filtered out


async def test_each_item_uses_its_own_teams_current_iteration() -> None:
    a1 = _iteration("A1", -1)
    b1, b2 = _iteration("B1", -10, 13), _iteration("B2", 3)
    project = Project(team_id=TEAM.id, name="Shared")
    items = [
        _todo("Team now", a1, project_id=project.id),
        _todo("Other now", b1, team=OTHER, project_id=project.id),
        _todo("Other next", b2, team=OTHER, project_id=project.id),
    ]
    resolver = MetricRulesResolver(
        InMemoryMetricRuleOverridesRepository(
            [RuleOverrides(organization_id=ORG, overrides={"remaining_iterations": "current"})]
        ),
        InMemoryTeamRepository([TEAM, OTHER]),
        InMemoryProjectRepository([project]),
    )
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository(items), InMemoryEventRepository(), resolver
    )

    scope = await loader.load(project_id=project.id)

    assert scope.remaining_count == 2
    assert scope.iterations == ("A1", "B1")


async def test_an_as_of_load_uses_the_iteration_current_then() -> None:
    start = NOW - timedelta(days=28)
    c1 = Iteration(external_id="c1", name="Cycle 1", starts_at=start, ends_at=start + timedelta(14))
    c2 = Iteration(
        external_id="c2",
        name="Cycle 2",
        starts_at=start + timedelta(14),
        ends_at=start + timedelta(28),
    )
    first, second = _todo("First", c1), _todo("Second", c2)
    events = [_at(first, EventType.CREATED, 30), _at(second, EventType.CREATED, 30)]
    loader, *_ = _loader([first, second], events, {"remaining_iterations": "current"})

    data = await loader.load_data(team_id=TEAM.id)
    in_c1 = data.samples(as_of=start + timedelta(days=1))
    in_c2 = data.samples(as_of=start + timedelta(days=15))

    assert (in_c1.remaining_count, in_c1.iterations) == (1, ("Cycle 1",))
    assert (in_c2.remaining_count, in_c2.iterations) == (1, ("Cycle 2",))


async def test_iteration_rule_never_widens_the_state_type_rule() -> None:
    c_now = _iteration("Cycle 38", -3)
    backlog = WorkItem(
        team_id=TEAM.id, title="Parked", state_type=StateType.BACKLOG, iteration=c_now
    )
    loader, *_ = _loader(
        [backlog],
        [],
        {"remaining_state_types": ["unstarted", "started"], "remaining_iterations": "current"},
    )

    scope = await loader.load(team_id=TEAM.id)

    assert scope.remaining_count == 0


async def test_a_team_with_only_past_iterations_keeps_all_its_open_work() -> None:
    past = _iteration("Cycle 12", -40)
    items = [_todo("Rolled over", past), _todo("Unplanned", None)]
    loader, *_ = _loader(items, [], {"remaining_iterations": "current"})

    scope = await loader.load(team_id=TEAM.id)

    assert scope.remaining_count == 2
    assert scope.iterations == ()
