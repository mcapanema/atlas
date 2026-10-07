"""Automatic Linear sync on each organization's schedule (ADR-0014).

One in-process asyncio task (ADR-0002: no queue, no cron) ticks every
TICK_SECONDS, starting at once so a slot missed while Atlas was off
catches up on startup. Each tick asks SyncScheduleService which
organizations have a slot due and syncs them one at a time. That's the
same sync + snapshot capture as `POST /api/connectors/linear/sync`, in its
own session and transaction. The outcome is recorded on the schedule in a
second session, so a failed sync's rollback can't erase its own error.
A failure still consumes its slot: no retry until the next one.

Manual and automatic syncs share `lock`. A tick that finds a sync
running skips and retries next tick; the manual route waits for a
running auto sync.

ponytail: one scheduler per process, so run Atlas as a single uvicorn
worker (the Dockerfile does). Move to a DB lease or a job table if Atlas
ever runs several workers.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    LINEAR_NOT_CONFIGURED,
    linear_data_source,
    snapshot_service_for,
    sync_schedule_service_for,
    sync_service_for,
)
from app.application.sync_schedules.service import DueSync
from app.domain.sync.port import DeliveryDataSource

logger = logging.getLogger(__name__)

TICK_SECONDS = 60.0


class AutoSyncRunner:
    """Runs scheduled syncs, one organization at a time."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        source_factory: Callable[[], DeliveryDataSource | None],
        *,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._source_factory = source_factory
        self._tick_seconds = tick_seconds
        self._task: asyncio.Task[None] | None = None
        # Held by every sync, manual or automatic: one at a time.
        self.lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._loop())

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def tick(self) -> int:
        """Sync every organization with a due slot; how many ran (0 while a sync is running)."""
        if self.lock.locked():
            return 0
        async with self.lock:
            async with self._sessionmaker() as session:
                due = await sync_schedule_service_for(session).due()
            for job in due:
                await self._record(job, await self._sync(job.organization_id))
            return len(due)

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Auto-sync tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def _sync(self, organization_id: UUID) -> str | None:
        """Run one organization's sync; the error message, if it failed."""
        source = self._source_factory()
        if source is None:
            logger.warning("Auto sync skipped for %s: %s", organization_id, LINEAR_NOT_CONFIGURED)
            return LINEAR_NOT_CONFIGURED
        try:
            async with self._sessionmaker() as session:
                await sync_service_for(session, source).sync(organization_id)
                await snapshot_service_for(session).capture_all()
                await session.commit()
        except Exception as exc:
            logger.exception("Auto sync failed for organization %s", organization_id)
            return str(exc) or type(exc).__name__
        logger.info("Auto sync finished for organization %s", organization_id)
        return None

    async def _record(self, job: DueSync, error: str | None) -> None:
        async with self._sessionmaker() as session:
            await sync_schedule_service_for(session).record_run(
                job.organization_id, job.slot_at, error=error
            )
            await session.commit()


def get_auto_sync_runner(request: Request) -> AutoSyncRunner:
    runner: AutoSyncRunner | None = getattr(request.app.state, "auto_sync_runner", None)
    if runner is None:  # no lifespan ran (tests): create on first use, never started
        runner = AutoSyncRunner(request.app.state.sessionmaker, linear_data_source)
        request.app.state.auto_sync_runner = runner
    return runner


AutoSyncRunnerDep = Annotated[AutoSyncRunner, Depends(get_auto_sync_runner)]
