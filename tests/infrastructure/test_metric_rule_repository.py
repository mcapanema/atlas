from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.metric_rules.entities import RecomputeStatus, RuleOverrides
from app.domain.teams.entities import Team
from app.infrastructure.repositories.metric_rules import SqlAlchemyMetricRuleOverridesRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository

ORG = uuid4()


async def test_workspace_row_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    started = datetime(2026, 10, 3, 12, tzinfo=UTC)
    row = RuleOverrides(
        organization_id=ORG,
        overrides={"aging_percentile": 80, "timezone": "America/Sao_Paulo"},
        recompute=RecomputeStatus(state="running", started_at=started),
    )

    await repo.save(row)
    loaded = await repo.get(ORG)

    assert loaded is not None
    assert loaded.overrides == {"aging_percentile": 80, "timezone": "America/Sao_Paulo"}
    assert loaded.recompute == RecomputeStatus(state="running", started_at=started)
    assert loaded.team_id is None


async def test_team_rows_are_distinct_from_the_workspace_row(session: AsyncSession) -> None:
    team = Team(organization_id=ORG, name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    await repo.save(RuleOverrides(organization_id=ORG, overrides={"healthy_min": 80}))
    await repo.save(
        RuleOverrides(organization_id=ORG, team_id=team.id, overrides={"warning_min": 50})
    )

    team_row = await repo.get(ORG, team_id=team.id)
    workspace_row = await repo.get(ORG)

    assert team_row is not None
    assert team_row.overrides == {"warning_min": 50}
    assert workspace_row is not None
    assert workspace_row.overrides == {"healthy_min": 80}
    assert len(await repo.list_for_organization(ORG)) == 2


async def test_save_replaces_the_row_with_the_same_id(session: AsyncSession) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    row = RuleOverrides(organization_id=ORG, overrides={"healthy_min": 80})
    await repo.save(row)

    await repo.save(RuleOverrides(organization_id=ORG, overrides={}, id=row.id))

    loaded = await repo.get(ORG)
    assert loaded is not None
    assert loaded.overrides == {}


async def test_list_recomputing_returns_running_workspace_rows(session: AsyncSession) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    running, idle = uuid4(), uuid4()
    await repo.save(
        RuleOverrides(organization_id=running, recompute=RecomputeStatus(state="running"))
    )
    await repo.save(RuleOverrides(organization_id=idle))

    assert [r.organization_id for r in await repo.list_recomputing()] == [running]


async def test_a_second_workspace_row_for_an_organization_is_rejected(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    await repo.save(RuleOverrides(organization_id=ORG))

    with pytest.raises(IntegrityError):
        await repo.save(RuleOverrides(organization_id=ORG))


async def test_save_never_clobbers_the_recompute_columns_of_an_existing_row(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    row = RuleOverrides(organization_id=ORG, recompute=RecomputeStatus(state="running"))
    await repo.save(row)

    await repo.save(RuleOverrides(organization_id=ORG, overrides={"healthy_min": 70}, id=row.id))

    loaded = await repo.get(ORG)
    assert loaded is not None
    assert loaded.overrides == {"healthy_min": 70}
    assert loaded.recompute.state == "running"


async def test_save_recompute_leaves_the_overrides_intact(session: AsyncSession) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)
    await repo.save(RuleOverrides(organization_id=ORG, overrides={"healthy_min": 80}))
    finished = datetime(2026, 10, 3, 13, tzinfo=UTC)

    await repo.save_recompute(ORG, RecomputeStatus(state="failed", finished_at=finished, error="x"))

    loaded = await repo.get(ORG)
    assert loaded is not None
    assert loaded.overrides == {"healthy_min": 80}
    assert loaded.recompute == RecomputeStatus(state="failed", finished_at=finished, error="x")


async def test_save_recompute_inserts_the_organization_row_when_missing(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyMetricRuleOverridesRepository(session)

    await repo.save_recompute(ORG, RecomputeStatus(state="running"))

    loaded = await repo.get(ORG)
    assert loaded is not None
    assert loaded.overrides == {}
    assert loaded.recompute.state == "running"
