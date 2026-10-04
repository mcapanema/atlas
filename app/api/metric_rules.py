"""Metric rules: the workspace default and each team's overrides.

A PATCH that changes effective rules rewrites the affected scopes' snapshot
history in the background (app/api/recompute.py); the response carries the
recompute status to poll.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MetricRulesServiceDep, SessionDep
from app.api.recompute import RecomputeRunner, RecomputeRunnerDep
from app.api.schemas import MetricRulesOverridesWrite, MetricRulesViewRead
from app.application.metric_rules.service import RulesChange, RulesView

router = APIRouter(tags=["metric-rules"])


def _read(view: RulesView | None, missing: str) -> MetricRulesViewRead:
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{missing} not found")
    return MetricRulesViewRead.model_validate(view)


async def _save(
    save: Callable[[], Awaitable[RulesChange | None]],
    missing: str,
    session: AsyncSession,
    runner: RecomputeRunner,
) -> MetricRulesViewRead:
    # The runner is paused BEFORE the write: a scope rewrite holds SQLite's
    # single write lock until it commits, so writing first would block (and
    # 500) behind it. It restarts on exit, even on a 404/422, so pending
    # work isn't stranded.
    async with runner.paused() as queue:
        change = await save()
        if change is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{missing} not found"
            )
        await session.commit()  # the new rules (and "running"), before the run restarts
        if change.scopes:
            queue(change.organization_id, change.scopes)
    return MetricRulesViewRead.model_validate(change.view)


@router.get("/api/organizations/{organization_id}/metric-rules", response_model=MetricRulesViewRead)
async def get_workspace_rules(
    organization_id: UUID, service: MetricRulesServiceDep
) -> MetricRulesViewRead:
    return _read(
        await service.organization_view(organization_id), f"Organization {organization_id}"
    )


@router.patch(
    "/api/organizations/{organization_id}/metric-rules", response_model=MetricRulesViewRead
)
async def update_workspace_rules(
    organization_id: UUID,
    payload: MetricRulesOverridesWrite,
    service: MetricRulesServiceDep,
    session: SessionDep,
    runner: RecomputeRunnerDep,
) -> MetricRulesViewRead:
    return await _save(
        lambda: service.update_organization(organization_id, payload.changes()),
        f"Organization {organization_id}",
        session,
        runner,
    )


@router.post(
    "/api/organizations/{organization_id}/metric-rules/recompute",
    response_model=MetricRulesViewRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def recompute_history(
    organization_id: UUID,
    service: MetricRulesServiceDep,
    session: SessionDep,
    runner: RecomputeRunnerDep,
) -> MetricRulesViewRead:
    _read(await service.organization_view(organization_id), f"Organization {organization_id}")
    scopes = await service.organization_scopes(organization_id)
    async with runner.paused() as queue:  # before writing; see _save
        await service.start_recompute(organization_id)
        await session.commit()
        queue(organization_id, scopes)
    return _read(
        await service.organization_view(organization_id), f"Organization {organization_id}"
    )


@router.get("/api/teams/{team_id}/metric-rules", response_model=MetricRulesViewRead)
async def get_team_rules(team_id: UUID, service: MetricRulesServiceDep) -> MetricRulesViewRead:
    return _read(await service.team_view(team_id), f"Team {team_id}")


@router.patch("/api/teams/{team_id}/metric-rules", response_model=MetricRulesViewRead)
async def update_team_rules(
    team_id: UUID,
    payload: MetricRulesOverridesWrite,
    service: MetricRulesServiceDep,
    session: SessionDep,
    runner: RecomputeRunnerDep,
) -> MetricRulesViewRead:
    return await _save(
        lambda: service.update_team(team_id, payload.changes()),
        f"Team {team_id}",
        session,
        runner,
    )
