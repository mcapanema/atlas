import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import metric_rules_service_for, snapshot_service_for
from app.api.recompute import RecomputeRunner
from app.application.metric_rules.service import MetricRulesService, ScopeRef
from app.application.snapshots.service import SnapshotService
from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import RuleOverrides
from app.domain.organizations.entities import Organization
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.metric_rules import SqlAlchemyMetricRuleOverridesRepository
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.snapshots import SqlAlchemyMetricSnapshotRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
Sessions = async_sessionmaker[AsyncSession]


async def _seed(sessionmaker: Sessions) -> Team:
    """A team with one parked-then-restarted item, a snapshot, and a restart-clock override."""
    async with sessionmaker() as session:
        org = Organization(name="Acme")
        await SqlAlchemyOrganizationRepository(session).add(org)
        team = Team(organization_id=org.id, name="Platform")
        await SqlAlchemyTeamRepository(session).add(team)
        item = WorkItem(team_id=team.id, title="Parked then restarted")
        await SqlAlchemyWorkItemRepository(session).add(item)
        events = SqlAlchemyEventRepository(session)
        for type_, days in (
            (EventType.CREATED, 20),
            (EventType.STARTED, 18),
            (EventType.STOPPED, 15),
            (EventType.STARTED, 4),
            (EventType.COMPLETED, 2),
        ):
            await events.add(
                Event(work_item_id=item.id, type=type_, occurred_at=NOW - timedelta(days=days))
            )
        await snapshot_service_for(session).capture_all(now=NOW)
        await SqlAlchemyMetricRuleOverridesRepository(session).save(
            RuleOverrides(
                organization_id=org.id,
                team_id=team.id,
                overrides={"restart_clock_after_move_back": True},
            )
        )
        await session.commit()
    return team


async def _state(sessionmaker: Sessions, team: Team) -> tuple[float | None, RuleOverrides | None]:
    async with sessionmaker() as session:
        (snapshot,) = await SqlAlchemyMetricSnapshotRepository(session).list(team_id=team.id)
        row = await SqlAlchemyMetricRuleOverridesRepository(session).get(team.organization_id)
    return snapshot.cycle_time_p50_seconds, row


async def test_runner_rewrites_scopes_and_marks_the_organization_idle(
    file_sessionmaker: Sessions,
) -> None:
    team = await _seed(file_sessionmaker)
    runner = RecomputeRunner(file_sessionmaker)

    await runner.schedule(team.organization_id, [ScopeRef(team_id=team.id)])
    await runner.wait_idle()

    cycle_p50, row = await _state(file_sessionmaker, team)
    assert cycle_p50 == timedelta(days=2).total_seconds()
    assert row is not None
    assert row.recompute.state == "idle"
    assert row.recompute.finished_at is not None


async def test_runner_records_a_failure(
    file_sessionmaker: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    team = await _seed(file_sessionmaker)

    async def boom(self: SnapshotService, **_: object) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(SnapshotService, "recompute_scope", boom)
    runner = RecomputeRunner(file_sessionmaker)

    await runner.schedule(team.organization_id, [ScopeRef(team_id=team.id)])
    await runner.wait_idle()

    _, row = await _state(file_sessionmaker, team)
    assert row is not None
    assert (row.recompute.state, row.recompute.error) == ("failed", "boom")


async def test_a_new_schedule_restarts_the_run_with_every_pending_scope(
    file_sessionmaker: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    team = await _seed(file_sessionmaker)
    gate = asyncio.Event()
    mid_scope = asyncio.Event()
    finished: list[ScopeRef] = []

    async def slow(
        self: SnapshotService, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        mid_scope.set()
        await gate.wait()
        finished.append(ScopeRef(team_id=team_id, project_id=project_id))
        return 0

    monkeypatch.setattr(SnapshotService, "recompute_scope", slow)
    runner = RecomputeRunner(file_sessionmaker)
    first, second = ScopeRef(team_id=team.id), ScopeRef(project_id=uuid4())

    await runner.schedule(team.organization_id, [first])
    await mid_scope.wait()  # the first run is mid-scope
    await runner.schedule(team.organization_id, [second])
    gate.set()
    await runner.wait_idle()

    assert sorted(finished, key=str) == sorted([first, second], key=str)


async def test_a_cancelled_run_does_not_overwrite_the_new_runs_status(
    file_sessionmaker: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    team = await _seed(file_sessionmaker)
    async with file_sessionmaker() as session:
        await metric_rules_service_for(session).start_recompute(team.organization_id)
        await session.commit()
    gate = asyncio.Event()

    async def slow(self: SnapshotService, **_: object) -> int:
        await gate.wait()
        return 0

    monkeypatch.setattr(SnapshotService, "recompute_scope", slow)
    runner = RecomputeRunner(file_sessionmaker)

    await runner.schedule(team.organization_id, [ScopeRef(team_id=team.id)])
    await asyncio.sleep(0.05)  # the first run is parked at the gate
    await runner.schedule(team.organization_id, [ScopeRef(team_id=team.id)])
    await asyncio.sleep(0.05)  # the cancelled run is gone; the new one is parked

    _, row = await _state(file_sessionmaker, team)
    assert row is not None
    assert row.recompute.state == "running"
    gate.set()
    await runner.wait_idle()


async def test_resume_reruns_organizations_left_running(file_sessionmaker: Sessions) -> None:
    team = await _seed(file_sessionmaker)
    async with file_sessionmaker() as session:
        await metric_rules_service_for(session).start_recompute(team.organization_id)
        await session.commit()
    runner = RecomputeRunner(file_sessionmaker)

    await runner.resume()
    await runner.wait_idle()

    cycle_p50, row = await _state(file_sessionmaker, team)
    assert cycle_p50 == timedelta(days=2).total_seconds()
    assert row is not None
    assert row.recompute.state == "idle"


async def _running_org(sessionmaker: Sessions, name: str) -> UUID:
    async with sessionmaker() as session:
        org = Organization(name=name)
        await SqlAlchemyOrganizationRepository(session).add(org)
        await metric_rules_service_for(session).start_recompute(org.id)
        await session.commit()
    return org.id


async def _recompute_state(sessionmaker: Sessions, organization_id: UUID) -> str:
    async with sessionmaker() as session:
        view = await metric_rules_service_for(session).organization_view(organization_id)
    assert view is not None
    return view.recompute.state


async def test_a_run_cancelled_inside_finish_is_finished_by_the_restart(
    file_sessionmaker: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await _running_org(file_sessionmaker, "A")
    second = await _running_org(file_sessionmaker, "B")
    entered = asyncio.Event()
    original = MetricRulesService.finish_recompute
    calls = 0

    async def finish(self: MetricRulesService, organization_id: UUID, *, error: str | None) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()  # parked until the next schedule cancels it
        await original(self, organization_id, error=error)

    monkeypatch.setattr(MetricRulesService, "finish_recompute", finish)
    runner = RecomputeRunner(file_sessionmaker)

    await runner.schedule(first, [])
    await entered.wait()
    await runner.schedule(second, [])
    await runner.wait_idle()

    assert await _recompute_state(file_sessionmaker, first) == "idle"
    assert await _recompute_state(file_sessionmaker, second) == "idle"


async def test_a_paused_body_that_raises_still_restarts_the_pending_work(
    file_sessionmaker: Sessions,
) -> None:
    org = await _running_org(file_sessionmaker, "A")
    runner = RecomputeRunner(file_sessionmaker)

    async def invalid_save() -> None:
        async with runner.paused() as queue:
            queue(org, [])
            raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
        await invalid_save()
    await runner.wait_idle()

    assert await _recompute_state(file_sessionmaker, org) == "idle"


async def test_a_failing_finish_does_not_kill_the_run_for_later_organizations(
    file_sessionmaker: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = await _running_org(file_sessionmaker, "A")
    healthy = await _running_org(file_sessionmaker, "B")
    original = MetricRulesService.finish_recompute

    async def finish(self: MetricRulesService, organization_id: UUID, *, error: str | None) -> None:
        if organization_id == broken:
            raise RuntimeError("cannot record")
        await original(self, organization_id, error=error)

    monkeypatch.setattr(MetricRulesService, "finish_recompute", finish)
    runner = RecomputeRunner(file_sessionmaker)

    async with runner.paused() as queue:
        queue(broken, [])
        queue(healthy, [])
    await runner.wait_idle()

    assert await _recompute_state(file_sessionmaker, healthy) == "idle"
