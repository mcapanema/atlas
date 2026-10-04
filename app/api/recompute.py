"""Background rewrite of snapshot history after a metric-rule change.

One in-process asyncio task (ADR-0002: no queue). A new schedule cancels
the running task and restarts with the union of pending scopes, so the
latest rules always win. Each scope is rewritten in its own session and
transaction: a cancel or failure never leaves a scope half old, half new.
A cancelled run never writes a finish status (CancelledError is not an
Exception), so it can't clobber the restarted run's "running" status.
The organization row's recompute status is the durable record — the
lifespan resumes any organization a restart left "running".

ponytail: one runner per process with a global cancel-and-restart. Move to
a job table + worker if recomputes outgrow one process.
"""

import asyncio
import logging
from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import metric_rules_service_for, snapshot_service_for
from app.application.metric_rules.service import ScopeRef

logger = logging.getLogger(__name__)


def _scope_key(scope: ScopeRef) -> str:
    return f"{scope.team_id}:{scope.project_id}"


class RecomputeRunner:
    """Runs snapshot-history recomputes one task at a time."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._pending: dict[UUID, set[ScopeRef]] = {}
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def schedule(self, organization_id: UUID, scopes: Iterable[ScopeRef]) -> None:
        """Queue `scopes` and (re)start the run; returns without waiting for it."""
        async with self._lock:
            self._pending.setdefault(organization_id, set()).update(scopes)
            await self._cancel()
            self._task = asyncio.create_task(self._run())

    async def resume(self) -> None:
        """Re-run every organization a restart left mid-recompute (lifespan)."""
        try:
            async with self._sessionmaker() as session:
                service = metric_rules_service_for(session)
                plans = [
                    (organization_id, await service.organization_scopes(organization_id))
                    for organization_id in await service.running_organizations()
                ]
        except Exception:
            logger.exception("Could not resume pending metric-rule recomputes")
            return
        for organization_id, scopes in plans:
            await self.schedule(organization_id, scopes)

    async def wait_idle(self) -> None:
        """Until no run is in flight (tests, shutdown)."""
        while (task := self._task) is not None and not task.done():
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        async with self._lock:
            await self._cancel()

    async def _cancel(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        for organization_id in list(self._pending):
            scopes = self._pending[organization_id]
            try:
                for scope in sorted(scopes, key=_scope_key):
                    await self._recompute(scope)
                    scopes.discard(scope)
            except Exception as exc:
                logger.exception(
                    "Metric-rule recompute failed for organization %s", organization_id
                )
                del self._pending[organization_id]
                await self._finish(organization_id, error=str(exc) or type(exc).__name__)
                continue
            del self._pending[organization_id]
            await self._finish(organization_id, error=None)

    async def _recompute(self, scope: ScopeRef) -> None:
        async with self._sessionmaker() as session:
            await snapshot_service_for(session).recompute_scope(
                team_id=scope.team_id, project_id=scope.project_id
            )
            await session.commit()

    async def _finish(self, organization_id: UUID, *, error: str | None) -> None:
        async with self._sessionmaker() as session:
            await metric_rules_service_for(session).finish_recompute(organization_id, error=error)
            await session.commit()


def get_recompute_runner(request: Request) -> RecomputeRunner:
    runner: RecomputeRunner | None = getattr(request.app.state, "recompute_runner", None)
    if runner is None:  # no lifespan ran (tests): create on first use
        runner = RecomputeRunner(request.app.state.sessionmaker)
        request.app.state.recompute_runner = runner
    return runner


RecomputeRunnerDep = Annotated[RecomputeRunner, Depends(get_recompute_runner)]
