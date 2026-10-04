import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import metric_rules_service_for, snapshot_service_for
from app.api.recompute import RecomputeRunner
from app.application.metric_rules.service import ScopeRef
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
    finished: list[ScopeRef] = []

    async def slow(
        self: SnapshotService, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        await gate.wait()
        finished.append(ScopeRef(team_id=team_id, project_id=project_id))
        return 0

    monkeypatch.setattr(SnapshotService, "recompute_scope", slow)
    runner = RecomputeRunner(file_sessionmaker)
    first, second = ScopeRef(team_id=team.id), ScopeRef(project_id=uuid4())

    await runner.schedule(team.organization_id, [first])
    await asyncio.sleep(0)  # let the first run reach the gate
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
