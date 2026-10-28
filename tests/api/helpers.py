"""Shared builders for API-level tests: create real parent chains via the API."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.metric_rules.entities import RuleOverrides
from app.infrastructure.repositories.metric_rules import SqlAlchemyMetricRuleOverridesRepository


async def create_org_and_team(
    client: AsyncClient, *, external_id: str | None = None
) -> tuple[str, str]:
    org = await client.post("/api/organizations", json={"name": "Acme"})
    assert org.status_code in (200, 201)
    org_id: str = org.json()["id"]
    team = await client.post(
        "/api/teams",
        json={"organization_id": org_id, "name": "Platform", "external_id": external_id},
    )
    assert team.status_code in (200, 201)
    team_id: str = team.json()["id"]
    return org_id, team_id


async def create_team(client: AsyncClient) -> str:
    return (await create_org_and_team(client))[1]


async def use_calendar_days(
    sessionmaker: async_sessionmaker[AsyncSession], organization_id: str
) -> None:
    """Make the organization's durations plain calendar time (all seven days work).

    For tests that seed events relative to the wall clock and assert exact
    durations: the default Monday-Friday calendar would make them depend on
    the weekday the suite runs on.

    Writes through the repository, not the rules endpoint: a PATCH starts the
    recompute runner, which the `client` fixture's single in-memory connection
    can't host (see `file_sessionmaker`). Call it before seeding events, so
    there is no history the skipped recompute would have rebuilt.
    """
    async with sessionmaker() as session:
        await SqlAlchemyMetricRuleOverridesRepository(session).save(
            RuleOverrides(
                organization_id=UUID(organization_id),
                overrides={"working_days": [1, 2, 3, 4, 5, 6, 7]},
            )
        )
        await session.commit()


async def settle(app: FastAPI) -> None:
    """Wait for the advice and sync job runners, then the recompute runner, to go idle."""
    advice = getattr(app.state, "advice_runner", None)
    if advice is not None:
        await advice.wait_idle()
    jobs = getattr(app.state, "sync_job_runner", None)
    if jobs is not None:
        await jobs.wait_idle()
    runner = getattr(app.state, "recompute_runner", None)
    if runner is not None:
        await runner.wait_idle()


async def create_work_item(
    client: AsyncClient, *, team_id: str | None = None, title: str = "Ship it"
) -> str:
    if team_id is None:
        team_id = await create_team(client)
    response = await client.post("/api/work-items", json={"team_id": team_id, "title": title})
    assert response.status_code == 201
    work_item_id: str = response.json()["id"]
    return work_item_id


def days_ago(days: int) -> str:
    """ISO timestamp ``days`` days ago, pinned to 12:00 UTC (mid-bucket).

    API endpoints window against the server's wall clock, so tests must
    seed relative to now — but an event exactly N days ago sits on the
    same instant boundary the server buckets by. Anchoring mid-day keeps
    date-bucket assertions (history days, lead-time bins) 12 hours from
    any midnight flip between seeding and the request under test.
    """
    noon = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return (noon - timedelta(days=days)).isoformat()
