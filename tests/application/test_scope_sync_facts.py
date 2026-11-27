from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.scope import ScopeSampleLoader, ScopeSamples
from app.domain._time import utcnow
from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import RuleOverrides
from app.domain.metrics.cfd import daily_flow_counts
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


class _CountingWorkItems(InMemoryWorkItemRepository):
    iteration_queries = 0

    async def iterations_by_team(self, team_ids: Collection[UUID]) -> dict[UUID, list[Iteration]]:
        self.iteration_queries += 1
        return await super().iterations_by_team(team_ids)


async def test_iterations_are_queried_only_under_the_current_iteration_rule() -> None:
    items = [_todo("Now", _iteration("Cycle 38", -3))]
    cases: list[tuple[dict[str, object], int]] = [({}, 0), ({"remaining_iterations": "current"}, 1)]
    for overrides, queries in cases:
        _, _, event_repo, resolver = _loader(items, [], overrides)
        counting = _CountingWorkItems(items)
        await ScopeSampleLoader(counting, event_repo, resolver).load(team_id=TEAM.id)
        assert counting.iteration_queries == queries


TOP_LEVEL_ONLY: dict[str, object] = {"count_sub_issues": False}


def _story_tree() -> tuple[WorkItem, WorkItem, WorkItem]:
    story = WorkItem(team_id=TEAM.id, title="Story")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    sub_task = WorkItem(team_id=TEAM.id, title="Sub-task", parent_id=task.id)
    return story, task, sub_task


async def test_top_level_only_drops_sub_issues_from_every_count() -> None:
    items = list(_story_tree())
    events = [_at(i, EventType.CREATED, 9) for i in items]
    loader, *_ = _loader(items, events, TOP_LEVEL_ONLY)

    scope = await loader.load(team_id=TEAM.id)

    assert scope.item_count == 1
    assert scope.remaining_count == 1
    assert [i.title for i, _ in scope.items_with_samples] == ["Story"]


async def test_defaults_still_count_every_level() -> None:
    items = list(_story_tree())
    events = [_at(i, EventType.CREATED, 9) for i in items]
    loader, *_ = _loader(items, events, {})

    assert (await loader.load(team_id=TEAM.id)).item_count == 3


async def test_sub_issue_with_parent_outside_the_scope_still_counts() -> None:
    story = WorkItem(team_id=OTHER.id, title="Story")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    events = [_at(i, EventType.CREATED, 9) for i in (story, task)]
    loader, *_ = _loader([story, task], events, TOP_LEVEL_ONLY)

    assert (await loader.load(team_id=TEAM.id)).item_count == 1


def _story_with_started_task() -> tuple[list[WorkItem], list[Event]]:
    story, task, sub_task = _story_tree()
    events = [
        *(_at(i, EventType.CREATED, 9) for i in (story, task, sub_task)),
        _at(sub_task, EventType.STARTED, 4),
        _at(task, EventType.STARTED, 3),
    ]
    return [story, task, sub_task], events


async def test_parent_starts_with_its_earliest_descendant() -> None:
    items, events = _story_with_started_task()
    loader, *_ = _loader(items, events, TOP_LEVEL_ONLY)

    scope = await loader.load(team_id=TEAM.id)

    ((_, sample),) = scope.items_with_samples
    assert sample.started_at == NOW - timedelta(days=4)


async def test_parent_keeps_its_own_start_by_default() -> None:
    items, events = _story_with_started_task()
    loader, *_ = _loader(items, events, {})

    scope = await loader.load(team_id=TEAM.id)

    story_sample = next(s for i, s in scope.items_with_samples if i.title == "Story")
    assert story_sample.started_at is None


async def test_roll_up_ignores_descendant_starts_after_as_of() -> None:
    items, events = _story_with_started_task()
    loader, *_ = _loader(items, events, TOP_LEVEL_ONLY)

    data = await loader.load_data(team_id=TEAM.id)

    before = data.samples(as_of=NOW - timedelta(days=6)).samples[0]
    after = data.samples(as_of=NOW - timedelta(days=4)).samples[0]
    assert before.started_at is None
    assert after.started_at == NOW - timedelta(days=4)


async def test_open_sub_issues_of_a_done_story_are_not_remaining() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story", state_type=StateType.COMPLETED)
    tasks = [
        WorkItem(
            team_id=TEAM.id, title=f"Task {n}", parent_id=story.id, state_type=StateType.UNSTARTED
        )
        for n in (1, 2)
    ]
    events = [
        *(_at(i, EventType.CREATED, 9) for i in (story, *tasks)),
        _at(story, EventType.COMPLETED, 2),
    ]
    loader, *_ = _loader([story, *tasks], events, TOP_LEVEL_ONLY)

    scope = await loader.load(team_id=TEAM.id)

    assert scope.remaining_count == 0
    assert scope.samples[0].completed_at == NOW - timedelta(days=2)


async def test_type_filter_keeps_dropping_sub_issues() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story")
    bug = WorkItem(team_id=TEAM.id, title="Crash", labels=("Bug",), parent_id=story.id)
    events = [_at(i, EventType.CREATED, 9) for i in (story, bug)]
    rules = {**TOP_LEVEL_ONLY, "type_labels": [{"label": "bug", "type": "bug"}]}
    loader, *_ = _loader([story, bug], events, rules)

    scope = await loader.load(team_id=TEAM.id, types={WorkItemType.BUG})

    assert scope.item_count == 0


async def _story_start(sub_task_events: list[tuple[EventType, int]]) -> datetime | None:
    """The story's started_at under top-level only, given its one sub-task's events."""
    story = WorkItem(team_id=TEAM.id, title="Story")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    events = [_at(story, EventType.CREATED, 30), _at(task, EventType.CREATED, 30)]
    events += [_at(task, type_, days_ago) for type_, days_ago in sub_task_events]
    loader, *_ = _loader([story, task], events, TOP_LEVEL_ONLY)
    ((_, sample),) = (await loader.load(team_id=TEAM.id)).items_with_samples
    return sample.started_at


async def test_a_canceled_sub_issue_does_not_start_its_story() -> None:
    assert await _story_start([(EventType.STARTED, 29), (EventType.CANCELED, 28)]) is None


async def test_a_moved_back_sub_issue_does_not_start_its_story() -> None:
    assert await _story_start([(EventType.STARTED, 29), (EventType.STOPPED, 28)]) is None


async def test_a_restarted_sub_issue_still_starts_its_story() -> None:
    events = [(EventType.STARTED, 29), (EventType.STOPPED, 28), (EventType.STARTED, 3)]
    assert await _story_start(events) == NOW - timedelta(days=29)


async def test_type_filter_keeps_the_roll_up() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story", labels=("Story",))
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    events = [
        *(_at(i, EventType.CREATED, 9) for i in (story, task)),
        _at(task, EventType.STARTED, 4),
    ]
    rules = {**TOP_LEVEL_ONLY, "type_labels": [{"label": "story", "type": "story"}]}
    loader, *_ = _loader([story, task], events, rules)

    scope = await loader.load(team_id=TEAM.id, types={WorkItemType.STORY})
    data = (await loader.load_data(team_id=TEAM.id)).filtered(types={WorkItemType.STORY})

    assert scope.samples[0].started_at == NOW - timedelta(days=4)
    assert data.samples().samples[0].started_at == NOW - timedelta(days=4)


async def test_cfd_shows_a_rolled_up_story_in_progress() -> None:
    items, events = _story_with_started_task()
    loader, *_ = _loader(items, events, TOP_LEVEL_ONLY)

    scope = await loader.load(team_id=TEAM.id)
    counts = daily_flow_counts(
        scope.streams, start=NOW - timedelta(days=1), end=NOW, stream_rules=scope.stream_rules
    )

    assert counts[-1].in_progress == 1
    assert counts[-1].todo == 0


def _moved(item: WorkItem, days_ago: int, parent: str | None) -> Event:
    return _at(item, EventType.PARENT_CHANGED, days_ago, detail=parent)


def _titles(scope: ScopeSamples) -> list[str]:
    return sorted(item.title for item, _ in scope.items_with_samples)


async def test_replay_before_the_move_counts_the_sub_issue() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story", external_id="S")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    events = [
        _at(task, EventType.CREATED, 20),
        _at(task, EventType.STARTED, 18),
        _at(task, EventType.COMPLETED, 15),
        _at(story, EventType.CREATED, 10),
        _moved(task, 10, "S"),
    ]
    loader, *_ = _loader([story, task], events, TOP_LEVEL_ONLY)

    data = await loader.load_data(team_id=TEAM.id)

    assert _titles(data.samples(as_of=NOW - timedelta(days=12))) == ["Task"]
    assert _titles(data.samples()) == ["Story"]


async def test_moved_sub_issue_rolls_up_into_its_parent_of_the_day() -> None:
    a = WorkItem(team_id=TEAM.id, title="A", external_id="A")
    b = WorkItem(team_id=TEAM.id, title="B", external_id="B")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=b.id)
    events = [
        _at(a, EventType.CREATED, 20),
        _at(b, EventType.CREATED, 20),
        _at(task, EventType.CREATED, 20),
        _moved(task, 20, "A"),
        _at(task, EventType.STARTED, 15),
        _moved(task, 5, "B"),
    ]
    loader, *_ = _loader([a, b, task], events, TOP_LEVEL_ONLY)
    data = await loader.load_data(team_id=TEAM.id)

    def starts(scope: ScopeSamples) -> dict[str, datetime | None]:
        return {item.title: sample.started_at for item, sample in scope.items_with_samples}

    then = starts(data.samples(as_of=NOW - timedelta(days=10)))
    now = starts(data.samples())
    assert then == {"A": NOW - timedelta(days=15), "B": None}
    assert now == {"A": None, "B": NOW - timedelta(days=15)}


async def test_a_parent_that_did_not_exist_yet_links_nothing() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story", external_id="S")
    task = WorkItem(team_id=TEAM.id, title="Task", parent_id=story.id)
    events = [
        _at(task, EventType.CREATED, 20),
        _at(task, EventType.COMPLETED, 15),
        _at(story, EventType.CREATED, 10),
    ]
    loader, *_ = _loader([story, task], events, TOP_LEVEL_ONLY)

    data = await loader.load_data(team_id=TEAM.id)

    assert data.samples(as_of=NOW - timedelta(days=12)).item_count == 1
    assert _titles(data.samples()) == ["Story"]


async def test_removed_parent_counts_the_issue_again() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story", external_id="S")
    task = WorkItem(team_id=TEAM.id, title="Task")
    events = [
        _at(story, EventType.CREATED, 20),
        _at(task, EventType.CREATED, 20),
        _moved(task, 10, "S"),
        _moved(task, 5, None),
    ]
    loader, *_ = _loader([story, task], events, TOP_LEVEL_ONLY)

    data = await loader.load_data(team_id=TEAM.id)

    assert _titles(data.samples(as_of=NOW - timedelta(days=12))) == ["Story", "Task"]
    assert _titles(data.samples(as_of=NOW - timedelta(days=7))) == ["Story"]
    assert _titles(data.samples()) == ["Story", "Task"]


class _RecordingEvents(InMemoryEventRepository):
    def __init__(self, events: list[Event]) -> None:
        super().__init__(events)
        self.requested: list[set[UUID]] = []

    async def list_for_work_items(
        self, work_item_ids: list[UUID], types: Collection[EventType] | None = None
    ) -> list[Event]:
        self.requested.append(set(work_item_ids))
        return await super().list_for_work_items(work_item_ids, types)


async def test_default_rules_load_only_the_filtered_items_events() -> None:
    story = WorkItem(team_id=TEAM.id, title="Story")
    bug = WorkItem(team_id=TEAM.id, title="Crash", labels=("Bug",), parent_id=story.id)
    events = [_at(i, EventType.CREATED, 9) for i in (story, bug)]
    rules: dict[str, object] = {"type_labels": [{"label": "bug", "type": "bug"}]}
    _, work_items, _, resolver = _loader([story, bug], events, rules)
    recording = _RecordingEvents(events)

    await ScopeSampleLoader(work_items, recording, resolver).load(
        team_id=TEAM.id, types={WorkItemType.TASK}
    )

    assert recording.requested == [{story.id}]


PARENTS_LEAVE: dict[str, object] = {"count_parent_issues": False}


def _story_and_late_child(
    child_events: list[tuple[int, str | None]],
) -> tuple[list[WorkItem], list[Event]]:
    """Story S (TEAM, 20 days old) and a child in OTHER created 8 days ago."""
    story = WorkItem(team_id=TEAM.id, title="Story", external_id="S")
    child = WorkItem(
        team_id=OTHER.id,
        title="Task",
        parent_id=story.id,
        created_at=NOW - timedelta(days=8),
    )
    events = [_at(story, EventType.CREATED, 20), _at(child, EventType.CREATED, 8)]
    events += [_moved(child, days_ago, parent) for days_ago, parent in child_events]
    return [story, child], events


async def test_parent_counts_until_its_first_child_arrives() -> None:
    items, events = _story_and_late_child([(8, "S")])
    loader, *_ = _loader(items, events, PARENTS_LEAVE)

    data = await loader.load_data(team_id=TEAM.id)

    assert data.samples(as_of=NOW - timedelta(days=10)).item_count == 1
    assert data.samples().item_count == 0


async def test_parent_counts_again_after_its_last_child_leaves() -> None:
    items, events = _story_and_late_child([(8, "S"), (3, None)])
    items[1] = replace(items[1], parent_id=None)
    loader, *_ = _loader(items, events, PARENTS_LEAVE)

    data = await loader.load_data(team_id=TEAM.id)

    assert data.samples(as_of=NOW - timedelta(days=5)).item_count == 0
    assert data.samples().item_count == 1


async def test_parent_rule_falls_back_to_current_links_for_old_syncs() -> None:
    items, events = _story_and_late_child([])
    loader, *_ = _loader(items, events, PARENTS_LEAVE)

    data = await loader.load_data(team_id=TEAM.id)

    assert data.samples(as_of=NOW - timedelta(days=10)).item_count == 1
    assert data.samples().item_count == 0
