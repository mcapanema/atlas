import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.forecasting.service import ForecastService
from app.application.metric_rules.resolver import MetricRulesResolver
from app.application.metrics.service import MetricsService
from app.application.scope import ScopeSampleLoader
from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import DEFAULT_RULES, RuleOverrides
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryEventRepository,
    InMemoryMetricRuleOverridesRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)
ORG = uuid4()


def _at(item: WorkItem, type_: EventType, days_ago: int) -> Event:
    return Event(work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days_ago))


def _parked(item: WorkItem) -> list[Event]:
    return [
        _at(item, EventType.CREATED, 20),
        _at(item, EventType.STARTED, 18),
        _at(item, EventType.STOPPED, 15),
        _at(item, EventType.STARTED, 4),
    ]


def _resolver(
    teams: Sequence[Team],
    projects: Sequence[Project] = (),
    rows: Sequence[RuleOverrides] = (),
) -> MetricRulesResolver:
    return MetricRulesResolver(
        InMemoryMetricRuleOverridesRepository(list(rows)),
        InMemoryTeamRepository(list(teams)),
        InMemoryProjectRepository(list(projects)),
    )


async def test_items_fold_with_their_own_teams_rules() -> None:
    restarts = Team(organization_id=ORG, name="Restarts")
    steady = Team(organization_id=ORG, name="Steady")
    project = Project(team_id=steady.id, name="Shared")
    mine = WorkItem(team_id=restarts.id, title="Mine", project_id=project.id)
    theirs = WorkItem(team_id=steady.id, title="Theirs", project_id=project.id)
    rows = [
        RuleOverrides(
            organization_id=ORG,
            team_id=restarts.id,
            overrides={"restart_clock_after_move_back": True},
        )
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([mine, theirs]),
        InMemoryEventRepository(_parked(mine) + _parked(theirs)),
        _resolver([restarts, steady], [project], rows),
    )

    scope = await loader.load(project_id=project.id)

    started = {item.title: sample.started_at for item, sample in scope.items_with_samples}
    assert started == {"Mine": NOW - timedelta(days=4), "Theirs": NOW - timedelta(days=18)}
    assert scope.rules == DEFAULT_RULES  # the project's team (Steady) has no overrides


async def test_scope_rules_come_from_the_projects_team() -> None:
    owner = Team(organization_id=ORG, name="Owner")
    other = Team(organization_id=ORG, name="Other")
    project = Project(team_id=owner.id, name="Owned")
    item = WorkItem(team_id=other.id, title="Borrowed", project_id=project.id)
    rows = [
        RuleOverrides(
            organization_id=ORG, team_id=owner.id, overrides={"forecast_history_days": 30}
        )
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([item]),
        InMemoryEventRepository([_at(item, EventType.CREATED, 3)]),
        _resolver([owner, other], [project], rows),
    )

    scope = await loader.load(project_id=project.id)

    assert scope.rules.forecast_history_days == 30


async def test_workspace_default_applies_to_teams_without_overrides() -> None:
    team = Team(organization_id=ORG, name="Plain")
    rows = [RuleOverrides(organization_id=ORG, overrides={"aging_percentile": 70})]

    rules = await _resolver([team], rows=rows).team_rules(team.id)

    assert rules.aging_percentile == 70


async def test_invalid_stored_rules_fall_back_to_built_in() -> None:
    team = Team(organization_id=ORG, name="Broken")
    rows = [RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"healthy_min": 0})]

    assert await _resolver([team], rows=rows).team_rules(team.id) == DEFAULT_RULES


async def test_born_done_items_count_when_the_team_includes_them() -> None:
    team = Team(organization_id=ORG, name="Records")
    item = WorkItem(team_id=team.id, title="Logged done")
    rows = [
        RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"exclude_born_done": False})
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([item]),
        InMemoryEventRepository(
            [_at(item, EventType.CREATED, 5), _at(item, EventType.COMPLETED, 5)]
        ),
        _resolver([team], rows=rows),
    )

    scope = await loader.load(team_id=team.id)

    assert scope.item_count == 1
    assert len(scope.samples) == 1


async def test_as_of_replays_the_scope_at_a_past_instant() -> None:
    team = Team(organization_id=ORG, name="Replay")
    done_later = WorkItem(team_id=team.id, title="Done later")
    created_later = WorkItem(team_id=team.id, title="Created later")
    old_backlog = WorkItem(team_id=team.id, title="Old", created_at=NOW - timedelta(days=30))
    new_backlog = WorkItem(team_id=team.id, title="New", created_at=NOW - timedelta(days=1))
    events = [
        _at(done_later, EventType.CREATED, 20),
        _at(done_later, EventType.STARTED, 15),
        _at(done_later, EventType.COMPLETED, 2),
        _at(created_later, EventType.CREATED, 3),
    ]
    loader = ScopeSampleLoader(
        InMemoryWorkItemRepository([done_later, created_later, old_backlog, new_backlog]),
        InMemoryEventRepository(events),
    )

    data = await loader.load_data(team_id=team.id)
    past = data.samples(as_of=NOW - timedelta(days=10))

    assert past.item_count == 2  # done_later + the old eventless item
    (sample,) = past.samples
    assert sample.completed_at is None
    assert sample.started_at == NOW - timedelta(days=15)
    assert data.samples().item_count == 4


async def test_forecast_history_window_defaults_to_the_teams_rule() -> None:
    team = Team(organization_id=ORG, name="Short history")
    item = WorkItem(team_id=team.id, title="Old")
    events = [
        _at(item, EventType.CREATED, 200),
        _at(item, EventType.STARTED, 100),
        _at(item, EventType.COMPLETED, 10),
    ]
    rows = [
        RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"forecast_history_days": 30})
    ]
    service = ForecastService(
        InMemoryWorkItemRepository([item]),
        InMemoryEventRepository(events),
        _resolver([team], rows=rows),
    )

    forecast = await service.get_forecast(team_id=team.id, now=NOW)

    assert forecast.window_end - forecast.window_start == timedelta(days=30)


async def test_aging_wip_uses_the_teams_aging_percentile() -> None:
    team = Team(organization_id=ORG, name="Strict")
    rows = [RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"aging_percentile": 50})]
    service = MetricsService(
        InMemoryWorkItemRepository([]), InMemoryEventRepository([]), _resolver([team], rows=rows)
    )

    aging = await service.get_aging_wip(team_id=team.id, now=NOW)

    assert aging.percentile == 50


async def test_as_of_replay_ignores_a_reopen_after_the_instant() -> None:
    team = Team(organization_id=ORG, name="Reopens")
    item = WorkItem(team_id=team.id, title="Reopened")
    events = [
        _at(item, EventType.CREATED, 20),
        _at(item, EventType.STARTED, 15),
        _at(item, EventType.COMPLETED, 8),
        _at(item, EventType.STARTED, 2),  # reopened after the as-of instant
    ]
    loader = ScopeSampleLoader(InMemoryWorkItemRepository([item]), InMemoryEventRepository(events))

    data = await loader.load_data(team_id=team.id)

    (sample,) = data.samples(as_of=NOW - timedelta(days=5)).samples
    assert sample.completed_at == NOW - timedelta(days=8)
    (now_sample,) = data.samples().samples
    assert now_sample.completed_at is None


class _CountingOverrides(InMemoryMetricRuleOverridesRepository):
    def __init__(self, rows: list[RuleOverrides]) -> None:
        super().__init__(rows)
        self.org_reads = 0

    async def get(
        self, organization_id: UUID, *, team_id: UUID | None = None
    ) -> RuleOverrides | None:
        if team_id is None:
            self.org_reads += 1
        return await super().get(organization_id, team_id=team_id)


async def test_resolve_reads_the_org_row_once_and_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = Team(organization_id=ORG, name="First")
    second = Team(organization_id=ORG, name="Second")
    overrides = _CountingOverrides(
        [RuleOverrides(organization_id=ORG, overrides={"renamed_rule": 1})]
    )
    resolver = MetricRulesResolver(
        overrides, InMemoryTeamRepository([first, second]), InMemoryProjectRepository([])
    )

    with caplog.at_level(logging.WARNING):
        await resolver.resolve(team_id=first.id, project_id=None, item_team_ids=[second.id])

    assert overrides.org_reads == 1
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


class _FreshRows(InMemoryMetricRuleOverridesRepository):
    """Hands out a new RuleOverrides (and overrides dict) on every read."""

    async def get(
        self, organization_id: UUID, *, team_id: UUID | None = None
    ) -> RuleOverrides | None:
        row = await super().get(organization_id, team_id=team_id)
        if row is None:
            return None
        return RuleOverrides(
            organization_id=row.organization_id,
            team_id=row.team_id,
            overrides=dict(row.overrides),
        )


async def test_each_teams_unknown_rule_warns_even_when_layers_are_freed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = Team(organization_id=ORG, name="First")
    second = Team(organization_id=ORG, name="Second")
    rows = [
        RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"typo": 1})
        for team in (first, second)
    ]
    resolver = MetricRulesResolver(
        _FreshRows(rows), InMemoryTeamRepository([first, second]), InMemoryProjectRepository([])
    )

    with caplog.at_level(logging.WARNING):
        await resolver.resolve(team_id=first.id, project_id=None, item_team_ids=[second.id])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
